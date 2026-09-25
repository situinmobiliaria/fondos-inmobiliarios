"""
Agente Asset (Asset Rentas Residenciales, Asset Outlets Vivo, Asset
Desarrollo Chamisero).

Descarga (Ronda 2, seccion 2.3 -- corregido tras revisar la pagina real):
assetagf.com/fondos-de-inversion/ NO usa tabs de JavaScript -- es una sola
pagina HTML larga con una seccion independiente por fondo (encabezado
"Fondo de Inversión ASSET <nombre>", con acordeones propios: Estados
Financieros, Asambleas, Información de Interés -> Folleto Informativo, etc.).
El bug original (mismo PDF "reciclado" para los 3 fondos) vino de que el
scraper generico buscaba el primer link "Folleto Informativo" en TODA la
pagina, sin acotarlo a la seccion del fondo correcto -- como los 3 fondos
comparten esa misma palabra clave, siempre agarraba el primero (el de Rentas
Residenciales).

descargar() corrige esto:
  1) ubica el encabezado (h1-h4) que contiene el nombre del fondo
  2) sube por los ancestros hasta encontrar un contenedor que ya incluya un
     link a PDF o el texto "folleto" (la seccion propia del fondo)
  3) dentro de ESE contenedor (no de toda la pagina) hace click en cualquier
     boton/acordeon "Ver documentos" / "Información de Interés" para
     expandirlo
  4) busca, tambien acotado a ese contenedor, el link a "Folleto
     Informativo" (evitando Estados Financieros / Informe de Auditor)

No se pudo probar en vivo (sin internet en el entorno de desarrollo) -- hay
que validarla corriendo `python -m agentes.asset` con conexion real.

Extraccion (confirmada con una captura de pantalla del Folleto Informativo
real que compartio el usuario): el documento SI trae, en texto (no grafico),
"Valor Cuota Contable al Inicio (fecha) $X" y "Valor Cuota Contable Actual
(fecha) $X" -- con eso se calcula la rentabilidad acumulada desde el inicio
(igual tecnica que agentes/credicorp.py). Tambien trae Moneda del Fondo y
Plazo del Fondo en texto limpio. El regex se valido contra un texto de
prueba armado a partir de la captura (ver test manual en el historial), pero
falta confirmarlo contra el PDF real extraido por pdfplumber, que puede
mezclar el orden por el layout de 2 columnas como pasa en otras
administradoras -- correr `python -m agentes.asset` una vez descargado el
documento correcto y avisar si no matchea.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from agentes.base import AgenteBase, registro_vacio, sanitize, extraer_metadatos_comunes

BLACKLIST_DOC_ASSET = ["estados financieros", "estado financiero", "informe de auditor",
                       "auditor", "acta", "asamblea", "hecho esencial"]

# Patrones del "Folleto Informativo" real (confirmado por el usuario con una
# captura de pantalla del documento correcto de Asset Rentas Residenciales --
# no se pudo descargar ese PDF en este entorno para probar el regex contra el
# texto real extraido por pdfplumber, asi que esto usa ventanas generosas
# tolerantes a que el layout de 2 columnas mezcle el orden como en otras
# administradoras; hay que validarlo con `python -m agentes.asset` una vez
# descargado el documento correcto):
#   Valor Cuota Contable al Inicio (22 noviembre 2013)   $23.230
#   Valor Cuota Contable Actual (31 marzo 2026)          $68.132
_PATRON_CUOTA_INICIO = re.compile(
    r"Valor Cuota Contable al Inicio\s*\(([^)]+)\)[^\$\d]{0,20}\$?\s*([\d.,]+)")
_PATRON_CUOTA_ACTUAL = re.compile(
    r"Valor Cuota Contable Actual\s*\(([^)]+)\)[^\$\d]{0,20}\$?\s*([\d.,]+)")


def _num_cl(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def _palabras_clave(nombre: str) -> list[str]:
    stop = {"de", "del", "la", "el", "los", "las", "y", "e", "fondo", "inversion",
            "inversión", "asset", "i", "ii", "iii"}
    return [w.lower() for w in nombre.split() if w.lower() not in stop and len(w) > 2]


class AgenteAsset(AgenteBase):
    administradora = "Asset"

    async def descargar(self, fondo: dict, browser) -> Optional[Path]:
        nombre = fondo["nombre"]
        link = fondo["link"]
        folder = self.carpeta(nombre)
        palabras = _palabras_clave(nombre)

        ctx = await browser.new_context(
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = await ctx.new_page()
        filepath = None
        try:
            try:
                await page.goto(link, wait_until="networkidle", timeout=45_000)
            except Exception:
                await page.goto(link, wait_until="domcontentloaded", timeout=45_000)
                await asyncio.sleep(5)

            # 1) ubicar el encabezado de la seccion del fondo
            heading = None
            for sel in ["h1", "h2", "h3", "h4"]:
                for h in await page.query_selector_all(sel):
                    try:
                        texto = (await h.inner_text()).strip().lower()
                        matches = sum(1 for p in palabras if p in texto)
                        if matches >= max(1, len(palabras) - 1):
                            heading = h
                            break
                    except Exception:
                        continue
                if heading:
                    break
            if heading is None:
                return None

            # 2) subir por los ancestros hasta encontrar el contenedor de la
            # seccion propia del fondo (que ya trae un PDF o dice "folleto")
            contenedor = heading
            for _ in range(6):
                padre = await contenedor.evaluate_handle("el => el.parentElement")
                padre_el = padre.as_element()
                if padre_el is None:
                    break
                html_low = (await padre_el.inner_html()).lower()
                contenedor = padre_el
                if "folleto" in html_low or ".pdf" in html_low:
                    break

            # 3) expandir acordeones dentro de ese contenedor
            for boton in await contenedor.query_selector_all("a, button"):
                try:
                    texto_b = (await boton.inner_text()).strip().lower()
                    if any(k in texto_b for k in ["documentos", "información de interés", "informacion de interes", "folleto"]):
                        await boton.click(timeout=2_000)
                        await asyncio.sleep(0.5)
                except Exception:
                    continue

            # 4) buscar el link al folleto informativo, acotado al contenedor
            candidatos = []
            for a in await contenedor.query_selector_all("a"):
                try:
                    href = await a.get_attribute("href") or ""
                    texto = (await a.inner_text()).strip()
                    if not href.lower().endswith(".pdf"):
                        continue
                    low = (texto + " " + href).lower()
                    if any(bl in low for bl in BLACKLIST_DOC_ASSET):
                        continue
                    candidatos.append((texto, href))
                except Exception:
                    continue

            if candidatos:
                preferidos = [c for c in candidatos if "folleto" in c[0].lower()]
                texto_doc, href_doc = (preferidos or candidatos)[0]
                if not href_doc.startswith("http"):
                    from urllib.parse import urljoin
                    href_doc = urljoin(link, href_doc)

                date_str = datetime.now().strftime("%Y%m%d")
                base = f"{date_str}_{sanitize(nombre)}"
                try:
                    import requests as req
                    r = req.get(href_doc, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, stream=True)
                    r.raise_for_status()
                    filepath = folder / f"{base}.pdf"
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(65536):
                            f.write(chunk)
                except Exception:
                    filepath = None
        finally:
            await ctx.close()

        return filepath

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        if info.get("tiene_texto"):
            texto = self._texto_pdf(pdf_path)
            info["es_informe_auditor"] = "informe del auditor" in texto.lower() or "opinión" in texto.lower()
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        insp = self.inspeccionar(pdf_path)

        if insp.get("es_informe_auditor"):
            r["estado_categoria"] = "C"
            r["estado"] = "Se descargo el documento equivocado (Informe de Auditor, no el Folleto Informativo)"
            r["notas"] = "descargar() no encontro el link correcto dentro de la seccion del fondo; revisar selectores en agentes/asset.py."
            return r

        texto = self._texto_pdf(pdf_path)
        r.update(extraer_metadatos_comunes(texto))

        m_ini = _PATRON_CUOTA_INICIO.search(texto)
        m_act = _PATRON_CUOTA_ACTUAL.search(texto)
        if m_ini and m_act:
            try:
                v_ini, v_act = _num_cl(m_ini.group(2)), _num_cl(m_act.group(2))
                if v_ini > 0:
                    pct = (v_act / v_ini - 1) * 100
                    r["Rent. Desde Inicio"] = f"{pct:.2f}".replace(".", ",")
                    r["estado_categoria"] = "F"
                    r["estado"] = "Rentabilidad calculada desde Valor Cuota Contable (Inicio vs Actual)"
                    r["notas"] = (f"Calculado desde Valor Cuota Contable: {m_ini.group(2)} ({m_ini.group(1)}) -> "
                                  f"{m_act.group(2)} ({m_act.group(1)}). Variacion de precio de la cuota, no "
                                  f"incluye dividendos ni esta anualizada.")
                    return r
            except ValueError:
                pass

        r["estado_categoria"] = "F" if texto.strip() else "E"
        r["estado"] = "Documento descargado, no se encontraron las etiquetas 'Valor Cuota Contable al Inicio/Actual' esperadas"
        r["notas"] = ("Se esperaba el patron confirmado por captura de pantalla del Folleto Informativo "
                      "('Valor Cuota Contable al Inicio (fecha) $X' / '...Actual (fecha) $X'); no se encontro "
                      "en este PDF -- puede que el layout de 2 columnas haya mezclado el texto (ver notas de "
                      "otras administradoras con el mismo problema) o que este no sea el Folleto Informativo.")
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteAsset().run_standalone())
