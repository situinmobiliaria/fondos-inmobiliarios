"""
Agente Toesca (Renta Residencial, Rentas Inmobiliarias, Rentas Inmobiliarias
Apoquindo, Rentas Inmobiliarias Pt Fondo de Inversion, Net Lease Chile II).

Particularidades:
- Los factsheets de Toesca SI traen una tabla "OBJETIVO RENTABILIDAD DEL
  FONDO" en texto plano, con filas "Rentabilidad desde el inicio
  (anualizada)", "Rentabilidad YTD (anualizada)", "Rentabilidad ultimos 12
  meses", "DividendYield", "LTV", "Leverage" y "Cap Rate" (a veces separado
  como "Cap Rate Bursatil"/"Cap Rate Contable", a veces uno solo). Cada fila
  trae varios valores seguidos (una por serie: A, C, I...) -- se toma el
  primero que no sea "N/A", que es el de la serie principal del fondo.
- Las etiquetas a veces aparecen pegadas sin espacio ("DividendYield",
  "CapRate") y a veces con espacio ("Dividend Yield", "Cap Rate") segun el
  fondo -- se prueban ambas variantes.
- Net Lease Chile II es un fondo mas nuevo (constituido 2023) y su factsheet
  de 1 sola pagina NO incluye la tabla de indicadores en absoluto (no es un
  problema de extraccion, el dato simplemente no esta publicado en este
  informe) -> se marca como categoria E en vez de forzar un valor.
"""
from __future__ import annotations

import re
from pathlib import Path

from agentes.base import AgenteBase, registro_vacio, extraer_metadatos_comunes

LABELS = {
    "Rent. Desde Inicio": ["Rentabilidad desde el inicio"],
    "Rent. YTD": ["Rentabilidad YTD"],
    "Rent. 12M (1A)": ["ltimos 12 meses"],
    "Dividend Yield": ["DividendYield(ii)", "Dividend Yield(ii)", "DividendYield", "Dividend Yield"],
    "LTV": ["LTV(v)", "LTV"],
    "Leverage": ["Leverage(iv)", "Leverage"],
    "Cap Rate": ["CapRate(x)", "Cap Rate(x)", "CapRate Burs", "Cap Rate Burs", "CapRate", "Cap Rate"],
}


def _primer_valor(snippet: str, es_x: bool = False) -> str | None:
    """De una fila tipo '(anualizada)(i) N/A -2,3%\\n...' devuelve el primer
    numero que no sea 'N/A' ni 'n/a'."""
    pat = r"(-?\d+[.,]\d+)\s*x" if es_x else r"(-?\d+[.,]\d+)\s*%"
    for m in re.finditer(pat, snippet):
        return m.group(1).replace(".", ",")
    return None


class AgenteToesca(AgenteBase):
    administradora = "Toesca"

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        if not info.get("tiene_texto"):
            return info
        texto = self._texto_pdf(pdf_path)
        info["tiene_tabla_indicadores"] = "OBJETIVO RENTABILIDAD DEL FONDO" in texto.upper() or "Rentabilidad YTD" in texto
        m = re.search(r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+(\d{4})", texto.upper())
        if m:
            info["fecha_reporte_texto"] = f"{m.group(1).title()} {m.group(2)}"
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        insp = self.inspeccionar(pdf_path)
        texto = self._texto_pdf(pdf_path)
        r.update(extraer_metadatos_comunes(texto))

        if not insp.get("tiene_tabla_indicadores"):
            r["estado_categoria"] = "E"
            r["estado"] = "El factsheet no incluye la tabla de indicadores de rentabilidad (fondo joven / informe reducido)"
            return r

        for campo, labels in LABELS.items():
            valor = None
            for lbl in labels:
                idx = texto.find(lbl)
                if idx == -1:
                    continue
                snippet = texto[idx + len(lbl): idx + len(lbl) + 60]
                valor = _primer_valor(snippet, es_x=(campo == "Leverage"))
                if valor:
                    break
            r[campo] = valor

        campos_ok = [k for k in LABELS if r.get(k)]
        if len(campos_ok) >= 4:
            r["estado_categoria"] = "OK"
            r["estado"] = "OK - rentabilidad extraida"
        elif campos_ok:
            r["estado_categoria"] = "F"
            r["estado"] = "Rentabilidad extraida parcialmente"
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "No se pudo extraer rentabilidad del texto"

        r["fecha_reporte"] = insp.get("fecha_reporte_texto")
        r["notas"] = "Serie principal del fondo (puede haber otras series con valores distintos)"
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteToesca().run_standalone())
