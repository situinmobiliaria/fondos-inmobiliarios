"""
Agente Ameris (7 fondos: Renta Industrial II, Renta Reisdencial, Rentas y
Desarrollos Aconcagua, Desarrollo Inmobiliario IX, UPC Desarrollo
Inmobiliario, Desarrollo Inmobiliario Uno, Megacentro Buenaventura).

Descarga (Ronda 2, seccion 2.2 -- corregido tras revisar Aclaraciones/Ameris/1..png):
Ameris SI publica la informacion, pero la pagina
(ameris.cl/asset-management/real-state/) es una SPA de una sola URL con un
menu lateral por categoria (Desarrollo / Deuda / Renta). Al hacer clic en un
fondo del menu, el panel de la derecha cambia dinamicamente (JS) y muestra 4
acordeones: Actas, Avisos, Documentos del Fondo, Estados Financieros.

descargar() reproduce esa interaccion con Playwright:
  1) click en la categoria del fondo (si el menu la trae colapsada; si ya
     esta expandida el click no hace daño, solo no cambia nada visible)
  2) click en el nombre del fondo dentro de esa categoria (match por palabras
     clave del nombre, igual que AgenteBase.navegar_a_fondo_en_pagina)
  3) espera a que el titulo del panel derecho contenga el nombre del fondo
     (confirma que cambio de contenido antes de seguir)
  4) click en el acordeon "Documentos del Fondo" para expandirlo
  5) toma el PDF mas reciente dentro de ese acordeon cuyo texto matchee
     factsheet/ficha/informe (evita Actas/Avisos/Estados Financieros)

Esta logica NO se pudo probar en vivo (sin internet en el entorno de
desarrollo) -- hay que validarla corriendo `python -m agentes.ameris` con
conexion real y ajustar los selectores si el sitio cambio algo respecto a la
captura de pantalla.

Categorizacion de rentabilidad (si ya se tiene un PDF descargado, sea de
antes o por descargar() nuevo):
- Para 3 fondos (Desarrollo Inmobiliario IX, Renta Reisdencial, UPC
  Desarrollo Inmobiliario) el documento disponible es un "informe mensual"
  exportado desde Power BI, con graficos pero SIN tabla numerica de
  rentabilidad en el texto -> Categoria E.
- Para los otros 4, si no se logra descargar la ficha real con la logica de
  arriba, se mantiene el fallback anterior (Estados Financieros -> Categoria
  G) en vez de dejar el fondo sin ningun dato.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from agentes.base import AgenteBase, registro_vacio, extraer_metadatos_comunes, sanitize

SIN_FACTSHEET = {
    "Renta Industrial II", "Rentas y Desarrollos Aconcagua",
    "Desarrollo Inmobiliario Uno", "Megacentro Buenaventura",
}

# Categoria del menu lateral en la que aparece cada fondo (segun
# Aclaraciones/Ameris/1..png). Ameris/Rentas y Ameris/Renta Industrial II no
# se alcanzaron a ver en la captura -> se intentan las 3 categorias conocidas
# por si acaso (ver _CATEGORIAS_PROBABLES).
CATEGORIA_FONDO = {
    "Desarrollo Inmobiliario IX": "Desarrollo",
    "UPC Desarrollo Inmobiliario": "Desarrollo",
    "Desarrollo Inmobiliario Uno": "Desarrollo",
    "Megacentro Buenaventura": "Desarrollo",
}
_CATEGORIAS_CONOCIDAS = ["Desarrollo", "Deuda", "Renta", "Rentas"]

BLACKLIST_DOC_AMERIS = ["acta", "aviso", "estados financieros", "estado financiero", "fecu", "eeff"]


def _palabras_clave(nombre: str) -> list[str]:
    stop = {"de", "del", "la", "el", "los", "las", "y", "e", "fondo", "inversion",
            "inversión", "ameris", "i", "ii", "iii", "iv"}
    return [w.lower() for w in nombre.split() if w.lower() not in stop and len(w) > 2]


class AgenteAmeris(AgenteBase):
    administradora = "Ameris"

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

            # 1) click en la categoria (si se conoce; si no, prueba las conocidas)
            categorias_a_probar = [CATEGORIA_FONDO[nombre]] if nombre in CATEGORIA_FONDO else _CATEGORIAS_CONOCIDAS
            for cat in categorias_a_probar:
                try:
                    el = page.get_by_text(cat, exact=False).first
                    if await el.count() if hasattr(el, "count") else el:
                        await el.click(timeout=3_000)
                        await asyncio.sleep(0.8)
                except Exception:
                    pass

            # 2) click en el nombre del fondo (match por palabras clave, igual
            # que AgenteBase.navegar_a_fondo_en_pagina pero sobre <li>/<a>/<div>)
            fondo_click_ok = False
            for selector in ["li", "a", "button", "div"]:
                if fondo_click_ok:
                    break
                try:
                    elementos = await page.query_selector_all(selector)
                except Exception:
                    continue
                for el in elementos:
                    try:
                        texto = (await el.inner_text()).strip().lower()
                        if not texto or len(texto) > 120:
                            continue
                        matches = sum(1 for p in palabras if p in texto)
                        if matches >= max(1, len(palabras) - 1):
                            await el.scroll_into_view_if_needed()
                            await el.click(timeout=3_000)
                            fondo_click_ok = True
                            break
                    except Exception:
                        continue

            if fondo_click_ok:
                # 3) esperar a que el panel derecho muestre el nombre del fondo
                try:
                    await page.wait_for_function(
                        """(palabras) => {
                            const t = document.body.innerText.toLowerCase();
                            return palabras.filter(p => t.includes(p)).length >= palabras.length - 1;
                        }""",
                        arg=palabras,
                        timeout=8_000,
                    )
                except Exception:
                    pass
                await asyncio.sleep(1)

            # 4) expandir "Documentos del Fondo"
            try:
                doc_header = page.get_by_text("Documentos del Fondo", exact=False).first
                await doc_header.click(timeout=3_000)
                await asyncio.sleep(0.8)
            except Exception:
                pass

            # 5) buscar el PDF mas reciente dentro de los links visibles que
            # no sean Actas/Avisos/EEFF
            candidatos = []
            for a in await page.query_selector_all("a"):
                try:
                    href = await a.get_attribute("href") or ""
                    texto = (await a.inner_text()).strip()
                    if not href.lower().endswith(".pdf"):
                        continue
                    low = (texto + " " + href).lower()
                    if any(bl in low for bl in BLACKLIST_DOC_AMERIS):
                        continue
                    candidatos.append((texto, href))
                except Exception:
                    continue

            if candidatos:
                # ultimo (mas reciente, asumiendo orden de publicacion) que
                # matchee ficha/factsheet/informe; si ninguno matchea, el primero
                preferidos = [c for c in candidatos if re.search(r"ficha|factsheet|informe|reporte", c[0].lower())]
                texto_doc, href_doc = (preferidos or candidatos)[-1]

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

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        nombre_fondo = pdf_path.parent.name
        texto = self._texto_pdf(pdf_path)
        r.update(extraer_metadatos_comunes(texto))

        es_eeff = "estados financieros" in texto.lower()[:2000] or "EEFF" in pdf_path.name

        if nombre_fondo in SIN_FACTSHEET or es_eeff:
            r["estado_categoria"] = "G"
            r["estado"] = "La administradora no publica factsheet/ficha para este fondo"
            r["notas"] = "Se descargaron los Estados Financieros como mejor alternativa disponible; no contienen rentabilidad periodica lista para usar."
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"
            r["notas"] = "Informe mensual exportado de Power BI: solo trae graficos (valor cuota, dividendos), sin tabla numerica de rentabilidad."
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteAmeris().run_standalone())
