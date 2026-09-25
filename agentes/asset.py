"""
Agente Asset (Asset Rentas Residenciales, Asset Outlets Vivo, Asset
Desarrollo Chamisero).

Particularidad (Categoria C -- documento equivocado): assetagf.com muestra
los 3 fondos como pestañas (tabs) dentro de una misma pagina
(fondos-de-inversion/); el ultimo re-scrapeo no pudo cargar el sitio y el
archivo que quedo descargado para los 3 fondos es el mismo "Informe de
Auditor" de Asset Rentas Residenciales, reciclado por error -- no es un
factsheet y no tiene datos de rentabilidad utilizables.

Ya se ubico manualmente el Folleto Informativo correcto para "Asset Rentas
Residenciales" (carpeta 4-Informacion de Interes / 5-Folleto Informativo,
trimestral, en el sitio de la administradora); falta ubicar los de "Outlets
Vivo" y "Desarrollo Chamisero" navegando a su pestaña especifica. Ver
fondos_pendientes.xlsx para el detalle completo.

descargar() no esta sobreescrito: hay que volver a intentarlo navegando a la
pestaña de cada fondo (AgenteBase.descargar() generico no distingue tabs de
una SPA), y por eso queda documentado aqui en vez de forzarlo sin validar
contra el sitio real.
"""
from __future__ import annotations

from pathlib import Path

from agentes.base import AgenteBase, registro_vacio


class AgenteAsset(AgenteBase):
    administradora = "Asset"

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        if info.get("tiene_texto"):
            texto = self._texto_pdf(pdf_path)
            info["es_informe_auditor"] = "informe del auditor" in texto.lower() or "opinión" in texto.lower()
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        r["estado_categoria"] = "C"
        r["estado"] = "Sitio caido durante el re-scrapeo (assetagf.com no respondio)"
        r["notas"] = ("El archivo actual es un Informe de Auditor de 'Asset Rentas Residenciales' "
                      "reciclado para los 3 fondos (documento incorrecto, sin datos de rentabilidad). "
                      "Reintentar navegando a la pestaña especifica de cada fondo en "
                      "https://assetagf.com/fondos-de-inversion/")
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteAsset().run_standalone())
