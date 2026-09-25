"""Inspecciona Frontal Trust y Santander sin interacción manual."""
import asyncio
from playwright.async_api import async_playwright

PAGINAS = [
    ("Santander", "https://www.santanderassetmanagement.cl/ficha-comercial-fi?id=656"),
    ("Frontal Trust", "https://www.frontaltrust.cl/chile/"),
]

async def inspeccionar(browser, nombre, url):
    print(f"\n{'='*60}\n  {nombre}\n  {url}\n{'='*60}")
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = await ctx.new_page()
    try:
        try:
            await page.goto(url, wait_until="networkidle", timeout=40_000)
        except Exception:
            await page.goto(url, wait_until="domcontentloaded", timeout=40_000)
            await asyncio.sleep(6)
        await asyncio.sleep(3)

        print("\n--- TODOS LOS LINKS (a) ---")
        for a in await page.query_selector_all("a"):
            try:
                t = (await a.inner_text()).strip().replace("\n"," ")
                h = await a.get_attribute("href") or ""
                if t:
                    print(f"  [{t[:90]}] -> {h[:120]}")
            except Exception:
                pass

        print("\n--- BOTONES y TABS ---")
        for b in await page.query_selector_all("button,[role='tab'],[role='button'],summary"):
            try:
                t = (await b.inner_text()).strip().replace("\n"," ")
                c = await b.get_attribute("class") or ""
                if t:
                    print(f"  [{t[:90]}]  class={c[:60]}")
            except Exception:
                pass

        print("\n--- IFRAMES ---")
        for fr in await page.query_selector_all("iframe"):
            src = await fr.get_attribute("src") or ""
            print(f"  iframe src={src[:120]}")

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        await ctx.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        for nombre, url in PAGINAS:
            await inspeccionar(browser, nombre, url)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
