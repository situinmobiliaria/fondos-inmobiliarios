"""
Agente Inversiones Security (Rentas Inmobiliarias II).

Particularidad: el documento descargado es un "Folleto Informativo" tipo
KIID regulatorio (Tasa Anual de Costos + "Mejores y Peores Rentabilidades
Ultimos 5 anos"), no un factsheet de rentabilidad periodica. Los numeros de
rentabilidad estan en un grafico de barras horizontal sin etiquetas de
periodo asociadas en el texto extraido (aparecen como una lista suelta de
porcentajes: 7,57%, 17,67%, -0,72%, etc., sin forma confiable de saber a que
mes/año corresponde cada uno) -> genuinamente Categoria E, confirmado tras
inspeccionar el PDF (no es un problema de regex, el dato no esta en texto
estructurado).
"""
from __future__ import annotations

from pathlib import Path

from agentes.base import AgenteBase, registro_vacio


class AgenteSecurity(AgenteBase):
    administradora = "Inversiones Security"

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        texto = self._texto_pdf(pdf_path)
        if "expresadas en CLP" in texto:
            r["moneda"] = "CLP"
        r["estado_categoria"] = "E"
        r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"
        r["notas"] = ("Folleto Informativo tipo KIID: trae 'Mejores y Peores Rentabilidades Ultimos 5 anos' "
                      "como grafico de barras sin etiquetas de periodo en el texto extraido.")
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteSecurity().run_standalone())
