"""
Scraper de Fondos Inmobiliarios
Descarga fichas / factsheets y registra rentabilidad histórica.
"""

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
import pdfplumber
from playwright.async_api import async_playwright

# ── Configuración ────────────────────────────────────────────────────────────
FONDOS_FILE = "20260507 Fondos Inmobiliarios.xlsx"
OUTPUT_DIR = Path("Fondos Descargados")
REGISTRO_FILE = "registro_rentabilidad.xlsx"

# Palabras clave para identificar el documento correcto
KEYWORDS_FICHA = [
    "información del fondo",
    "informacion del fondo",
    "factsheet",
    "ficha del fondo",
    "ficha de fondo",
    "ficha comercial",
    "información de fondo",
    "informacion de fondo",
    "fact sheet",
]

# Términos que EXCLUYEN un documento (reglamentos, estados financieros, etc.)
BLACKLIST_DOC = [
    "reglamento",
    "estados financieros",
    "estado financiero",
    "auditores",
    "auditor",
    "auditada",
    "fecu",
    "acta ",
    "aviso ",
    "citacion",
    "citación",
    "deposito",
    "depósito",
    "valor cuota",
    "memoria anual",
    "hecho esencial",
    "política",
    "politica",
]

# Patrones regex para extraer rentabilidades del PDF
RENT_LABELS = [
    "1 mes", "3 meses", "6 meses",
    "ytd", "año", "1 año", "3 años", "5 años",
    "12 meses", "24 meses", "36 meses",
    "inception",
]

# ── Utilidades ───────────────────────────────────────────────────────────────

def sanitize(name: str) -> str:
    """Elimina caracteres inválidos para nombres de carpeta/archivo."""
    return re.sub(r'[<>:"/\\|?*\n\r\t]', '', name).strip()


def leer_fondos() -> list[dict]:
    wb = openpyxl.load_workbook(FONDOS_FILE)
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
    return fondos


def carpeta_fondo(administradora: str, nombre: str) -> Path:
    folder = OUTPUT_DIR / sanitize(administradora) / sanitize(nombre)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def es_keyword(text: str) -> bool:
    t = text.lower().strip()
    if any(bl in t for bl in BLACKLIST_DOC):
        return False
    return any(kw in t for kw in KEYWORDS_FICHA)


def palabras_clave_fondo(nombre: str) -> list[str]:
    """Extrae palabras significativas del nombre del fondo para buscar en la página."""
    stopwords = {"de", "del", "la", "el", "los", "las", "y", "e", "fondo", "fi", "i", "ii", "iii", "iv"}
    return [w.lower() for w in nombre.split() if w.lower() not in stopwords and len(w) > 2]


async def navegar_a_fondo_en_pagina(page, nombre_fondo: str) -> bool:
    """
    Busca el nombre del fondo como accordion/tab/heading en la página y lo clickea.
    Retorna True si encontró y clickeó algo, expandiendo la sección del fondo.
    """
    palabras = palabras_clave_fondo(nombre_fondo)
    if not palabras:
        return False

    selectores = [
        "button", "summary", "[role='tab']", "[role='button']",
        "h2", "h3", "h4", "h5",
        ".accordion-header", ".accordion-button", ".panel-heading",
        ".fund-name", ".fondo-nombre", "li.fondo", "li.fund",
    ]

    for selector in selectores:
        try:
            elementos = await page.query_selector_all(selector)
            for el in elementos:
                try:
                    texto = (await el.inner_text()).strip().lower()
                    # Match si al menos 2 palabras clave del fondo están en el texto
                    matches = sum(1 for p in palabras if p in texto)
                    if matches >= min(2, len(palabras)):
                        await el.scroll_into_view_if_needed()
                        await el.click()
                        await asyncio.sleep(2)
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def extraer_rentabilidades(pdf_path: Path) -> dict:
    """Extrae rentabilidades del PDF usando pdfplumber."""
    resultados = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            texto = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            ).lower()

        # Buscar porcentajes junto a etiquetas de período
        for label in RENT_LABELS:
            patron = rf"{re.escape(label)}[:\s]*(\-?\d+[.,]\d+)\s*%"
            m = re.search(patron, texto, re.IGNORECASE)
            if m:
                resultados[label] = m.group(1).replace(",", ".")

        # Busca también tablas de números con %
        patron_generico = r"(\-?\d{1,3}[.,]\d{1,4})\s*%"
        porcentajes = re.findall(patron_generico, texto)
        if porcentajes and not resultados:
            resultados["valores_encontrados"] = ", ".join(porcentajes[:10])

    except Exception as e:
        resultados["error_extraccion"] = str(e)
    return resultados


# ── Registro Excel ────────────────────────────────────────────────────────────

HEADERS = [
    "Fecha Descarga", "Administradora", "Fondo",
    "Archivo", "Ruta",
    "Rent. 1M", "Rent. 3M", "Rent. 6M",
    "Rent. YTD", "Rent. 1A", "Rent. 3A", "Rent. 5A",
    "Otros valores %", "Estado",
]

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def inicializar_registro() -> openpyxl.Workbook:
    if Path(REGISTRO_FILE).exists():
        return openpyxl.load_workbook(REGISTRO_FILE)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Registro"
    ws.append(HEADERS)
    for col, header in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 35
    ws.column_dimensions["E"].width = 55
    wb.save(REGISTRO_FILE)
    return wb


def registrar_descarga(wb, fondo: dict, filepath: Path | None,
                        rentabilidades: dict, estado: str):
    ws = wb["Registro"]
    rents = rentabilidades or {}
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        fondo["administradora"],
        fondo["nombre"],
        filepath.name if filepath else "",
        str(filepath) if filepath else "",
        rents.get("1 mes") or rents.get("1mes", ""),
        rents.get("3 meses") or rents.get("3meses", ""),
        rents.get("6 meses") or rents.get("6meses", ""),
        rents.get("ytd", ""),
        rents.get("1 año") or rents.get("1 ano") or rents.get("12 meses", ""),
        rents.get("3 años") or rents.get("3 anos") or rents.get("36 meses", ""),
        rents.get("5 años") or rents.get("5 anos", ""),
        rents.get("valores_encontrados", ""),
        estado,
    ]
    ws.append(row)
    wb.save(REGISTRO_FILE)


# ── Scraper principal ────────────────────────────────────────────────────────

async def descargar_archivo(page, href: str, folder: Path,
                             fondo_nombre: str) -> Path | None:
    """Descarga un archivo desde href o click, devuelve la ruta guardada."""
    date_str = datetime.now().strftime("%Y%m%d")
    base_name = sanitize(fondo_nombre)

    # Si el href apunta directamente a un archivo descargable
    if href and re.search(r"\.(pdf|xlsx|xls|doc|docx)(\?|$)", href, re.IGNORECASE):
        try:
            import urllib.request
            ext = re.search(r"\.(pdf|xlsx|xls|doc|docx)", href, re.IGNORECASE).group(1)
            filename = folder / f"{date_str}_{base_name}.{ext}"
            urllib.request.urlretrieve(href, filename)
            return filename
        except Exception:
            pass  # fallback a click

    # Intenta click y captura el download
    try:
        async with page.expect_download(timeout=20_000) as dl_info:
            await page.goto(href, wait_until="networkidle", timeout=30_000)
        download = await dl_info.value
        ext = Path(download.suggested_filename).suffix or ".pdf"
        filepath = folder / f"{date_str}_{base_name}{ext}"
        await download.save_as(filepath)
        return filepath
    except Exception:
        return None


async def scrape_fondo(browser, fondo: dict, wb) -> str:
    """Procesa un fondo: navega, busca el documento, lo descarga."""
    administradora = fondo["administradora"]
    nombre = fondo["nombre"]
    link = fondo["link"]
    folder = carpeta_fondo(administradora, nombre)

    log = f"  [{administradora}] {nombre}"

    context = await browser.new_context(
        accept_downloads=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()

    filepath = None
    estado = "sin documento"

    try:
        try:
            await page.goto(link, wait_until="networkidle", timeout=40_000)
        except Exception:
            await page.goto(link, wait_until="domcontentloaded", timeout=40_000)
            await asyncio.sleep(5)
        await asyncio.sleep(2)

        # Intentar navegar a la sección del fondo dentro de la página
        navego = await navegar_a_fondo_en_pagina(page, nombre)
        if navego:
            print(f"{log} -> navegó a sección del fondo en la página")

        async def buscar_candidatos(anchors_list):
            """Filtra anchors por keyword (con blacklist) y devuelve candidatos."""
            candidatos = []
            for anchor in anchors_list:
                try:
                    texto = (await anchor.inner_text()).strip()
                    href = await anchor.get_attribute("href") or ""
                    if es_keyword(texto):
                        candidatos.append((texto, href, anchor))
                except Exception:
                    continue
            return candidatos

        # 1. Buscar por texto (con blacklist aplicada)
        anchors = await page.query_selector_all("a")
        candidatos = await buscar_candidatos(anchors)

        # 2. Si no hay, buscar por href que contenga keywords
        if not candidatos:
            for anchor in anchors:
                try:
                    href = (await anchor.get_attribute("href") or "").lower()
                    texto = (await anchor.inner_text()).strip()
                    if any(kw.replace(" ", "") in href for kw in KEYWORDS_FICHA):
                        if not any(bl in texto.lower() for bl in BLACKLIST_DOC):
                            candidatos.append((texto, href, anchor))
                except Exception:
                    continue

        # 3. Si tampoco, buscar PDFs cercanos a la sección del fondo (si se navegó)
        if not candidatos and navego:
            for anchor in anchors:
                try:
                    href = await anchor.get_attribute("href") or ""
                    texto = (await anchor.inner_text()).strip()
                    if href.lower().endswith(".pdf") and not any(bl in texto.lower() for bl in BLACKLIST_DOC):
                        candidatos.append((texto, href, anchor))
                except Exception:
                    continue

        if candidatos:
            texto_doc, href_doc, anchor_doc = candidatos[0]
            print(f"{log} -> encontrado: '{texto_doc}'")

            from urllib.parse import urljoin

            if href_doc and not href_doc.startswith("http"):
                href_doc = urljoin(link, href_doc)

            date_str = datetime.now().strftime("%Y%m%d")
            base = f"{date_str}_{sanitize(nombre)}"

            # 1) Si el href apunta directamente a un PDF/Excel, descarga con requests
            if href_doc and re.search(r"\.(pdf|xlsx|xls)(\?.*)?$", href_doc, re.IGNORECASE):
                try:
                    import requests as req
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    r = req.get(href_doc, headers=headers, timeout=30, stream=True)
                    r.raise_for_status()
                    ext = re.search(r"\.(pdf|xlsx|xls)", href_doc, re.IGNORECASE).group(1)
                    filepath = folder / f"{base}.{ext}"
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(65536):
                            f.write(chunk)
                    estado = "descargado"
                except Exception as e_req:
                    print(f"{log} -> fallo descarga directa: {e_req}")

            # 2) Click + captura de nueva pestaña (PDF abierto en nueva tab)
            if not filepath:
                try:
                    async with context.expect_page(timeout=12_000) as new_page_info:
                        await anchor_doc.click()
                    new_page = await new_page_info.value
                    await new_page.wait_for_load_state("load", timeout=20_000)
                    new_url = new_page.url
                    await new_page.close()
                    if re.search(r"\.(pdf|xlsx|xls)(\?.*)?$", new_url, re.IGNORECASE):
                        import requests as req
                        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                        r = req.get(new_url, headers=headers, timeout=30, stream=True)
                        r.raise_for_status()
                        ext = re.search(r"\.(pdf|xlsx|xls)", new_url, re.IGNORECASE).group(1)
                        filepath = folder / f"{base}.{ext}"
                        with open(filepath, "wb") as f:
                            for chunk in r.iter_content(65536):
                                f.write(chunk)
                        estado = "descargado (nueva tab)"
                    elif new_url and new_url != link:
                        # La URL es un visor de PDF — descarga directa igual
                        import requests as req
                        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                        r = req.get(new_url, headers=headers, timeout=30, stream=True)
                        ct = r.headers.get("content-type", "")
                        if "pdf" in ct or "octet" in ct:
                            filepath = folder / f"{base}.pdf"
                            with open(filepath, "wb") as f:
                                for chunk in r.iter_content(65536):
                                    f.write(chunk)
                            estado = "descargado (visor)"
                except Exception:
                    pass

            # 3) Click + expect_download (descarga forzada por el servidor)
            if not filepath:
                try:
                    async with page.expect_download(timeout=15_000) as dl_info:
                        await anchor_doc.click()
                    download = await dl_info.value
                    ext = Path(download.suggested_filename).suffix or ".pdf"
                    filepath = folder / f"{base}{ext}"
                    await download.save_as(filepath)
                    estado = "descargado"
                except Exception:
                    pass

            # 4) Último recurso: navegar al href y descargar el contenido
            if not filepath and href_doc:
                try:
                    import requests as req
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    r = req.get(href_doc, headers=headers, timeout=30, stream=True)
                    ct = r.headers.get("content-type", "")
                    if "pdf" in ct or "octet" in ct or "excel" in ct:
                        ext = "xlsx" if "excel" in ct else "pdf"
                        filepath = folder / f"{base}.{ext}"
                        with open(filepath, "wb") as f:
                            for chunk in r.iter_content(65536):
                                f.write(chunk)
                        estado = "descargado (contenido)"
                except Exception:
                    pass

            if not filepath:
                estado = "encontrado sin descarga"

        else:
            print(f"{log} -> no se encontro documento de ficha")
            estado = "no encontrado"

    except Exception as e:
        print(f"{log} -> ERROR: {e}")
        estado = f"error: {str(e)[:80]}"

    finally:
        await context.close()

    # Extraer rentabilidades si hay PDF descargado
    rentabilidades = {}
    if filepath and filepath.exists() and filepath.suffix.lower() == ".pdf":
        rentabilidades = extraer_rentabilidades(filepath)

    registrar_descarga(wb, fondo, filepath, rentabilidades, estado)

    if filepath:
        print(f"{log} -> guardado en {filepath.name} | rents: {rentabilidades or 'pendiente extraccion'}")

    return estado


async def main():
    print("=" * 60)
    print("  Scraper Fondos Inmobiliarios")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    fondos = leer_fondos()
    print(f"\nFondos a procesar: {len(fondos)}\n")

    wb = inicializar_registro()
    OUTPUT_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=True para producción

        for i, fondo in enumerate(fondos, 1):
            print(f"\n[{i}/{len(fondos)}] Procesando: {fondo['nombre']}")
            await scrape_fondo(browser, fondo, wb)
            await asyncio.sleep(1.5)  # pausa entre requests

        await browser.close()

    print("\n" + "=" * 60)
    print(f"  Proceso completo. Registro guardado en: {REGISTRO_FILE}")
    print(f"  Archivos en: {OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
