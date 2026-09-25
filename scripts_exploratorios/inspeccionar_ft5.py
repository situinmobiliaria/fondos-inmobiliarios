"""
Extrae IDs de documentos desde el frame GeneXus de Frontal Trust
y prueba patrones de URL de descarga.
"""
import asyncio
import re
import requests as req
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

        # Interceptar TODAS las requests para encontrar patrones de descarga
        all_reqs = []
        page.on("request", lambda r: all_reqs.append((r.method, r.url)))

        try:
            await page.goto(PARENT_URL, wait_until="networkidle", timeout=45_000)
        except Exception:
            await page.goto(PARENT_URL, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(3)

        for a in await page.query_selector_all("a"):
            t = (await a.inner_text()).strip()
            if "buscador" in t.lower():
                await a.click()
                await asyncio.sleep(4)
                break

        target_frame = None
        for frame in page.frames:
            if "viewdashboarddocumento" in frame.url:
                target_frame = frame
                break

        if not target_frame:
            print("Sin frame")
            await browser.close()
            return

        await asyncio.sleep(2)

        # Obtener HTML completo del frame y extraer IDs
        html = await target_frame.content()

        # Buscar IDs de documentos (patrón: ReadonlyAttribute con número de 5-6 dígitos)
        ids = re.findall(r'class="[^"]*ReadonlyAttribute[^"]*"[^>]*>\s*(\d{5,6})\s*<', html)
        nombres = re.findall(r'class="[^"]*ReadonlyAttribute[^"]*"[^>]*>([A-Z0-9]{4,}_[^\s<]{5,})\s*<', html)

        print(f"\n--- IDs encontrados en el frame ---")
        print(f"IDs: {ids[:10]}")
        print(f"Nombres: {nombres[:10]}")

        # Buscar el ID del primer "Ficha Mensual" (el segundo bloque de IDs)
        # El primer bloque es Estados Financieros (ID: 150430), el segundo es Ficha Mensual (ID: 147784)
        # Intentar construir URLs de descarga
        if ids:
            doc_id = ids[1] if len(ids) > 1 else ids[0]  # segundo ID = Ficha Mensual
            print(f"\nID de Ficha Mensual: {doc_id}")

            # Nombre del documento
            doc_nombre = nombres[1] if len(nombres) > 1 else (nombres[0] if nombres else "")
            print(f"Nombre del documento: {doc_nombre}")

            # Intentar diferentes patrones de URL de GeneXus
            base = "https://dashboard.frontaltrust.cl"
            patterns = [
                f"{base}/GXBLOBUpload.aspx?tbl=DOCUMENTOMOVIMIENTO&fld=DocumentoFile&val={doc_id}&ext=pdf&type=application/pdf",
                f"{base}/GXBLOBUpload.aspx?{doc_id}",
                f"{base}/apiv1/gxmedia/DOCUMENTOMOVIMIENTO/DocumentoFile/{doc_id}",
                f"{base}/download?id={doc_id}",
                f"{base}/documento/{doc_id}.pdf",
                f"{base}/GXBLOBUpload.aspx?tbl=DOCUMENTOMOVIMIENTO&fld=DocumentoFile&val={doc_id}",
            ]

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": PARENT_URL,
            }

            print("\n--- Probando URLs de descarga ---")
            for url in patterns:
                try:
                    r = req.head(url, headers=headers, timeout=10, allow_redirects=True)
                    ct = r.headers.get("content-type", "")
                    cl = r.headers.get("content-length", "?")
                    print(f"  {r.status_code} [{ct[:40]}] {cl}B -> {url[:80]}")
                except Exception as e:
                    print(f"  ERROR: {e.__class__.__name__} -> {url[:80]}")

        # Buscar onclick handlers en celdas de la tabla
        print("\n--- onclick en celdas ---")
        tds = await target_frame.query_selector_all("td, tr")
        for el in tds[:30]:
            try:
                oc = await el.get_attribute("onclick") or ""
                gx = await el.get_attribute("data-gx-action") or ""
                t = (await el.inner_text()).strip()[:50]
                if oc or gx:
                    print(f"  td '{t}': onclick={oc[:100]} gx={gx[:50]}")
            except Exception:
                pass

        # Buscar el GXState (contiene el estado del formulario)
        gx_state = await target_frame.query_selector("input[name='GXState']")
        if gx_state:
            val = await gx_state.get_attribute("value") or ""
            print(f"\nGXState: {val[:200]}")

        # Buscar el GridContainerDataV (datos de la grilla)
        grid_data = await target_frame.query_selector("input[name='GridContainerDataV']")
        if grid_data:
            val = await grid_data.get_attribute("value") or ""
            print(f"\nGridContainerDataV: {val[:300]}")

        print("\nEsperando 30s para inspección visual...")
        await asyncio.sleep(30)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
