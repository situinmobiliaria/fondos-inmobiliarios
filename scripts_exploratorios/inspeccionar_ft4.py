"""Intercepta requests al hacer click en una fila de Ficha Mensual en Frontal Trust."""
import asyncio
from playwright.async_api import async_playwright

PARENT_URL = "https://www.frontaltrust.cl/informacion-frontal-trust-agf-s-a-y-fondos-publicos/?seccion=buscador-de-documentos&variable=134"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()

        reqs = []
        def on_req(r):
            reqs.append(("REQ", r.method, r.url))
        def on_res(r):
            if r.status != 304:
                reqs.append(("RES", r.status, r.url, r.headers.get("content-type","")[:50]))

        page.on("request", on_req)
        page.on("response", on_res)

        print("Cargando página...")
        try:
            await page.goto(PARENT_URL, wait_until="networkidle", timeout=45_000)
        except Exception:
            await page.goto(PARENT_URL, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(3)

        # Click en BUSCADOR DE DOCUMENTOS
        for a in await page.query_selector_all("a"):
            t = (await a.inner_text()).strip()
            if "buscador" in t.lower():
                await a.click()
                await asyncio.sleep(4)
                print(f"Tab clickeado: '{t}'")
                break

        # Encontrar frame de documentos
        target_frame = None
        for frame in page.frames:
            if "viewdashboarddocumento" in frame.url:
                target_frame = frame
                print(f"Frame: {frame.url}")
                break

        if not target_frame:
            print("Sin frame")
            await browser.close()
            return

        await asyncio.sleep(2)

        # Encontrar la primera fila con "Ficha Mensual"
        rows = await target_frame.query_selector_all("tr")
        ficha_row = None
        for row in rows:
            txt = (await row.inner_text()).lower()
            if "ficha" in txt and "mensual" in txt:
                print(f"Fila encontrada: {(await row.inner_text()).strip().replace(chr(10),' | ')[:120]}")
                ficha_row = row
                break

        if not ficha_row:
            print("Sin fila Ficha Mensual")
            await browser.close()
            return

        # Limpiar log antes del click
        reqs.clear()
        print("\nHaciendo click en fila... (monitoreando requests)")

        # Capturar el click en el contexto completo
        download_captured = None

        async def handle_download(download):
            nonlocal download_captured
            download_captured = download
            print(f"DESCARGA CAPTURADA: {download.suggested_filename} - URL: {download.url}")

        page.on("download", handle_download)
        ctx.on("page", lambda p: p.on("download", handle_download))

        await ficha_row.click()
        await asyncio.sleep(5)

        print("\n--- Requests generadas por el click ---")
        for r in reqs:
            print(f"  {r}")

        if download_captured:
            print(f"\nDescarga: {download_captured.suggested_filename}")
            await download_captured.save_as(f"test_ft_{download_captured.suggested_filename}")
        else:
            print("\nSin descarga automática. Buscando botón de descarga...")
            # Ver qué elementos cambiaron/aparecieron
            for el in await target_frame.query_selector_all("a, button, input[type='button']"):
                try:
                    t = (await el.inner_text()).strip()
                    h = await el.get_attribute("href") or await el.get_attribute("onclick") or ""
                    if t and ("descargar" in t.lower() or "download" in t.lower() or ".pdf" in h.lower()):
                        print(f"  Botón descarga: '{t}' -> {h[:100]}")
                except Exception:
                    pass

        print("\nEsperando 30s para inspección visual...")
        await asyncio.sleep(30)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
