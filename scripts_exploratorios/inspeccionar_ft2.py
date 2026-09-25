"""
Captura las llamadas de red de Frontal Trust para encontrar el endpoint de documentos.
"""
import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://www.frontaltrust.cl/informacion-frontal-trust-agf-s-a-y-fondos-publicos/?seccion=buscador-de-documentos&variable=134"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()

        # Capturar todas las requests de red
        requests_log = []
        def on_request(req):
            if any(x in req.url for x in ["api", "ajax", "json", "pdf", "doc", "wp-admin", "wp-json", "query"]):
                requests_log.append(("REQ", req.method, req.url))

        def on_response(resp):
            if any(x in resp.url for x in ["api", "ajax", "json", "pdf", "doc", "wp-admin", "wp-json", "query"]):
                requests_log.append(("RES", resp.status, resp.url))

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"Cargando: {URL}")
        try:
            await page.goto(URL, wait_until="networkidle", timeout=40_000)
        except Exception:
            await page.goto(URL, wait_until="domcontentloaded", timeout=40_000)
        await asyncio.sleep(4)

        print("\n--- Requests capturadas ---")
        for r in requests_log:
            print(f"  {r}")

        # Buscar el select de vehiculo
        sel = await page.query_selector("select[name='vehiculo']")
        if sel:
            opts = await sel.query_selector_all("option")
            print(f"\n--- Opciones del select vehiculo ---")
            for opt in opts:
                val = await opt.get_attribute("value") or ""
                txt = (await opt.inner_text()).strip()
                print(f"  value='{val}' texto='{txt}'")

            # Seleccionar la opción con value=134 y ver qué pasa
            print("\nSeleccionando vehiculo=134...")
            requests_log.clear()
            await page.select_option("select[name='vehiculo']", value="134")
            await asyncio.sleep(5)

            print("\n--- Requests después de seleccionar ---")
            for r in requests_log:
                print(f"  {r}")

            # Ver links ahora
            print("\n--- Links después de seleccionar ---")
            for a in await page.query_selector_all("a"):
                try:
                    t = (await a.inner_text()).strip().replace("\n", " ")
                    h = await a.get_attribute("href") or ""
                    if h and (h.endswith(".pdf") or "download" in h.lower() or "document" in h.lower()):
                        print(f"  [{t[:80]}] -> {h[:120]}")
                except Exception:
                    pass

            # Obtener el HTML del contenedor de documentos
            import re
            html = await page.content()
            pdfs = re.findall(r'https?://[^\s"\'<>]+\.pdf', html)
            print(f"\n--- PDFs en HTML tras selección ---")
            for p_url in pdfs[:10]:
                print(f"  {p_url}")

            # Mostrar todo el texto visible del área de documentos
            for el in await page.query_selector_all(".documentos, .buscador, [class*='document'], [class*='result'], table, .archivo"):
                try:
                    t = (await el.inner_text()).strip().replace("\n", " ")
                    cls = await el.get_attribute("class") or ""
                    if t and len(t) > 5:
                        print(f"\n  [{cls[:40]}]: {t[:200]}")
                except Exception:
                    pass
        else:
            print("Select vehiculo NO encontrado")
            # Intentar hacer click en el tab BUSCADOR DE DOCUMENTOS
            for a in await page.query_selector_all("a"):
                t = (await a.inner_text()).strip()
                if "buscador" in t.lower() or "documento" in t.lower():
                    print(f"Clickeando: {t}")
                    await a.click()
                    await asyncio.sleep(3)
                    break

        print("\nEsperando 20s para inspección visual...")
        await asyncio.sleep(20)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
