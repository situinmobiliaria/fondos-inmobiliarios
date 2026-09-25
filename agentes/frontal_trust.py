"""
Agente Frontal Trust (7 fondos: Fundamenta Plaza Egaña, San Bernardo,
Desarrollos Industriales I, Desarrollo Inmobiliario XIII/XV/XVI/XX).

Descarga: el sitio de Frontal Trust no tiene links directos por fondo -- cada
fondo vive en un dashboard con un iframe identificado por (variable_id,
vehiculo_id) que hay que resolver a mano. Esta logica ya estaba probada en
scraper_especiales.py::scrape_frontal_trust y se porta aqui tal cual
(navega al tab "Buscador de Documentos", filtra por tipo "Ficha Mensual" y
descarga el primer resultado).

Extraccion: revisando el texto de estos PDFs ("Informe General"), son fondos
de DESARROLLO -- reportan avance de proyectos por unidad (ventas, escrituras,
% construccion) en vez de una tabla de rentabilidad periodica. La unica
mencion de retorno es contractual/objetivo (ej. "una rentabilidad equivalente
a UF mas 8,0% anual... tasa futura compuesta" para la Distribucion
Extraordinaria de la Serie B), que es una condicion del reglamento, no un
resultado medido -- no corresponde extraerla como "Rentabilidad". Por eso se
mantienen en Categoria E, igual que en el diagnostico original.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path

from agentes.base import AgenteBase, registro_vacio, sanitize, extraer_metadatos_comunes

FRONTAL_TRUST_IDS = {
    "Fundamenta Plaza Egaña":       (134, 413),
    "San Bernardo":                 (183, 1495),
    "Desarrollos Industriales I":   (203, 2059),
    "Desarrollo Inmobiliario XIII": (138, 407),
    "Desarrollo Inmobiliario XV":   (173, 1053),
    "Desarrollo Inmobiliario XVI":  (177, 1991),
    "Desarrollo Inmobiliario XX":   (204, 2061),
}


def _get_ids(nombre_fondo: str):
    nombre_low = nombre_fondo.lower().strip()
    for key, ids in FRONTAL_TRUST_IDS.items():
        if key.lower().strip() == nombre_low:
            return ids
    for key, ids in sorted(FRONTAL_TRUST_IDS.items(), key=lambda x: len(x[0]), reverse=True):
        if key.lower() in nombre_low or nombre_low in key.lower():
            return ids
    return None


class AgenteFrontalTrust(AgenteBase):
    administradora = "Frontal Trust"

    async def descargar(self, fondo: dict, browser) -> Path | None:
        nombre = fondo["nombre"]
        folder = self.carpeta(nombre)
        ids = _get_ids(nombre)
        if not ids:
            return None
        variable_id, _vehiculo_id = ids

        ctx = await browser.new_context(accept_downloads=True,
                                         user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await ctx.new_page()
        filepath = None
        parent_url = (
            "https://www.frontaltrust.cl/informacion-frontal-trust-agf-s-a-y-fondos-publicos/"
            f"?seccion=buscador-de-documentos&variable={variable_id}"
        )
        try:
            try:
                await page.goto(parent_url, wait_until="networkidle", timeout=45_000)
            except Exception:
                await page.goto(parent_url, wait_until="domcontentloaded", timeout=45_000)
                await asyncio.sleep(6)
            await asyncio.sleep(3)

            for a in await page.query_selector_all("a"):
                try:
                    t = (await a.inner_text()).strip()
                    if "buscador" in t.lower() or "documento" in t.lower():
                        await a.click()
                        await asyncio.sleep(4)
                        break
                except Exception:
                    continue

            date_str = datetime.now().strftime("%Y%m%d")
            base = f"{date_str}_{sanitize(nombre)}"

            target_frame = None
            for frame in page.frames:
                if "dashboard.frontaltrust.cl" in frame.url:
                    target_frame = frame
                    if "documento" in frame.url:
                        break

            if target_frame:
                await asyncio.sleep(3)
                try:
                    await target_frame.select_option(
                        "select[name='vDOCUMENTOTIPOID']", label="Ficha Mensual", timeout=8_000)
                    submit_btn = await target_frame.query_selector("input[type='submit'], button[type='submit']")
                    if submit_btn:
                        await submit_btn.click()
                    else:
                        await target_frame.evaluate("document.querySelector('form').submit()")
                    await asyncio.sleep(4)
                except Exception:
                    pass

                ficha_row = None
                for row in await target_frame.query_selector_all("tr"):
                    try:
                        txt = (await row.inner_text()).lower()
                        if "ficha" in txt and "mensual" in txt:
                            ficha_row = row
                            break
                    except Exception:
                        continue

                if ficha_row:
                    download_icon = await ficha_row.query_selector(
                        "img[class*='fa-download'], img[id*='vDOWNLOAD'], [id*='vDOWNLOAD']")
                    if download_icon:
                        try:
                            async with ctx.expect_page(timeout=15_000) as np_info:
                                await download_icon.click()
                            np = await np_info.value
                            await np.wait_for_load_state("load", timeout=20_000)
                            doc_url = np.url
                            await np.close()
                            if doc_url and ".pdf" in doc_url.lower():
                                import requests as req
                                r = req.get(doc_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, stream=True)
                                filepath = folder / f"{base}.pdf"
                                with open(filepath, "wb") as f:
                                    for chunk in r.iter_content(65536):
                                        f.write(chunk)
                        except Exception:
                            try:
                                async with page.expect_download(timeout=12_000) as dl_info:
                                    await download_icon.click()
                                dl = await dl_info.value
                                ext = Path(dl.suggested_filename).suffix or ".pdf"
                                filepath = folder / f"{base}{ext}"
                                await dl.save_as(filepath)
                            except Exception:
                                filepath = None
        finally:
            await ctx.close()

        return filepath

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        texto = self._texto_pdf(pdf_path)

        m = re.search(r"Informe General (\w+) (\d{4})", texto)
        if m:
            r["fecha_reporte"] = f"{m.group(2)}-{m.group(1)[:3]}"

        r.update(extraer_metadatos_comunes(texto))
        r["estado_categoria"] = "E"
        r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"
        r["notas"] = ("Informe General de fondo de desarrollo: reporta avance de proyectos por unidad "
                      "(ventas/escrituras/%construccion), no una tabla de rentabilidad periodica.")
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteFrontalTrust().run_standalone())
