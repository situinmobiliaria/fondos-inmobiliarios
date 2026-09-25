"""
Agente Larrain Vial (Patio Oficinas I, Patio Oficinas II, Renta Inmobiliaria I,
Patio Stripcenters II).

Particularidades:
- El factsheet ("Reporte Patio Renta Inmobiliaria") SI trae los indicadores en
  texto (no en grafico), pero con etiquetas pegadas a numeros de nota al pie
  (ej. "DividendYield8", "Loan ToValue2") y mezcladas con los ejes de un
  grafico de evolucion de valor cuota que esta al lado. Por eso se usa
  ventana corta (buscar_pct/buscar_num) en vez de una regex global, igual que
  en el agente BTG.
- Reporta dos metricas de Dividend Yield: "Dividend Yield (NAV final)" y
  "Dividend Yield" a secas (sobre valor bolsa). Se usa esta ultima
  (bursatil), que es la que veniamos registrando.
- "Rentabilidad Directa" y el LTV/"Loan to Value" aparecen con varios valores
  seguidos en la misma linea (series / periodos distintos); se toma el
  primero, que es el vigente al cierre del reporte.
- OJO Patio Oficinas II: el archivo actualmente descargado
  ("20260507_Patio Oficinas II.pdf") NO es el factsheet -- es una carta a
  aportantes sobre la auditoria forense de Grupo Patio/Factop (marzo 2024).
  El diagnostico anterior lo tenia mal clasificado como "OK, rentabilidad en
  grafico" cuando en realidad es Categoria C (documento equivocado). Este
  agente lo detecta en inspeccionar() y no intenta extraer rentabilidad de
  ahi -- hay que volver a descargar el PDF correcto desde la pagina del fondo.
"""
from __future__ import annotations

import re
from pathlib import Path

from agentes.base import AgenteBase, registro_vacio


class AgenteLarrainVial(AgenteBase):
    administradora = "Larrain Vial"

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        if not info.get("tiene_texto"):
            return info

        texto = self._texto_pdf(pdf_path)
        tiene_indicadores = "INDICADORES" in texto.upper() or "Dividend" in texto or "DividendYield" in texto
        es_carta_auditoria = "Auditoría" in texto and "Gerente General" in texto and not tiene_indicadores
        info["es_factsheet_probable"] = tiene_indicadores and not es_carta_auditoria
        info["documento_equivocado"] = es_carta_auditoria

        m = re.search(r"(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)\s+(\d{4})", texto)
        if m:
            info["fecha_reporte_texto"] = f"{m.group(1)} {m.group(2)}"
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        insp = self.inspeccionar(pdf_path)

        if insp.get("documento_equivocado"):
            r["estado_categoria"] = "C"
            r["estado"] = "Se descargo el documento equivocado (carta a aportantes, no el factsheet)"
            r["notas"] = "Reintentar descarga desde la pagina del fondo en larrainvial.com; este PDF es una carta sobre la auditoria forense de Grupo Patio/Factop."
            return r

        texto = self._texto_pdf(pdf_path)

        dy = self.buscar_pct(texto, "DividendYield8") or self.buscar_pct(texto, "Dividend Yield8")
        if not dy:
            # fallback: primera ocurrencia de "Dividend Yield" que NO sea la variante NAV
            for m in re.finditer(r"Dividend ?Yield(?!\s*\(NAV)[^\n%]{0,20}?(-?\d+[.,]\d+)\s*%", texto):
                dy = m.group(1).replace(".", ",")
                break
        r["Dividend Yield"] = dy

        ltv = self.buscar_pct(texto, "LTV", window=15) or self.buscar_pct(texto, "Loan ToValue") or self.buscar_pct(texto, "Loan to Value")
        r["LTV"] = ltv

        rd = self.buscar_pct(texto, "Rentabilidad Directa")
        r["Rentabilidad Directa"] = rd.replace(",", ".") if rd else None

        lev = self.buscar_num(texto, "Leverage", sufijo="", window=15)
        r["Leverage"] = lev

        # Los 4 fondos reportan sus valores en "$" (CLP); no hay un campo
        # explicito de "Moneda del Fondo" en este layout.
        r["moneda"] = "CLP"
        idx_dur = texto.find("Duraci")
        m_plazo = re.search(r"(\d+\s*a[nñ]os)", texto[idx_dur:idx_dur + 60]) if idx_dur != -1 else None
        r["plazo"] = m_plazo.group(1) if m_plazo else None
        # N Activos: estos fondos son de 1 solo edificio/activo subyacente
        # cada uno, pero el PDF no lo declara con una etiqueta explicita
        # ("N Activos") -> se deja vacio para no inventar.

        campos_ok = [k for k in ("Dividend Yield", "LTV", "Rentabilidad Directa", "Leverage") if r.get(k)]
        if campos_ok:
            r["estado_categoria"] = "OK"
            r["estado"] = "OK - rentabilidad extraida"
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "No se pudo extraer rentabilidad del texto"

        r["notas"] = "Dividend Yield sobre valor bolsa; ver PDF para Dividend Yield sobre NAV"
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteLarrainVial().run_standalone())
