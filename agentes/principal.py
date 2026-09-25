"""
Agente Principal (carpeta "Princiapl" en Fondos Descargados -- typo heredado
del listado maestro; el nombre de la administradora es "Principal").
Fondo: Renta Residencial (Principal - Amplo).

Particularidad importante: el diagnostico anterior marcaba este fondo como
"OK, pero rentabilidad en formato grafico (no extraible por texto)". Al
inspeccionar el PDF ("Reporte de desempeño") se encontro que en realidad SI
trae una tabla de rentabilidad limpia en texto, por serie:

    Serie <mes> 3 meses YTD Desde el Inicio
    I  -0,13% 1,87% 0,14% 29,07%
    B  -0,17% 1,75% 0,06% 25,91%
    C  -0,21% 1,60% -0,03% 22,59%
    D  -0,26% 1,45% -0,13% 18,97%

(el PDF tiene letras sueltas "D"/"F" repetidas como artefacto de marca de
agua que pdfplumber intercala en el texto de otras secciones, pero la fila
de la tabla de rentabilidad en si queda intacta). Se reporta la Serie I
(primera columna de la tabla, aparenta ser la serie principal/institucional).
"""
from __future__ import annotations

import re
from pathlib import Path

from agentes.base import AgenteBase, registro_vacio

FILA_SERIE = re.compile(
    r"\n([IBCD])\s+(-?\d+[.,]\d+)%\s+(-?\d+[.,]\d+)%\s+(-?\d+[.,]\d+)%\s+(-?\d+[.,]\d+)%\n"
)


class AgentePrincipal(AgenteBase):
    administradora = "Princiapl"

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        if not info.get("tiene_texto"):
            return info
        texto = self._texto_pdf(pdf_path)
        info["es_factsheet_probable"] = "Rentabilidad desde el inicio" in texto
        m = re.search(r"[Cc]ierre de (\w+) (\d{4})", texto)
        if m:
            info["fecha_reporte_texto"] = f"{m.group(1)} {m.group(2)}"
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        texto = self._texto_pdf(pdf_path)
        insp = self.inspeccionar(pdf_path)

        m = FILA_SERIE.search(texto)
        if m:
            serie, m1, m3, ytd, inicio = m.groups()
            r["Rent. 1M"] = m1.replace(".", ",")
            r["Rent. 3M"] = m3.replace(".", ",")
            r["Rent. YTD"] = ytd.replace(".", ",")
            r["Rent. Desde Inicio"] = inicio.replace(".", ",")
            r["serie"] = serie
            r["estado_categoria"] = "OK"
            r["estado"] = "OK - rentabilidad extraida"
            r["notas"] = f"Serie {serie} (primera serie reportada en la tabla del fondo)"
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "No se pudo extraer rentabilidad del texto"

        r["fecha_reporte"] = insp.get("fecha_reporte_texto")
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgentePrincipal().run_standalone())
