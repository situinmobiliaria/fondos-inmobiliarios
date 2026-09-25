"""Inspecciona el contenido de la tabla de documentos del frame de Frontal Trust."""
import asyncio
from playwright.async_api import async_playwright

PARENT_URL = "https://www.frontaltrust.cl/informacion-frontal-trust-agf-s-a-y-fondos-publicos/?seccion=buscador-de-documentos&variable=134"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()

        print(f"Cargando: {PARENT_URL}")
        try:
            await page.goto(PARENT_URL, wait_until="networkidle", timeout=45_000)
        except Exception:
            await page.goto(PARENT_URL, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(3)

        # Hacer click en el tab de Buscador de Documentos
        for a in await page.query_selector_all("a"):
            t = (await a.inner_text()).strip()
            if "buscador" in t.lower() or "documento" in t.lower():
                print(f"Click en tab: '{t}'")
                await a.click()
                await asyncio.sleep(4)
                break

        # Encontrar el frame correcto
        target_frame = None
        for frame in page.frames:
            if "viewdashboarddocumento" in frame.url:
                target_frame = frame
                print(f"Frame encontrado: {frame.url}")
                break

        if not target_frame:
            print("Frame no encontrado")
            await asyncio.sleep(10)
            await browser.close()
            return

        await asyncio.sleep(2)

        # Obtener el HTML completo del frame
        html = await target_frame.content()
        print(f"\nHTML del frame (primeros 3000 chars):\n{html[:3000]}")

        print("\n--- Todas las rows de la tabla ---")
        rows = await target_frame.query_selector_all("tr, .row, [class*='row'], [class*='item'], [class*='doc']")
        for row in rows[:20]:
            try:
                t = (await row.inner_text()).strip().replace("\n", " | ")
                if t and len(t) > 3:
                    print(f"  row: {t[:150]}")
            except Exception:
                pass

        print("\n--- Todos los elementos con texto ---")
        for el in await target_frame.query_selector_all("td, li, span, div, p"):
            try:
                t = (await el.inner_text()).strip().replace("\n", " ")
                cls = await el.get_attribute("class") or ""
                if t and len(t) > 5 and len(t) < 200:
                    print(f"  [{cls[:30]}] {t[:120]}")
            except Exception:
                pass

        print("\n--- Inputs y botones ---")
        for el in await target_frame.query_selector_all("input, button, select"):
            try:
                t = await el.get_attribute("type") or await el.get_attribute("value") or await el.inner_text() or ""
                n = await el.get_attribute("name") or await el.get_attribute("id") or ""
                cls = await el.get_attribute("class") or ""
                print(f"  [{t[:40]}] name={n} class={cls[:40]}")
            except Exception:
                pass

        print("\nEsperando 30s...")
        await asyncio.sleep(30)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
