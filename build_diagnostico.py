"""
Genera diagnostico_fondos.xlsx cruzando:
  - 20260507 Fondos Inmobiliarios.xlsx (listado maestro)
  - registro_rentabilidad.xlsx (estado actual por fondo, ya trae una columna "Estado"
    con el resultado del ultimo scrape / re-scrape)
  - fondos_pendientes.xlsx (detalle adicional para los casos problematicos ya conocidos)
  - Fondos Descargados\\<Administradora>\\<Fondo>\\ (que se descargo realmente)

No descarga nada nuevo ni modifica los .py del scraper: es un diagnostico de
lectura sobre lo que ya existe en el proyecto (Tarea 1 de INSTRUCCIONES_VSCODE.txt).
"""
import os
import re
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DESCARGADOS = os.path.join(BASE, "Fondos Descargados")

CATEGORIAS = {
    "OK": "OK. Todo correcto",
    "A": "A. Pagina no reconocida (no encuentra el link del factsheet)",
    "B": "B. Sitio bloquea automatizacion (403 / Cloudflare / anti-bot)",
    "C": "C. Se descargo el documento equivocado",
    "D": "D. PDF sin texto (escaneado/imagen) -> requiere OCR",
    "E": "E. Rentabilidad en grafico / tabla no estandar (no extraible por regex)",
    "F": "F. Rentabilidad extraida parcialmente",
    "G": "G. La administradora no publica factsheet",
}

# orden de dificultad para el ordenamiento final (0 = mas facil / ya resuelto)
DIFICULTAD = {"OK": 0, "F": 1, "E": 2, "D": 3, "C": 4, "A": 5, "B": 6, "G": 7}

CAMPOS_RENT = [
    "Rent. 1M", "Rent. 3M", "Rent. 6M", "Rent. YTD", "Rent. 12M (1A)",
    "Rent. 24M (2A)", "Rent. 36M (3A)", "Rent. Desde Inicio",
    "Dividend Yield", "TIR", "Cap Rate", "LTV", "Rentabilidad Directa", "Leverage",
]


def clasificar(estado, notas, algun_valor):
    """Devuelve (categoria, es_doc_correcto, se_leyo_rentabilidad) a partir del
    texto libre que ya dejo el scraper en la columna Estado/Notas."""
    e = (estado or "").lower()

    if "no publica factsheet" in e:
        return "G", "No (se descargo EEFF u otro documento como mejor alternativa)", "No"

    if "bloquea automatizacion" in e or "403" in e or "cloudflare" in e:
        return "B", "No (bloqueado; el archivo actual es el documento equivocado)", "No"

    if "sin capa de texto" in e or "escaneado" in e:
        return "D", "Si", "No (PDF escaneado, requiere OCR)"

    if "sitio caido" in e or "no respondio" in e or "documento equivocado" in e:
        return "C", "No (documento reciclado / incorrecto, ver notas)", "No"

    if ("rentabilidad en formato grafico" in e or "no extraible" in e
            or "no se pudo extraer" in e or "no incluye la tabla" in e):
        return "E", "Si", "No (la rentabilidad esta en grafico, no en texto/tabla, o el informe no la incluye)"

    if "parcialmente" in e or "parcial" in e:
        return "F", "Si", "Parcial (se extrajeron algunos campos pero no todos)"

    if "rentabilidad extraida" in e:
        if algun_valor:
            return "OK", "Si", "Si"
        return "F", "Si", "Parcial (se extrajeron algunos campos pero no todos)"

    return "F", "Si (revisar)", "Parcial / sin clasificar automaticamente"


def main():
    master = pd.read_excel(
        os.path.join(BASE, "20260507 Fondos Inmobiliarios.xlsx"), header=4
    ).dropna(how="all")
    master = master[["Administradora", "Nombre", "Link"]].rename(columns={"Nombre": "Fondo"})
    master["Administradora"] = master["Administradora"].str.strip()
    master["Fondo"] = master["Fondo"].str.strip()

    dup_mask = master.duplicated(subset=["Administradora", "Fondo"], keep=False)
    duplicados = master[dup_mask]

    reg = pd.read_excel(os.path.join(BASE, "registro_rentabilidad.xlsx"))
    reg.columns = [c.replace("�", "a") for c in reg.columns]

    pend = pd.read_excel(os.path.join(BASE, "fondos_pendientes.xlsx"))

    filas = []
    for _, m in master.drop_duplicates(subset=["Administradora", "Fondo"]).iterrows():
        adm, fondo, link = m["Administradora"], m["Fondo"], m["Link"]

        r = reg[(reg["Administradora"] == adm) & (reg["Fondo"] == fondo)]
        p = pend[(pend["Administradora"] == adm) & (pend["Fondo"] == fondo)]

        carpeta = os.path.join(DESCARGADOS, adm, fondo)
        archivos_disco = []
        if os.path.isdir(carpeta):
            archivos_disco = sorted(os.listdir(carpeta))
        se_descargo = "Si" if archivos_disco else "No"

        if len(r):
            row = r.iloc[0]
            estado = row.get("Estado", "")
            notas = row.get("Notas", "")
            archivo = row.get("Archivo", archivos_disco[0] if archivos_disco else "")
            algun_valor = any(pd.notna(row.get(c)) for c in CAMPOS_RENT)
        else:
            estado, notas, archivo, algun_valor = "", "", (archivos_disco[0] if archivos_disco else ""), False

        if not archivos_disco:
            categoria = "A"
            doc_correcto = "No (no se descargo nada)"
            se_leyo = "No"
            detalle = "No existe carpeta/archivo en 'Fondos Descargados' para este fondo."
        else:
            categoria, doc_correcto, se_leyo = clasificar(estado, notas, algun_valor)
            detalle = estado if pd.notna(estado) and estado else "(sin Estado registrado)"

        detalle_extra = ""
        siguiente_paso = ""
        if len(p):
            prow = p.iloc[0]
            detalle_extra = str(prow.get("Detalle", "") or "")
            siguiente_paso = str(prow.get("Que se necesita", "") or "")

        if not siguiente_paso:
            siguiente_paso = {
                "OK": "Ninguno, dato ya disponible.",
                "F": "Revisar el PDF y completar manualmente los campos faltantes, o ajustar el regex del agente.",
                "E": "Construir un agente que lea el grafico (ejes/leyenda) o pida el dato en formato tabla a la administradora.",
                "D": "Aplicar OCR (pytesseract/ocrmypdf) o buscar una version nativa (no escaneada) del documento.",
                "C": "Reintentar la descarga apuntando al documento correcto (factsheet, no el que se bajo).",
                "A": "Revisar manualmente el sitio y ajustar el selector/URL del agente para encontrar el factsheet.",
                "B": "Descarga manual indicada por el usuario; no intentar evadir el bloqueo.",
                "G": "Confirmar con la administradora si existe factsheet en otro canal (CMF, reportes a aportantes).",
            }[categoria]

        nota_final = notas if pd.notna(notas) and notas else ""
        if detalle_extra:
            nota_final = (nota_final + " | " if nota_final else "") + detalle_extra

        filas.append({
            "Administradora": adm,
            "Fondo": fondo,
            "Link": link,
            "Se descargo": se_descargo,
            "Archivo": archivo,
            "Documento correcto (factsheet)": doc_correcto,
            "Se leyo la rentabilidad": se_leyo,
            "Categoria": categoria,
            "Categoria_desc": CATEGORIAS[categoria],
            "Detalle": detalle,
            "Notas adicionales": nota_final,
            "Siguiente paso sugerido": siguiente_paso,
            "_dificultad": DIFICULTAD[categoria],
        })

    df = pd.DataFrame(filas)

    # dificultad promedio por administradora -> ordena administradoras de
    # mas facil (mayoria OK) a mas dificil, y dentro de cada una por dificultad de fondo
    adm_rank = df.groupby("Administradora")["_dificultad"].mean().sort_values()
    df["_adm_rank"] = df["Administradora"].map(adm_rank)
    df = df.sort_values(
        by=["_adm_rank", "Administradora", "_dificultad", "Fondo"]
    ).drop(columns=["_dificultad", "_adm_rank"])

    out_path = os.path.join(BASE, "diagnostico_fondos.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Diagnostico", index=False)

        resumen = (
            df.groupby(["Administradora", "Categoria"])
            .size()
            .unstack(fill_value=0)
        )
        for cat in CATEGORIAS:
            if cat not in resumen.columns:
                resumen[cat] = 0
        resumen = resumen[list(CATEGORIAS.keys())]
        resumen["Total"] = resumen.sum(axis=1)
        resumen.to_excel(writer, sheet_name="Resumen por administradora")

        cat_resumen = df["Categoria"].value_counts().reindex(CATEGORIAS.keys(), fill_value=0)
        cat_df = pd.DataFrame({
            "Categoria": cat_resumen.index,
            "Descripcion": [CATEGORIAS[c] for c in cat_resumen.index],
            "N fondos": cat_resumen.values,
        })
        cat_df.to_excel(writer, sheet_name="Resumen por categoria", index=False)

        if len(duplicados):
            duplicados.to_excel(writer, sheet_name="Duplicados en listado maestro", index=False)

    # autoajuste simple de ancho de columnas
    from openpyxl import load_workbook
    wb = load_workbook(out_path)
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col)
            letter = col[0].column_letter
            ws.column_dimensions[letter].width = min(max(10, max_len + 2), 60)
    wb.save(out_path)

    print(f"OK -> {out_path}")
    print()
    print("Resumen por categoria:")
    print(cat_df.to_string(index=False))
    print()
    print("Resumen por administradora:")
    print(resumen.to_string())
    if len(duplicados):
        print()
        print("ATENCION - filas duplicadas en el listado maestro (mismo fondo repetido):")
        print(duplicados.to_string(index=False))


if __name__ == "__main__":
    main()
