"""
Encuentra y clickea el ícono fa-download en la fila de Ficha Mensual.
Captura la descarga y monitorea todas las requests.
"""
import asyncio
import re
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

        await asyncio.sleep(3)

        # Buscar el ícono de descarga fa-download en el frame
        html = await target_frame.content()

        # Buscar botones de descarga y su HTML
        print("--- HTML de botones fa-download ---")
        download_icons = re.findall(r'<[^>]*fa-download[^>]*>.*?</[^>]+>', html[:50000], re.DOTALL)
        for i, icon in enumerate(download_icons[:5]):
            print(f"  [{i}]: {icon[:200]}")

        # También buscar elementos con vDOWNLOAD
        download_vars = re.findall(r'<[^>]*vDOWNLOAD[^>]*>.*?</[^>]+>', html[:50000], re.DOTALL)
        for i, v in enumerate(download_vars[:3]):
            print(f"  vDOWNLOAD [{i}]: {v[:200]}")

        # Buscar anchors con onclick en el frame
        print("\n--- Elementos con onclick en frame ---")
        for el in await target_frame.query_selector_all("[onclick]"):
            try:
                t = (await el.inner_text()).strip()[:30]
                oc = await el.get_attribute("onclick") or ""
                tag = await el.evaluate("el => el.tagName")
                cls = await el.get_attribute("class") or ""
                print(f"  <{tag.lower()} class='{cls[:30]}'> '{t}' onclick={oc[:100]}")
            except Exception:
                pass

        # Buscar específicamente i.fa-download o span.fa-download
        print("\n--- Íconos fa-download como elementos ---")
        for selector in ["i.fa-download", ".fa-download", "[class*='fa-download']", "i.fas", ".fas"]:
            elements = await target_frame.query_selector_all(selector)
            if elements:
                print(f"  Selector '{selector}': {len(elements)} elementos")
                for el in elements[:3]:
                    try:
                        cls = await el.get_attribute("class") or ""
                        parent_html = await el.evaluate("el => el.parentElement ? el.parentElement.outerHTML : ''")
                        print(f"    class={cls} parent={parent_html[:150]}")
                    except Exception:
                        pass

        # Buscar en todas las rows la primera con Ficha Mensual y mirar su HTML
        rows = await target_frame.query_selector_all("tr")
        ficha_row = None
        for row in rows:
            txt = (await row.inner_text()).lower()
            if "ficha" in txt and "mensual" in txt:
                ficha_row = row
                row_html = await row.evaluate("el => el.outerHTML")
                print(f"\n--- HTML de fila Ficha Mensual ---\n{row_html[:500]}")
                break

        if ficha_row:
            # Buscar el ícono de descarga dentro de la fila
            download_btn = await ficha_row.query_selector("i.fa-download, i.fas.fa-download, [class*='fa-download'], img[src*='Download']")
            if download_btn:
                parent = await download_btn.evaluate_handle("el => el.parentElement")
                parent_html = await parent.evaluate("el => el.outerHTML")
                print(f"\nBotón de descarga: {parent_html[:200]}")

                # Limpiar requests y hacer click
                all_reqs.clear()
                print("\nHaciendo click en botón de descarga...")

                download_captured = None
                page.on("download", lambda d: setattr(download_captured, 'value', d))

                try:
                    async with ctx.expect_page(timeout=8_000) as np_info:
                        await download_btn.click()
                    np = await np_info.value
                    print(f"Nueva página: {np.url}")
                    await asyncio.sleep(2)
                    await np.close()
                except Exception:
                    pass

                try:
                    async with page.expect_download(timeout=8_000) as dl_info:
                        await download_btn.click()
                    dl = await dl_info.value
                    print(f"Descarga capturada: {dl.suggested_filename}")
                except Exception as e:
                    print(f"Sin descarga directa: {e.__class__.__name__}")

                print("\nRequests generadas:")
                for r in all_reqs:
                    print(f"  {r}")
            else:
                print("Sin botón de descarga en la fila")
                # Listar todos los elementos dentro de la fila
                cells = await ficha_row.query_selector_all("td")
                for i, td in enumerate(cells):
                    try:
                        t = (await td.inner_text()).strip()
                        h = await td.inner_html()
                        if h.strip():
                            print(f"  td[{i}]: '{t}' html={h[:100]}")
                    except Exception:
                        pass

        print("\nEsperando 30s...")
        await asyncio.sleep(30)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
