"""Inspecciona la página de documentos de Frontal Trust para un fondo."""
import asyncio
from playwright.async_api import async_playwright

URL = "https://www.frontaltrust.cl/informacion-frontal-trust-agf-s-a-y-fondos-publicos/?seccion=buscador-de-documentos&variable=134"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()

        print(f"Navegando a: {URL}")
        try:
            await page.goto(URL, wait_until="networkidle", timeout=40_000)
        except Exception:
            await page.goto(URL, wait_until="domcontentloaded", timeout=40_000)
        await asyncio.sleep(6)

        print("\n--- TODOS LOS LINKS ---")
        for a in await page.query_selector_all("a"):
            try:
                t = (await a.inner_text()).strip().replace("\n", " ")
                h = await a.get_attribute("href") or ""
                if t:
                    print(f"  [{t[:80]}] -> {h[:100]}")
            except Exception:
                pass

        print("\n--- BOTONES ---")
        for b in await page.query_selector_all("button,[role='button']"):
            try:
                t = (await b.inner_text()).strip().replace("\n", " ")
                h = await b.get_attribute("onclick") or await b.get_attribute("data-url") or ""
                if t:
                    print(f"  [{t[:80]}] onclick/data={h[:100]}")
            except Exception:
                pass

        print("\n--- SELECTS/FILTROS ---")
        for s in await page.query_selector_all("select, input[type='text'], input[type='search']"):
            try:
                n = await s.get_attribute("name") or await s.get_attribute("id") or ""
                print(f"  select/input: {n}")
            except Exception:
                pass

        print("\n--- URLs de PDF en HTML ---")
        import re
        html = await page.content()
        pdfs = re.findall(r'https?://[^\s"\'<>]+\.pdf', html)
        for p_url in pdfs[:20]:
            print(f"  {p_url}")

        print("\n--- Texto visible relevante ---")
        for el in await page.query_selector_all("li, tr, div.documento, div.file, div.download, .item"):
            try:
                t = (await el.inner_text()).strip().replace("\n", " ")
                if t and len(t) > 5 and len(t) < 200:
                    tag = await el.evaluate("el => el.tagName")
                    cls = await el.get_attribute("class") or ""
                    print(f"  <{tag.lower()} class='{cls[:40]}'> {t[:100]}")
            except Exception:
                pass

        print("\nEsperando 30s para inspeccion manual del navegador...")
        await asyncio.sleep(30)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
