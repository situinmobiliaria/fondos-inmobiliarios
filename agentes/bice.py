"""
Agente BICE (Rentas Inmobiliarias).

Categoria B -- sitio bloquea automatizacion. banco.bice.cl devuelve 403 /
Cloudflare incluso con navegador headless real (probado en la sesion
anterior). Por instruccion explicita del usuario (INSTRUCCIONES_VSCODE.txt,
seccion 4) NO se debe insistir con tecnicas para evadir el bloqueo.

descargar() esta sobreescrito para retornar None de inmediato (en vez de
heredar el intento generico de AgenteBase, que solo gastaria tiempo contra
un sitio que ya sabemos que bloquea) y dejar instrucciones claras de
descarga manual.
"""
from __future__ import annotations

from pathlib import Path

from agentes.base import AgenteBase, registro_vacio

URL_FONDO = (
    "https://banco.bice.cl/inversiones/fondos-de-inversion/"
    "bice-rentas-inmobiliarias-fondo-de-inversion"
)


class AgenteBICE(AgenteBase):
    administradora = "BICE"

    async def descargar(self, fondo: dict, browser):
        # No reintentar: el sitio rechaza la automatizacion de forma
        # consistente. Requiere descarga manual (ver notas en extraer()).
        return None

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        r["estado_categoria"] = "B"
        r["estado"] = "Sitio bloquea automatizacion (HTTP 403, Cloudflare/anti-bot bancario)"
        r["notas"] = (f"El archivo actual es el Reglamento Interno del fondo, no la ficha. "
                      f"Descarga manual requerida desde {URL_FONDO} y guardar en "
                      f"'Fondos Descargados/BICE/Rentas Inmobiliarias/'.")
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteBICE().run_standalone())
