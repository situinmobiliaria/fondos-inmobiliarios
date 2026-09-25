"""
Scraper especializado para Frontal Trust y Santander.
Frontal Trust: cada fondo tiene variable=ID en la URL de documentos.
Santander: necesita inspección manual del DOM para encontrar el PDF.
"""

import asyncio
import re
import requests as req
from datetime import datetime
from pathlib import Path

import openpyxl
from scraper_fondos import (
    OUTPUT_DIR, REGISTRO_FILE, BLACKLIST_DOC, KEYWORDS_FICHA,
    carpeta_fondo, sanitize, extraer_rentabilidades, registrar_descarga, inicializar_registro
)

# ── Frontal Trust: mapeo fondo -> variable ID ────────────────────────────────
# URL base: /informacion-frontal-trust-agf-s-a-y-fondos-publicos/?seccion=buscador-de-documentos&variable=XXX
FT_BASE = "https://www.frontaltrust.cl/informacion-frontal-trust-agf-s-a-y-fondos-publicos/"
FT_DASHBOARD = "https://dashboard.frontaltrust.cl/viewdashboarddocumento.aspx?{variable}"

# variable_id del iframe (del URL de Desempeño en la página principal)
# vehiculo_id = value del <select name="vehiculo"> dentro del iframe
FRONTAL_TRUST_IDS = {
    # nombre_excel: (variable_id, vehiculo_id)
    "Fundamenta Plaza Egaña":       (134, 413),
    "Fundamenta Plaza Eg":          (134, 413),
    "San Bernardo":                 (183, 1495),
    "Desarrollos Industriales I":   (203, 2059),
    "Desarrollo Inmobiliario XIII": (138, 407),
    "Desarrollo Inmobiliario XV":   (173, 1053),
    "Desarrollo Inmobiliario XVI":  (177, 1991),
    "Desarrollo Inmobiliario XX":   (204, 2061),
}

# Prioridad de términos: primero los más relevantes
FICHA_PRIORITY = ["factsheet", "ficha del fondo", "informacion del fondo",
                  "información del fondo", "ficha comercial", "folleto", "informativo"]


def get_ft_ids(nombre_fondo: str) -> tuple[int, int] | None:
    """Retorna (variable_id, vehiculo_id) para el fondo dado."""
    nombre_low = nombre_fondo.lower().strip()
    # Exact match first
    for key, ids in FRONTAL_TRUST_IDS.items():
        if key.lower().strip() == nombre_low:
            return ids
    # Substring match — sort by key length desc to avoid partial matches (e.g. "XV" in "XVI")
    for key, ids in sorted(FRONTAL_TRUST_IDS.items(), key=lambda x: len(x[0]), reverse=True):
        if key.lower() in nombre_low or nombre_low in key.lower():
            return ids
    # Word-based fuzzy match
    for key, ids in FRONTAL_TRUST_IDS.items():
        palabras = [w for w in key.lower().split() if len(w) > 3]
        if all(p in nombre_low for p in palabras):
            return ids
    return None


async def scrape_frontal_trust(browser, fondo: dict, wb):
    nombre = fondo["nombre"]
    administradora = fondo["administradora"]
    folder = carpeta_fondo(administradora, nombre)
    log = f"  [Frontal Trust] {nombre}"

    ids = get_ft_ids(nombre)
    if not ids:
        print(f"{log} -> no se encontro ID para este fondo")
        registrar_descarga(wb, fondo, None, {}, "sin ID")
        return

    variable_id, vehiculo_id = ids
    # Navegar directamente al iframe del dashboard
    iframe_url = f"https://dashboard.frontaltrust.cl/viewdashboarddocumento.aspx?{variable_id}"
    print(f"{log} -> iframe dashboard (variable={variable_id}, vehiculo={vehiculo_id})")

    ctx = await browser.new_context(
        accept_downloads=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = await ctx.new_page()
    filepath = None
    estado = "sin documento"

    # URL de la página padre que carga el iframe
    parent_url = (
        f"https://www.frontaltrust.cl/informacion-frontal-trust-agf-s-a-y-fondos-publicos/"
        f"?seccion=buscador-de-documentos&variable={variable_id}"
    )

    try:
        try:
            await page.goto(parent_url, wait_until="networkidle", timeout=45_000)
        except Exception:
            await page.goto(parent_url, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(6)
        await asyncio.sleep(3)

        # Hacer click en el tab "BUSCADOR DE DOCUMENTOS" para cargar el iframe correcto
        for a in await page.query_selector_all("a"):
            try:
                t = (await a.inner_text()).strip()
                h = await a.get_attribute("href") or ""
                if "buscador" in t.lower() or "documento" in t.lower():
                    await a.click()
                    await asyncio.sleep(4)
                    print(f"{log} -> click en tab: '{t}' ({h})")
                    break
            except Exception:
                continue

        date_str = datetime.now().strftime("%Y%m%d")
        base = f"{date_str}_{sanitize(nombre)}"

        # Buscar el frame del dashboard (ahora debe ser viewdashboarddocumento)
        target_frame = None
        for frame in page.frames:
            if "dashboard.frontaltrust.cl" in frame.url:
                target_frame = frame
                print(f"{log} -> frame: {frame.url[:80]}")
                if "documento" in frame.url:
                    break  # preferir el frame de documentos

        if target_frame:
            print(f"{log} -> frame encontrado: {target_frame.url}")
            await asyncio.sleep(3)

            # Filtrar por tipo "Ficha Mensual" dentro del frame
            try:
                await target_frame.select_option(
                    "select[name='vDOCUMENTOTIPOID']",
                    label="Ficha Mensual",
                    timeout=8_000
                )
                # Hacer submit del formulario de filtros
                submit_btn = await target_frame.query_selector("input[type='submit'], button[type='submit']")
                if submit_btn:
                    await submit_btn.click()
                else:
                    await target_frame.evaluate("document.querySelector('form').submit()")
                await asyncio.sleep(4)
                print(f"{log} -> filtrado por Ficha Mensual")
            except Exception as e:
                print(f"{log} -> sin filtro tipo doc ({e.__class__.__name__})")

            # Buscar la primera fila de "Ficha Mensual" en la tabla
            ficha_row = None
            rows = await target_frame.query_selector_all("tr")
            for row in rows:
                try:
                    txt = (await row.inner_text()).lower()
                    if "ficha" in txt and "mensual" in txt:
                        ficha_row = row
                        break
                except Exception:
                    continue

            if ficha_row:
                print(f"{log} -> fila Ficha Mensual encontrada, buscando icono de descarga...")
                # El boton de descarga es un <img class="fas fa-download" id="vDOWNLOAD_000X">
                download_icon = await ficha_row.query_selector(
                    "img[class*='fa-download'], img[id*='vDOWNLOAD'], [id*='vDOWNLOAD']"
                )
                if not download_icon:
                    # Fallback: primer icono fa-download en el frame
                    download_icon = await target_frame.query_selector(
                        "img[class*='fa-download'], img[id*='vDOWNLOAD']"
                    )
                if download_icon:
                    icon_id = await download_icon.get_attribute("id") or "?"
                    print(f"{log} -> icono encontrado: {icon_id}, haciendo click...")
                    try:
                        async with ctx.expect_page(timeout=15_000) as np_info:
                            await download_icon.click()
                        np = await np_info.value
                        await np.wait_for_load_state("load", timeout=20_000)
                        doc_url = np.url
                        await np.close()
                        print(f"{log} -> URL de descarga: {doc_url[:100]}")
                        if doc_url and ".pdf" in doc_url.lower():
                            r = req.get(doc_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, stream=True)
                            ct = r.headers.get("content-type", "")
                            if "pdf" in ct or ".pdf" in doc_url.lower():
                                filepath = folder / f"{base}.pdf"
                                with open(filepath, "wb") as f:
                                    for chunk in r.iter_content(65536):
                                        f.write(chunk)
                                estado = "descargado"
                        else:
                            estado = "click icono sin pdf"
                    except Exception as e:
                        print(f"{log} -> error captura nueva pagina: {e.__class__.__name__}")
                        # Fallback: capturar descarga directa
                        try:
                            async with page.expect_download(timeout=12_000) as dl_info:
                                await download_icon.click()
                            dl = await dl_info.value
                            ext = Path(dl.suggested_filename).suffix or ".pdf"
                            filepath = folder / f"{base}{ext}"
                            await dl.save_as(filepath)
                            estado = "descargado"
                        except Exception:
                            estado = "click icono sin descarga"
                else:
                    print(f"{log} -> no se encontro icono de descarga en fila")
                    estado = "sin icono descarga"
            else:
                print(f"{log} -> no se encontro fila de Ficha Mensual")
                # Mostrar las primeras filas disponibles
                all_rows = await target_frame.query_selector_all("tr")
                for row in all_rows[:5]:
                    try:
                        t = (await row.inner_text()).strip().replace("\n", " | ")
                        if t and len(t) > 5:
                            print(f"    fila: {t[:120]}")
                    except Exception:
                        pass
                estado = "sin Ficha Mensual en FT"
        else:
            print(f"{log} -> frame no encontrado. Frames: {[f.url[:60] for f in page.frames]}")
            estado = "sin frame FT"

    except Exception as e:
        print(f"{log} -> ERROR: {e}")
        estado = f"error: {str(e)[:80]}"
    finally:
        await ctx.close()

    rentabilidades = {}
    if filepath and filepath.exists() and filepath.suffix.lower() == ".pdf":
        rentabilidades = extraer_rentabilidades(filepath)

    registrar_descarga(wb, fondo, filepath, rentabilidades, estado)
    if filepath:
        print(f"{log} -> guardado: {filepath.name}")


async def scrape_santander(browser, fondo: dict, wb):
    """Santander: intenta varias estrategias para encontrar el PDF."""
    nombre = fondo["nombre"]
    link = fondo["link"]
    folder = carpeta_fondo(fondo["administradora"], nombre)
    log = f"  [Santander] {nombre}"

    ctx = await browser.new_context(
        accept_downloads=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = await ctx.new_page()
    filepath = None
    estado = "sin documento"

    try:
        try:
            await page.goto(link, wait_until="networkidle", timeout=40_000)
        except Exception:
            await page.goto(link, wait_until="domcontentloaded", timeout=40_000)
            await asyncio.sleep(6)
        await asyncio.sleep(3)

        # Buscar iframes con PDFs embebidos
        iframes = await page.query_selector_all("iframe")
        for iframe in iframes:
            src = await iframe.get_attribute("src") or ""
            if src.endswith(".pdf") or "pdf" in src.lower():
                print(f"{log} -> PDF en iframe: {src}")
                r = req.get(src, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, stream=True)
                date_str = datetime.now().strftime("%Y%m%d")
                filepath = folder / f"{date_str}_{sanitize(nombre)}.pdf"
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                estado = "descargado (iframe)"
                break

        # Buscar cualquier link a PDF
        if not filepath:
            for a in await page.query_selector_all("a"):
                try:
                    h = await a.get_attribute("href") or ""
                    t = (await a.inner_text()).strip()
                    if h.endswith(".pdf") and not any(bl in t.lower() for bl in BLACKLIST_DOC):
                        print(f"{log} -> PDF link: {t} -> {h}")
                        if not h.startswith("http"):
                            h = "https://www.santanderassetmanagement.cl" + h
                        r = req.get(h, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, stream=True)
                        date_str = datetime.now().strftime("%Y%m%d")
                        filepath = folder / f"{date_str}_{sanitize(nombre)}.pdf"
                        with open(filepath, "wb") as f:
                            for chunk in r.iter_content(65536):
                                f.write(chunk)
                        estado = "descargado"
                        break
                except Exception:
                    continue

        if not filepath:
            # Obtener todo el contenido de la página y buscar URLs de PDF
            html = await page.content()
            pdf_urls = re.findall(r'https?://[^\s"\'<>]+\.pdf', html)
            if pdf_urls:
                print(f"{log} -> PDFs encontrados en HTML: {pdf_urls[:3]}")
                r = req.get(pdf_urls[0], headers={"User-Agent": "Mozilla/5.0"}, timeout=30, stream=True)
                date_str = datetime.now().strftime("%Y%m%d")
                filepath = folder / f"{date_str}_{sanitize(nombre)}.pdf"
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                estado = "descargado (html scan)"
            else:
                print(f"{log} -> no se encontro PDF. Links disponibles:")
                for a in await page.query_selector_all("a"):
                    try:
                        t = (await a.inner_text()).strip()
                        h = await a.get_attribute("href") or ""
                        if t and h:
                            print(f"    '{t}' -> {h[:100]}")
                    except Exception:
                        pass
                estado = "no encontrado (Santander)"

    except Exception as e:
        print(f"{log} -> ERROR: {e}")
        estado = f"error: {str(e)[:80]}"
    finally:
        await ctx.close()

    rentabilidades = {}
    if filepath and filepath.exists() and filepath.suffix.lower() == ".pdf":
        rentabilidades = extraer_rentabilidades(filepath)

    registrar_descarga(wb, fondo, filepath, rentabilidades, estado)
    if filepath:
        print(f"{log} -> guardado: {filepath.name}")


async def main():
    from playwright.async_api import async_playwright
    from scraper_fondos import leer_fondos

    print("=" * 60)
    print("  Scraper Especiales: Frontal Trust + Santander")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    fondos = leer_fondos()
    frontal = [f for f in fondos if f["administradora"] == "Frontal Trust"]
    santander = [f for f in fondos if "Santander" in f["administradora"]]

    wb = inicializar_registro()
    OUTPUT_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        print(f"\n--- Frontal Trust ({len(frontal)} fondos) ---")
        for fondo in frontal:
            print(f"\nProcesando: {fondo['nombre']}")
            await scrape_frontal_trust(browser, fondo, wb)
            await asyncio.sleep(2)

        print(f"\n--- Santander ({len(santander)} fondos) ---")
        for fondo in santander:
            print(f"\nProcesando: {fondo['nombre']}")
            await scrape_santander(browser, fondo, wb)
            await asyncio.sleep(2)

        await browser.close()

    print("\n" + "=" * 60)
    print("  Proceso completo.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
