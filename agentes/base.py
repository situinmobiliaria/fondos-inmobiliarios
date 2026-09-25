"""
Clase base para los agentes por administradora.

Cada agente concreto (agentes/btg.py, agentes/toesca.py, ...) hereda de
AgenteBase y sobreescribe lo que necesite:

  descargar(fondo)   -> navega la pagina de ESA administradora, encuentra el
                         factsheet mas reciente y lo guarda en
                         "Fondos Descargados/<Administradora>/<Fondo>/AAAAMMDD_<Fondo>.pdf"
                         Por defecto usa la logica generica de scraper_fondos.py
                         (busqueda de links por keyword), que ya funciona bien
                         para administradoras "simples" como BTG Pactual.

  inspeccionar(pdf)   -> abre el PDF y devuelve un dict describiendo si es un
                         factsheet valido, la fecha del reporte y donde esta
                         la tabla de rentabilidad (texto/tabla/grafico/imagen).

  extraer(pdf)        -> devuelve el dict estandar de campos de registro
                         (ver CAMPOS_REGISTRO), + fecha_reporte, serie, moneda.

Cada agente debe declarar administradora = "Nombre exacto como aparece en el
listado maestro" y puede correrse aislado con `python -m agentes.<modulo>`.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pdfplumber

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "Fondos Descargados"
FONDOS_FILE = Path(__file__).resolve().parent.parent / "20260507 Fondos Inmobiliarios.xlsx"

# Columnas estandar de salida de extraer() / registro_rentabilidad.xlsx
CAMPOS_REGISTRO = [
    "Rent. 1M", "Rent. 3M", "Rent. 6M", "Rent. YTD", "Rent. 12M (1A)",
    "Rent. 24M (2A)", "Rent. 36M (3A)", "Rent. Desde Inicio",
    "Dividend Yield", "TIR", "Cap Rate", "LTV",
    "Rentabilidad Directa", "Leverage",
]

# Categorias de diagnostico (mismas que diagnostico_fondos.xlsx / Tarea 1)
CATEGORIAS_ESTADO = {
    "OK": "OK. Todo correcto",
    "A": "A. Pagina no reconocida",
    "B": "B. Sitio bloquea automatizacion",
    "C": "C. Se descargo el documento equivocado",
    "D": "D. PDF sin texto (escaneado/imagen)",
    "E": "E. Rentabilidad en grafico / tabla no estandar",
    "F": "F. Rentabilidad extraida parcialmente",
    "G": "G. La administradora no publica factsheet",
}


def sanitize(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\n\r\t]', "", name).strip()


def carpeta_fondo(administradora: str, nombre: str) -> Path:
    folder = OUTPUT_DIR / sanitize(administradora) / sanitize(nombre)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def archivo_mas_reciente(administradora: str, nombre: str) -> Optional[Path]:
    """Devuelve el PDF mas reciente ya descargado para ese fondo, si existe."""
    folder = OUTPUT_DIR / sanitize(administradora) / sanitize(nombre)
    if not folder.is_dir():
        return None
    pdfs = sorted(folder.glob("*.pdf"))
    return pdfs[-1] if pdfs else None


def registro_vacio() -> dict:
    """Dict con todos los campos de registro en None, para que cada agente
    solo tenga que llenar lo que efectivamente encontro."""
    d = {c: None for c in CAMPOS_REGISTRO}
    d.update({
        "fecha_reporte": None,
        "serie": None,
        "moneda": None,
        "plazo": None,      # duracion/plazo del fondo, tal como aparece en el PDF (texto libre, ej. "10 anos")
        "n_activos": None,  # N de propiedades/proyectos/activos del fondo, si el PDF lo declara explicitamente
        "estado_categoria": None,   # una de CATEGORIAS_ESTADO
        "estado": "",               # texto libre legible (va a columna Estado)
        "notas": "",
    })
    return d


_MONEDA_MAP = {
    "clp": "CLP", "pesos chilenos": "CLP", "pesos": "CLP", "$": "CLP",
    "uf": "UF", "usd": "USD", "dolares": "USD", "dólares": "USD", "us$": "USD",
}

_MONEDA_LABELS = ["Moneda del Fondo", "Moneda Fondo", "Moneda del fondo", "Moneda:", "Moneda "]
_PLAZO_LABELS = ["Plazo de Duración", "Plazo del fondo", "Plazo:", "Duración",
                 "Duracion", "Duraci", "Plazo "]
_N_ACTIVOS_LABELS = [
    "N°Activos", "N° Activos", "Nº Activos", "N Activos",
    "N°Proyectos Vigentes", "N° Proyectos Vigentes",
    "N°Proyectos", "N° Proyectos",
    "Número de propiedades", "Numero de propiedades",
]


def extraer_metadatos_comunes(texto: str) -> dict:
    """Intenta extraer Moneda / Plazo (duracion) / N de Activos con
    etiquetas genericas que se repiten en varias administradoras. No inventa
    nada: si ninguna etiqueta aparece, el campo queda en None. Cada agente
    puede llamar a esto como base y despues sobreescribir con logica propia
    si conoce mejor el layout de su factsheet."""
    out = {"moneda": None, "plazo": None, "n_activos": None}

    for lbl in _MONEDA_LABELS:
        idx = texto.find(lbl)
        if idx == -1:
            continue
        snippet = texto[idx + len(lbl): idx + len(lbl) + 25].strip().lower()
        for clave, val in _MONEDA_MAP.items():
            if snippet.startswith(clave):
                out["moneda"] = val
                break
        if out["moneda"]:
            break

    for lbl in _PLAZO_LABELS:
        idx = texto.find(lbl)
        if idx == -1:
            continue
        snippet = texto[idx + len(lbl): idx + len(lbl) + 40]
        m = re.search(r"(\d+\s*a[n�ñ]os(?:\s*\([^)]{0,20}\))?)", snippet)
        if m:
            out["plazo"] = m.group(1).strip().replace("�", "ñ")
            break

    for lbl in _N_ACTIVOS_LABELS:
        idx = texto.find(lbl)
        if idx == -1:
            continue
        snippet = texto[idx + len(lbl): idx + len(lbl) + 30].split("\n")[0]
        # numeros NO seguidos de "%" (para no agarrar un porcentaje de un
        # grafico/leyenda vecino que quedo pegado en la misma linea)
        valores = re.findall(r"\d+(?!\s*%)", snippet)
        if not valores:
            continue
        if "propiedades" in lbl.lower():
            # fila con varias columnas de anos (ej. "82 81 81 80 81") ->
            # se toma la columna mas reciente (ultima)
            out["n_activos"] = int(valores[-1])
        else:
            # etiqueta de un solo valor (ej. "N Activos 36") -> el primero,
            # por si hay texto/leyenda de un grafico vecino pegado despues
            out["n_activos"] = int(valores[0])
        break

    return out


class AgenteBase:
    """Agente generico. Las administradoras 'simples' (link con anchors
    directos al factsheet) pueden usar descargar() sin sobreescribirlo."""

    administradora: str = ""

    # Palabras clave / blacklist heredadas del scraper generico original
    KEYWORDS_FICHA = [
        "información del fondo", "informacion del fondo", "factsheet",
        "ficha del fondo", "ficha de fondo", "ficha comercial",
        "información de fondo", "informacion de fondo", "fact sheet",
    ]
    BLACKLIST_DOC = [
        "reglamento", "estados financieros", "estado financiero", "auditores",
        "auditor", "auditada", "fecu", "acta ", "aviso ", "citacion",
        "citación", "deposito", "depósito", "valor cuota", "memoria anual",
        "hecho esencial", "política", "politica",
    ]

    def carpeta(self, nombre_fondo: str) -> Path:
        return carpeta_fondo(self.administradora, nombre_fondo)

    def es_keyword(self, texto: str) -> bool:
        t = texto.lower().strip()
        if any(bl in t for bl in self.BLACKLIST_DOC):
            return False
        return any(kw in t for kw in self.KEYWORDS_FICHA)

    # ------------------------------------------------------------------
    # 1) DESCARGAR
    # ------------------------------------------------------------------
    async def descargar(self, fondo: dict, browser) -> Optional[Path]:
        """Implementacion generica: busca en la pagina del fondo un link cuyo
        texto matchee KEYWORDS_FICHA (sin BLACKLIST_DOC) y lo descarga.
        Administradoras con paginas mas complejas (iframes, dashboards con
        variable=ID, sitios que bloquean bots, etc.) deben sobreescribir este
        metodo -- ver scraper_especiales.py para la logica ya probada de
        Frontal Trust y Santander como referencia.
        """
        nombre, link = fondo["nombre"], fondo["link"]
        folder = self.carpeta(nombre)
        date_str = datetime.now().strftime("%Y%m%d")
        base = f"{date_str}_{sanitize(nombre)}"

        context = await browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        filepath = None
        try:
            try:
                await page.goto(link, wait_until="networkidle", timeout=40_000)
            except Exception:
                await page.goto(link, wait_until="domcontentloaded", timeout=40_000)
                await asyncio.sleep(5)

            anchors = await page.query_selector_all("a")
            candidatos = []
            for a in anchors:
                try:
                    texto = (await a.inner_text()).strip()
                    href = await a.get_attribute("href") or ""
                    if self.es_keyword(texto):
                        candidatos.append((texto, href, a))
                except Exception:
                    continue

            if not candidatos:
                return None

            texto_doc, href_doc, anchor_doc = candidatos[0]
            from urllib.parse import urljoin
            if href_doc and not href_doc.startswith("http"):
                href_doc = urljoin(link, href_doc)

            if href_doc and re.search(r"\.(pdf|xlsx|xls)(\?.*)?$", href_doc, re.IGNORECASE):
                import requests as req
                r = req.get(href_doc, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, stream=True)
                r.raise_for_status()
                ext = re.search(r"\.(pdf|xlsx|xls)", href_doc, re.IGNORECASE).group(1)
                filepath = folder / f"{base}.{ext}"
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
            else:
                try:
                    async with page.expect_download(timeout=15_000) as dl_info:
                        await anchor_doc.click()
                    download = await dl_info.value
                    ext = Path(download.suggested_filename).suffix or ".pdf"
                    filepath = folder / f"{base}{ext}"
                    await download.save_as(filepath)
                except Exception:
                    filepath = None
        finally:
            await context.close()

        return filepath

    # ------------------------------------------------------------------
    # 2) INSPECCIONAR
    # ------------------------------------------------------------------
    def inspeccionar(self, pdf_path: Path) -> dict:
        """Chequeo generico: extrae texto y dice si hay o no capa de texto.
        Sobreescribir para detectar fecha de reporte / serie especifica de
        cada administradora."""
        info = {
            "tiene_texto": False,
            "n_paginas": 0,
            "es_factsheet_probable": None,
            "fecha_reporte": None,
        }
        try:
            with pdfplumber.open(pdf_path) as pdf:
                info["n_paginas"] = len(pdf.pages)
                texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
                info["tiene_texto"] = len(texto.strip()) > 50
        except Exception as e:
            info["error"] = str(e)
        return info

    # ------------------------------------------------------------------
    # 3) EXTRAER
    # ------------------------------------------------------------------
    def extraer(self, pdf_path: Path) -> dict:
        """Debe ser sobreescrito por cada agente: cada administradora tiene su
        propio layout de factsheet. La base solo devuelve el dict vacio."""
        r = registro_vacio()
        r["estado_categoria"] = "E"
        r["estado"] = (
            "Sin extractor especifico implementado para esta administradora "
            "(usar AgenteBase.extraer como placeholder)."
        )
        return r

    # ------------------------------------------------------------------
    # Utilidades para correr el agente aislado / dentro de master.py
    # ------------------------------------------------------------------
    @staticmethod
    def _texto_pdf(pdf_path: Path) -> str:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)

    @staticmethod
    def buscar_pct(texto: str, label: str, window: int = 60,
                   permitir_negativo: bool = True) -> Optional[str]:
        """Busca `label` en el texto y devuelve el primer numero-porcentaje
        que aparece a continuacion, dentro de una ventana de `window`
        caracteres (para evitar cruzar con otra etiqueta lejana).
        Usa una ventana en vez de una regex unica porque pdfplumber suele
        entremezclar columnas y el texto entre la etiqueta y el numero no es
        estable (parentesis, notas al pie, otro numero antes, etc.)."""
        idx = texto.find(label)
        if idx == -1:
            return None
        snippet = texto[idx + len(label): idx + len(label) + window]
        signo = r"-?" if permitir_negativo else ""
        m = re.search(rf"({signo}\d+[.,]\d+)\s*%", snippet)
        return m.group(1).replace(".", ",") if m else None

    @staticmethod
    def buscar_num(texto: str, label: str, sufijo: str = "", window: int = 60) -> Optional[str]:
        idx = texto.find(label)
        if idx == -1:
            return None
        snippet = texto[idx + len(label): idx + len(label) + window]
        m = re.search(rf"(\d+[.,]?\d*)\s*{re.escape(sufijo)}", snippet)
        return m.group(1).replace(".", ",") if m else None

    @staticmethod
    def leer_ultimo_valor_grafico(pdf_path: Path, titulo_grafico: str,
                                   ventana_vertical: float = 80,
                                   sufijo: str = "%") -> Optional[str]:
        """Tecnica 1 de lectura de graficos (Ronda 2, seccion 2.1): cuando un
        grafico de lineas/barras trae sus VALORES como etiquetas de texto
        reales en el PDF (no como imagen), pdfplumber los puede leer -- el
        problema es que quedan revueltos con el resto de la pagina al usar
        extract_text() plano, porque pdfplumber no sabe que forman parte de
        un grafico.

        Esta funcion usa las coordenadas (x0, top) de cada palabra para
        separar dos grupos que se confunden facilmente:
          - las etiquetas del EJE (habitualmente todas en la misma columna
            x0, a intervalos verticales regulares: son la escala del grafico,
            no un dato)
          - las etiquetas de DATO (una por punto/barra, cada una en su propia
            columna x0, cerca de su marca en el grafico)
        Se descarta la columna x0 mas repetida (el eje) y se toma el valor
        de dato con mayor x0 = el mas a la derecha = el mas reciente
        (asumiendo, como en todos los grafos de evolucion vistos, que el
        tiempo avanza de izquierda a derecha).

        Devuelve el valor como string (ej. "40") o None si no se pudo
        determinar con confianza (menos de 2 candidatos, o todos en la
        misma columna == parecen ser todos eje).
        """
        import pdfplumber

        patron = re.compile(rf"^-?\d+[.,]?\d*{re.escape(sufijo)}$")
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    palabras = page.extract_words()
                    titulo_word = None
                    idx_by_top = {}
                    for w in palabras:
                        idx_by_top.setdefault(round(w["top"]), []).append(w)
                    texto_pagina = " ".join(w["text"] for w in palabras)
                    if titulo_grafico.replace(" ", "") not in texto_pagina.replace(" ", ""):
                        continue

                    # ubicar el top del titulo (primera palabra del titulo)
                    primera_palabra_titulo = titulo_grafico.split()[0]
                    candidatos_titulo = [w for w in palabras if w["text"].startswith(primera_palabra_titulo[:4])]
                    if not candidatos_titulo:
                        continue
                    top_titulo = min(w["top"] for w in candidatos_titulo)

                    en_ventana = [w for w in palabras
                                  if top_titulo <= w["top"] <= top_titulo + ventana_vertical
                                  and patron.match(w["text"])]
                    if len(en_ventana) < 2:
                        continue

                    # agrupar por columna x0 (redondeado) para detectar el eje
                    from collections import Counter
                    cont_x0 = Counter(round(w["x0"] / 3) * 3 for w in en_ventana)
                    x0_eje = cont_x0.most_common(1)[0][0] if cont_x0 else None
                    n_en_eje = cont_x0.most_common(1)[0][1] if cont_x0 else 0

                    datos = [w for w in en_ventana if round(w["x0"] / 3) * 3 != x0_eje] if n_en_eje >= 3 else en_ventana
                    if not datos:
                        continue
                    datos.sort(key=lambda w: w["x0"])
                    valor = datos[-1]["text"].rstrip(sufijo)
                    return valor.replace(".", ",")
        except Exception:
            return None
        return None

    async def run_standalone(self):
        """python -m agentes.<modulo>: corre descargar+inspeccionar+extraer
        para todos los fondos de esta administradora usando el listado
        maestro, e imprime el resultado (no escribe el registro global,
        eso lo hace master.py)."""
        from openpyxl import load_workbook

        wb = load_workbook(FONDOS_FILE)
        ws = wb.active
        fondos = []
        for row in ws.iter_rows(min_row=6, values_only=True):
            if len(row) < 4:
                continue
            _, administradora, nombre, link = row[0], row[1], row[2], row[3]
            if administradora and nombre and link and str(administradora).strip() == self.administradora:
                fondos.append({
                    "administradora": str(administradora).strip(),
                    "nombre": str(nombre).strip(),
                    "link": str(link).strip(),
                })

        print(f"=== Agente {self.administradora} — {len(fondos)} fondo(s) ===\n")

        for fondo in fondos:
            print(f"[{fondo['nombre']}]")
            pdf_path = archivo_mas_reciente(self.administradora, fondo["nombre"])
            if pdf_path is None:
                print("  -> no hay PDF descargado (correr con browser para descargar)")
                continue
            print(f"  archivo: {pdf_path.name}")
            info = self.inspeccionar(pdf_path)
            print(f"  inspeccionar(): {info}")
            datos = self.extraer(pdf_path)
            resumen = {k: v for k, v in datos.items() if v not in (None, "", {})}
            print(f"  extraer(): {resumen}")
            print()
