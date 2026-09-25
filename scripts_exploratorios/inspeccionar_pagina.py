"""
Inspecciona la estructura de una página para identificar
cómo están listados los fondos y sus documentos.
"""
import asyncio
from playwright.async_api import async_playwright

PAGINAS = [
    ("Ameris", "https://www.ameris.cl/asset-management/real-state/"),
    ("Frontal Trust", "https://www.frontaltrust.cl/chile/"),
    ("Santander", "https://www.santanderassetmanagement.cl/ficha-comercial-fi?id=656"),
]


async def inspeccionar(browser, nombre, url):
    print(f"\n{'='*60}")
    print(f"  {nombre}: {url}")
    print('='*60)

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = await context.new_page()

    try:
        try:
            await page.goto(url, wait_until="networkidle", timeout=40_000)
        except Exception:
            await page.goto(url, wait_until="domcontentloaded", timeout=40_000)
            await asyncio.sleep(5)

        await asyncio.sleep(3)

        # Mostrar todos los <a> con texto
        print("\n--- LINKS (a) con texto ---")
        anchors = await page.query_selector_all("a")
        for a in anchors:
            try:
                txt = (await a.inner_text()).strip().replace("\n", " ")
                href = await a.get_attribute("href") or ""
                if txt:
                    print(f"  [{txt[:80]}] -> {href[:100]}")
            except Exception:
                pass

        # Mostrar botones con texto
        print("\n--- BOTONES con texto ---")
        btns = await page.query_selector_all("button, [role='button'], [role='tab']")
        for b in btns:
            try:
                txt = (await b.inner_text()).strip().replace("\n", " ")
                cls = await b.get_attribute("class") or ""
                if txt:
                    print(f"  [{txt[:80]}] class={cls[:60]}")
            except Exception:
                pass

        # Mostrar elementos con texto que contenga nombre de fondos conocidos
        print("\n--- Elementos con texto tipo 'fondo' ---")
        items = await page.query_selector_all("li, div, span, p, h1, h2, h3, h4")
        for el in items:
            try:
                txt = (await el.inner_text()).strip().replace("\n", " ")
                if any(kw in txt.lower() for kw in ["fondo", "fund", "renta", "industrial", "residencial", "desarrollo"]):
                    if len(txt) < 120 and len(txt) > 5:
                        tag = await el.evaluate("el => el.tagName")
                        print(f"  <{tag.lower()}> {txt[:100]}")
            except Exception:
                pass

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        await context.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        for nombre, url in PAGINAS:
            await inspeccionar(browser, nombre, url)
            input(f"\n>>> Presiona Enter para continuar con la siguiente página...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
