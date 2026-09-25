"""
Agente master (orquestador).

  python master.py                     -> todas las administradoras migradas
  python master.py --adm "BTG Pactual"  -> solo una administradora
  python master.py --solo-fallidos      -> reemplaza a retry_fondos.py:
                                            solo reprocesa fondos cuyo estado
                                            actual en registro_rentabilidad.xlsx
                                            no es "OK"

Que hace:
  1. Lee el listado maestro de fondos.
  2. Asigna cada fondo al agente de su administradora (ver AGENTES abajo).
     Las administradoras que todavia no tienen agente propio se dejan
     intactas en el registro (no se tocan sus filas) y se listan al final
     bajo "sin migrar".
  3. Ejecuta los agentes en paralelo (asyncio, concurrencia limitada a
     CONCURRENCIA para no gatillar bloqueos anti-bot).
  4. Si un agente falla para un fondo, registra el error y sigue con el resto.
  5. Escribe registro_rentabilidad.xlsx (mismas columnas de siempre) y
     fondos_data.json para el dashboard.
  6. Regenera diagnostico_fondos.xlsx (reusa build_diagnostico.py).
  7. Imprime resumen final: X OK / Y parciales / Z fallidos, por administradora.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl import load_workbook

from agentes.base import CAMPOS_REGISTRO, archivo_mas_reciente, sanitize
from agentes.btg import AgenteBTG
from agentes.larrainvial import AgenteLarrainVial
from agentes.toesca import AgenteToesca
from agentes.independencia import AgenteIndependencia
from agentes.security import AgenteSecurity
from agentes.principal import AgentePrincipal
from agentes.zurich import AgenteZurich
from agentes.credicorp import AgenteCredicorp
from agentes.frontal_trust import AgenteFrontalTrust
from agentes.banchile import AgenteBanchile
from agentes.ameris import AgenteAmeris
from agentes.asset import AgenteAsset
from agentes.bice import AgenteBICE
from agentes.santander import AgenteSantander

BASE = Path(__file__).resolve().parent
FONDOS_FILE = BASE / "20260507 Fondos Inmobiliarios.xlsx"
REGISTRO_FILE = BASE / "registro_rentabilidad.xlsx"
DATA_JSON = BASE / "fondos_data.json"
OUTPUT_DIR = BASE / "Fondos Descargados"

CONCURRENCIA = 3

# Administradora -> clase de agente. Se va completando a medida que se migra
# cada una (Tarea 2.3 de INSTRUCCIONES_VSCODE.txt: de a una, con OK del
# usuario antes de seguir).
AGENTES = {
    "BTG Pactual": AgenteBTG,
    "Larrain Vial": AgenteLarrainVial,
    "Toesca": AgenteToesca,
    "Independencia": AgenteIndependencia,
    "Inversiones Security": AgenteSecurity,
    "Princiapl": AgentePrincipal,
    "Zurich": AgenteZurich,
    "Credicorp": AgenteCredicorp,
    "Frontal Trust": AgenteFrontalTrust,
    "Banchile": AgenteBanchile,
    "Ameris": AgenteAmeris,
    "Asset": AgenteAsset,
    "BICE": AgenteBICE,
    "Santander": AgenteSantander,
}

CAMPOS_META = ["moneda", "plazo", "n_activos"]
CAMPOS_META_HEADERS = ["Moneda", "Plazo/Duracion", "N Activos"]

HEADERS = [
    "Fecha actualizacion", "Administradora", "Fondo", "Archivo",
] + CAMPOS_REGISTRO + CAMPOS_META_HEADERS + ["Estado", "Notas"]

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def leer_fondos_maestro() -> list[dict]:
    wb = load_workbook(FONDOS_FILE)
    ws = wb.active
    fondos = []
    for row in ws.iter_rows(min_row=6, values_only=True):
        if len(row) < 4:
            continue
        _, administradora, nombre, link = row[0], row[1], row[2], row[3]
        if administradora and nombre and link:
            fondos.append({
                "administradora": str(administradora).strip(),
                "nombre": str(nombre).strip(),
                "link": str(link).strip(),
            })
    # de-dup por (administradora, nombre) -- el maestro trae una fila repetida
    vistos = set()
    unicos = []
    for f in fondos:
        key = (f["administradora"], f["nombre"])
        if key in vistos:
            continue
        vistos.add(key)
        unicos.append(f)
    return unicos


def estados_actuales() -> dict[tuple, str]:
    """(administradora, fondo) -> texto de Estado en el registro actual."""
    if not REGISTRO_FILE.exists():
        return {}
    wb = load_workbook(REGISTRO_FILE)
    ws = wb["Registro"]
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    try:
        i_adm = headers.index("Administradora")
        i_fondo = headers.index("Fondo")
        i_estado = headers.index("Estado")
    except ValueError:
        return {}
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        out[(row[i_adm], row[i_fondo])] = row[i_estado] or ""
    return out


async def procesar_fondo(agente, fondo: dict, sem: asyncio.Semaphore, browser) -> dict:
    """Corre descargar (si hace falta) + inspeccionar + extraer para un fondo.
    Nunca lanza: cualquier excepcion queda registrada en el resultado."""
    nombre = fondo["nombre"]
    async with sem:
        try:
            pdf_path = archivo_mas_reciente(agente.administradora, nombre)
            if pdf_path is None and browser is not None:
                pdf_path = await agente.descargar(fondo, browser)

            if pdf_path is None:
                out = {c: None for c in CAMPOS_REGISTRO + CAMPOS_META}
                out.update({
                    "administradora": agente.administradora,
                    "fondo": nombre,
                    "archivo": "",
                    "estado": "No se pudo descargar (sin browser en este entorno o sitio no respondio)",
                    "notas": "",
                })
                return out

            datos = agente.extraer(pdf_path)
            out = {c: datos.get(c) for c in CAMPOS_REGISTRO + CAMPOS_META}
            out.update({
                "administradora": agente.administradora,
                "fondo": nombre,
                "archivo": pdf_path.name,
                "estado": datos.get("estado", ""),
                "notas": datos.get("notas", ""),
                "estado_categoria": datos.get("estado_categoria", ""),
            })
            return out
        except Exception as e:
            out = {c: None for c in CAMPOS_REGISTRO + CAMPOS_META}
            out.update({
                "administradora": agente.administradora,
                "fondo": nombre,
                "archivo": "",
                "estado": f"error: {str(e)[:120]}",
                "notas": "",
            })
            return out


async def ejecutar(administradoras: list[str] | None, solo_fallidos: bool) -> list[dict]:
    todos = leer_fondos_maestro()
    estados = estados_actuales() if solo_fallidos else {}

    admins_a_correr = administradoras or list(AGENTES.keys())
    admins_no_migradas = [a for a in admins_a_correr if a not in AGENTES]
    if admins_no_migradas:
        print(f"AVISO: sin agente todavia para: {', '.join(admins_no_migradas)} "
              f"(se omiten, sus filas del registro quedan intactas)")

    fondos = [f for f in todos if f["administradora"] in AGENTES
              and f["administradora"] in admins_a_correr]

    if solo_fallidos:
        fondos = [
            f for f in fondos
            if not str(estados.get((f["administradora"], f["nombre"]), "")).startswith("OK")
        ]

    if not fondos:
        print("Nada que procesar con los filtros dados.")
        return []

    print(f"Procesando {len(fondos)} fondo(s) con {len(set(f['administradora'] for f in fondos))} agente(s)...")

    sem = asyncio.Semaphore(CONCURRENCIA)
    browser = None
    pw = None
    resultados = []
    try:
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)
        except Exception as e:
            print(f"AVISO: no se pudo iniciar el navegador ({e}). "
                  f"Solo se usaran PDFs ya descargados en 'Fondos Descargados/'.")

        tareas = []
        for fondo in fondos:
            agente = AGENTES[fondo["administradora"]]()
            tareas.append(procesar_fondo(agente, fondo, sem, browser))

        resultados = await asyncio.gather(*tareas)
    finally:
        if browser is not None:
            await browser.close()
        if pw is not None:
            await pw.stop()

    return resultados


def actualizar_registro(resultados: list[dict]) -> None:
    """Reemplaza, dentro de registro_rentabilidad.xlsx, solo las filas de los
    fondos que se acaban de procesar. Las filas de administradoras sin
    migrar (o fondos no incluidos en esta corrida) se dejan tal cual."""
    if REGISTRO_FILE.exists():
        wb = load_workbook(REGISTRO_FILE)
        ws = wb["Registro"]
        filas_existentes = list(ws.iter_rows(min_row=2, values_only=True))
        headers_actuales = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Registro"
        filas_existentes = []
        headers_actuales = HEADERS

    procesados = {(r["administradora"], r["fondo"]): r for r in resultados}

    # Se trabaja siempre por diccionario (columna -> valor) y se re-emite en
    # el orden de HEADERS al final. Asi, si HEADERS crece (ej. se agregan
    # columnas nuevas como Moneda/Plazo/N Activos), las filas viejas que no
    # se reprocesaron en esta corrida no quedan desalineadas: simplemente les
    # faltan esos campos nuevos (se guardan vacios) en vez de correrse de columna.
    filas_finales = []
    for fila in filas_existentes:
        d = dict(zip(headers_actuales, fila))
        key = (d.get("Administradora"), d.get("Fondo"))
        if key in procesados:
            continue  # se reemplaza mas abajo
        filas_finales.append(d)

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    for r in resultados:
        d = {
            "Fecha actualizacion": fecha,
            "Administradora": r["administradora"],
            "Fondo": r["fondo"],
            "Archivo": r["archivo"],
            "Estado": r.get("estado", ""),
            "Notas": r.get("notas", ""),
        }
        for c in CAMPOS_REGISTRO:
            d[c] = r.get(c)
        for c, h in zip(CAMPOS_META, CAMPOS_META_HEADERS):
            d[h] = r.get(c)
        filas_finales.append(d)

    # reescribe la hoja completa
    if ws.max_row > 0:
        ws.delete_rows(1, ws.max_row)
    ws.append(HEADERS)
    for col in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    for d in filas_finales:
        ws.append([d.get(h) for h in HEADERS])

    wb.save(REGISTRO_FILE)


def escribir_json(resultados: list[dict]) -> None:
    if REGISTRO_FILE.exists():
        wb = load_workbook(REGISTRO_FILE)
        ws = wb["Registro"]
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        data = [dict(zip(headers, row)) for row in ws.iter_rows(min_row=2, values_only=True)]
    else:
        data = resultados

    DATA_JSON.write_text(
        json.dumps({
            "generado": datetime.now().isoformat(timespec="seconds"),
            "fondos": data,
        }, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def resumen(resultados: list[dict]) -> None:
    if not resultados:
        return
    por_admin: dict[str, dict[str, int]] = {}
    for r in resultados:
        adm = r["administradora"]
        categoria = r.get("estado_categoria") or ""
        if categoria == "OK":
            bucket = "OK"
        elif categoria == "F":
            bucket = "parcial"
        else:
            bucket = "fallido"  # A/B/C/D/E/G o sin PDF/error
        por_admin.setdefault(adm, {"OK": 0, "parcial": 0, "fallido": 0})[bucket] += 1

    print("\nResumen:")
    tot = {"OK": 0, "parcial": 0, "fallido": 0}
    for adm, c in por_admin.items():
        print(f"  {adm}: {c['OK']} OK / {c['parcial']} parciales / {c['fallido']} fallidos")
        for k in tot:
            tot[k] += c[k]
    print(f"  TOTAL: {tot['OK']} OK / {tot['parcial']} parciales / {tot['fallido']} fallidos")


def main():
    parser = argparse.ArgumentParser(description="Orquestador de agentes de fondos.")
    parser.add_argument("--adm", action="append", help="Administradora a correr (repetible). Por defecto: todas las migradas.")
    parser.add_argument("--solo-fallidos", action="store_true", help="Solo reprocesa fondos que no estan en estado OK.")
    args = parser.parse_args()

    resultados = asyncio.run(ejecutar(args.adm, args.solo_fallidos))

    if resultados:
        actualizar_registro(resultados)
        escribir_json(resultados)
        resumen(resultados)

        sys.path.insert(0, str(BASE))
        import build_diagnostico
        build_diagnostico.main()
    else:
        print("Registro y diagnostico no se modificaron.")


if __name__ == "__main__":
    main()
