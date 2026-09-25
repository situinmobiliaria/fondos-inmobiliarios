"""
Agente BTG Pactual (Renta Comercial).

Particularidades de este sitio / factsheet:
- La pagina (btgpactual.cl/rentacomercial/informacion-a-los-inversionistas/)
  tiene un link cuyo texto matchea "Ficha del fondo" / "factsheet" -> la
  logica generica de AgenteBase.descargar() ya funciona bien aqui, no hace
  falta sobreescribirla (validado en el diagnostico: categoria OK).
- El factsheet trae DOS series (A e I). Se reporta siempre la Serie A, que
  es la serie principal / la que se transa en bolsa (CFIBTGRCA).
- pdfplumber mezcla las dos columnas del PDF al extraer texto plano (el PDF
  tiene layout a 2 columnas), por lo que las etiquetas y los numeros quedan
  entrelazados con texto de otras secciones. Por eso extraer() no usa una
  regex global sino AgenteBase.buscar_pct()/buscar_num(), que busca cada
  etiqueta y toma el primer numero dentro de una ventana corta de caracteres
  a continuacion (evita cruzarse con la etiqueta de otro indicador).
- La tabla de rentabilidad esta en texto (no en grafico), a diferencia de la
  mayoria de las otras administradoras -> es uno de los pocos casos ya "OK".
- Fecha de reporte: aparece como "<Mes> | <Año>" en el encabezado de cada
  pagina (ej. "Marzo | 2026"), y es el mes de cierre del informe (no la
  fecha de descarga).
"""
from __future__ import annotations

import re
from pathlib import Path

from agentes.base import AgenteBase, registro_vacio

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


class AgenteBTG(AgenteBase):
    administradora = "BTG Pactual"

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        if not info.get("tiene_texto"):
            return info

        texto = self._texto_pdf(pdf_path)
        info["es_factsheet_probable"] = "Rentabilidad Bursátil del Fondo" in texto or (
            "Rentabilidad Burs" in texto and "til del Fondo" in texto
        )

        m = re.search(r"(\w+)\s*\|\s*(\d{4})\s*Real Estate", texto)
        if m and m.group(1).lower() in MESES:
            mes = MESES[m.group(1).lower()]
            info["fecha_reporte"] = f"{m.group(2)}-{mes:02d}"

        info["ubicacion_rentabilidad"] = "texto (tabla 'Rentabilidad Bursátil del Fondo')"
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        texto = self._texto_pdf(pdf_path)

        # Nota: por el mojibake de acentos en este PDF, "Últimos" llega como
        # "�ltimos" -- se busca por el sufijo "ltimos" que es estable.
        r["Rent. YTD"] = self.buscar_pct(texto, "hasta la fecha")
        r["Rent. 12M (1A)"] = self.buscar_pct(texto, "ltimos 12M")
        r["Rent. 24M (2A)"] = self.buscar_pct(texto, "ltimos 24M")
        r["Rent. 36M (3A)"] = self.buscar_pct(texto, "ltimos 36M")
        r["Rent. Desde Inicio"] = self.buscar_pct(texto, "Desde el inicio")
        r["Dividend Yield"] = self.buscar_pct(texto, "Dividend Yield", permitir_negativo=False)
        cap_rate = self.buscar_pct(texto, "Cap Rate Burs", permitir_negativo=False)
        r["Cap Rate"] = cap_rate
        r["LTV"] = self.buscar_num(texto, "Loan to Value", sufijo="%", window=30)
        r["Leverage"] = self.buscar_num(texto, "Leverage", sufijo="x", window=20)

        insp = self.inspeccionar(pdf_path)
        r["fecha_reporte"] = insp.get("fecha_reporte")
        r["serie"] = "A"
        r["moneda"] = "CLP"  # "Moneda del Fondo CLP" en Antecedentes Generales

        m_plazo = re.search(r"Plazo de Duraci[oó]n[^\d]*(\d{2}-\d{2}-\d{4})", texto)
        r["plazo"] = f"hasta {m_plazo.group(1)}" if m_plazo else None
        # N Activos: el PDF solo lo menciona en prosa ("11 activos de oficinas,
        # 24 comerciales..."), no en una tabla/campo limpio -> se deja vacio
        # para no inventar un total.

        campos_ok = [k for k in (
            "Rent. YTD", "Rent. 12M (1A)", "Rent. 24M (2A)", "Rent. 36M (3A)",
            "Rent. Desde Inicio", "Dividend Yield", "Cap Rate", "LTV",
        ) if r.get(k)]

        if len(campos_ok) >= 6:
            r["estado_categoria"] = "OK"
            r["estado"] = "OK - rentabilidad extraida"
        elif campos_ok:
            r["estado_categoria"] = "F"
            r["estado"] = "Rentabilidad extraida parcialmente"
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "No se pudo extraer rentabilidad del texto"

        r["notas"] = "Serie A (fondo tambien reporta Serie I en el PDF)"
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteBTG().run_standalone())
