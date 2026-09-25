"""
Agente Zurich (Renta Residencial I).

Mismo caso que Inversiones Security: el documento es un "Folleto
Informativo" tipo KIID (formato LVA Indices), con la rentabilidad en el
grafico "Mejores y Peores Rentabilidades | Ultimos 5 anos" sin etiquetas de
periodo asociadas en el texto extraido -> Categoria E confirmada.
"""
from __future__ import annotations

from pathlib import Path

from agentes.base import AgenteBase, registro_vacio, extraer_metadatos_comunes


class AgenteZurich(AgenteBase):
    administradora = "Zurich"

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        texto = self._texto_pdf(pdf_path)
        r.update(extraer_metadatos_comunes(texto))
        r["moneda"] = "CLP"  # tabla "Administradora Run Moneda Patrimonio...": CLP
        r["estado_categoria"] = "E"
        r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"
        r["notas"] = ("Folleto Informativo tipo KIID (LVA Indices): 'Mejores y Peores Rentabilidades "
                      "Ultimos 5 anos' como grafico de barras sin etiquetas de periodo en el texto extraido.")
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteZurich().run_standalone())
