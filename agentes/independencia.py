"""
Agente Independencia (CEFIN Rentas / Fondo de Inversion Independencia Rentas
Inmobiliarias).

Particularidades:
- La "Ficha Informativa" SI trae una tabla historica limpia en texto (filas
  "Rentabilidad valor libro 12M", "Dividend Yield (P. Inicial)", "TIR Nominal
  Contable 12M", con 5 columnas de fechas: 4 cierres anuales + el cierre del
  trimestre actual). El valor vigente es siempre el ULTIMO numero de la fila
  (la columna mas reciente), no el primero como en otras administradoras.
  Por eso este agente no reutiliza buscar_pct() (que toma el primero) sino
  que busca el ultimo porcentaje dentro de una ventana corta despues de la
  etiqueta.
- LTV y Leverage SI estan en el PDF pero como texto dentro de un grafico de
  barras (los numeros del eje/las barras quedan entremezclados sin poder
  asociarlos de forma confiable a "el valor mas reciente"), por lo que se
  dejan vacios en vez de arriesgar un valor incorrecto -- a diferencia del
  diagnostico anterior (que marcaba TODO el fondo como "sin extraer"), aqui
  al menos Rentabilidad 12M / Dividend Yield / TIR si quedan disponibles.
"""
from __future__ import annotations

import re
from pathlib import Path

from agentes.base import AgenteBase, registro_vacio, extraer_metadatos_comunes


def _ultimo_pct(texto: str, label: str, window: int = 90) -> str | None:
    idx = texto.find(label)
    if idx == -1:
        return None
    snippet = texto[idx + len(label): idx + len(label) + window]
    snippet = snippet.split("\n")[0]  # solo la misma linea/fila de la tabla
    valores = re.findall(r"(-?\d+[.,]\d+)\s*%", snippet)
    return valores[-1].replace(".", ",") if valores else None


class AgenteIndependencia(AgenteBase):
    administradora = "Independencia"

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        if not info.get("tiene_texto"):
            return info
        texto = self._texto_pdf(pdf_path)
        info["es_factsheet_probable"] = "FICHA INFORMATIVA" in texto.upper()
        m = re.search(r"FECU\s+(\w+)\s+(\d{4})", texto)
        if m:
            info["fecha_reporte_texto"] = f"{m.group(1).title()} {m.group(2)}"
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        texto = self._texto_pdf(pdf_path)
        insp = self.inspeccionar(pdf_path)

        r["Rent. 12M (1A)"] = _ultimo_pct(texto, "Rentabilidad valor libro 12M")
        r["Dividend Yield"] = _ultimo_pct(texto, "Dividend Yield (P. Inicial)")
        r["TIR"] = _ultimo_pct(texto, "TIR Nominal Contable 12M")
        r["fecha_reporte"] = insp.get("fecha_reporte_texto")

        r.update(extraer_metadatos_comunes(texto))
        r["moneda"] = "CLP"  # todas las cifras del documento estan en $ (pesos), no en UF
        m_ini = re.search(r"Inicio del Fondo\s+(\w+ \d{4})", texto)
        m_venc = re.search(r"Vencimiento\s+(\w+ \d{4})", texto)
        if m_ini and m_venc:
            r["plazo"] = f"{m_ini.group(1)} – vencimiento {m_venc.group(1)}"
        # n_activos ya viene de extraer_metadatos_comunes via "Numero de propiedades"

        campos_ok = [k for k in ("Rent. 12M (1A)", "Dividend Yield", "TIR") if r.get(k)]
        if len(campos_ok) == 3:
            r["estado_categoria"] = "F"
            r["estado"] = "Rentabilidad extraida parcialmente"
            r["notas"] = ("LTV y Leverage estan en grafico de barras (numeros no asociables de forma "
                          "confiable a la columna vigente); Rentabilidad 12M / Dividend Yield / TIR "
                          "son sobre valor libro, no bursatil.")
        elif campos_ok:
            r["estado_categoria"] = "F"
            r["estado"] = "Rentabilidad extraida parcialmente"
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "No se pudo extraer rentabilidad del texto"
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteIndependencia().run_standalone())
