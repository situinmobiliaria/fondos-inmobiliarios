"""
Agente Banchile (Desarrollo y Rentas Residenciales, Inmobiliario IX, X, XI).

Particularidad: 3 de los 4 fondos (todos excepto Inmobiliario X) SI traen
una tabla de rentabilidad limpia en texto, con dos columnas (UF y CLP):

    Rentabilidad del Fondo (6)(7)
    Desde el Inicio (anualizada) -4,82% -0,14%
    30 Días -0,04% 0,09%
    90 Días 0,04% 0,34%
    360 Días -5,30% -2,85%
    Acumulado año 0,04% 0,32%

Se reporta la columna UF (primer porcentaje de cada fila), que es la moneda
de referencia del fondo. "Inmobiliario X" SI es Categoria E genuina: su PDF
solo trae un grafico de evolucion ("Rentabilidad en CLP... en base 100"),
sin la tabla numerica -- se detecta la ausencia de la tabla y se deja vacio
en vez de forzar un valor.
"""
from __future__ import annotations

import re
from pathlib import Path

from agentes.base import AgenteBase, registro_vacio, extraer_metadatos_comunes

LABELS = {
    "Rent. 1M": "30 D",       # "30 Dias"/"30 D�as"
    "Rent. 3M": "90 D",
    "Rent. 12M (1A)": "360 D",
    "Rent. YTD": "Acumulado a",  # "Acumulado año"
    "Rent. Desde Inicio": "Desde el Inicio",
}


def _primer_pct(texto: str, label: str, window: int = 40) -> str | None:
    idx = texto.find(label)
    if idx == -1:
        return None
    snippet = texto[idx + len(label): idx + len(label) + window]
    m = re.search(r"(-?\d+[.,]\d+)\s*%", snippet)
    return m.group(1).replace(".", ",") if m else None


class AgenteBanchile(AgenteBase):
    administradora = "Banchile"

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        if not info.get("tiene_texto"):
            return info
        texto = self._texto_pdf(pdf_path)
        info["tiene_tabla_rentabilidad"] = "Rentabilidad del Fondo" in texto
        m = re.search(r"Informaci.n al (\d{1,2}) de(\w+) de (\d{4})", texto)
        if m:
            info["fecha_reporte_texto"] = f"{m.group(1)} de{m.group(2)} de {m.group(3)}"
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        insp = self.inspeccionar(pdf_path)
        texto = self._texto_pdf(pdf_path)
        r.update(extraer_metadatos_comunes(texto))  # rescata N Proyectos Vigentes como n_activos
        r["fecha_reporte"] = insp.get("fecha_reporte_texto")

        if not insp.get("tiene_tabla_rentabilidad"):
            r["estado_categoria"] = "E"
            r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"
            r["notas"] = "Este fondo solo trae el grafico de evolucion de valor cuota, sin la tabla numerica 'Rentabilidad del Fondo'."
            r["moneda"] = "CLP"  # el grafico de evolucion de este fondo esta expresado en CLP
            return r

        for campo, label in LABELS.items():
            r[campo] = _primer_pct(texto, label)

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

        r["moneda"] = "UF"
        r["notas"] = "Rentabilidad en UF (el PDF tambien reporta la misma tabla en CLP)"
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteBanchile().run_standalone())
