"""
Agente Credicorp (11 fondos: Aconcagua II/III, Capital Raices, Plaza Egaña,
Preferente Maestra II, Renta Industrial I, Renta Inmobiliaria II, Renta
Residencial I/II/III, Retorno Preferente Maestra I).

Particularidad (confirmada revisando el texto de varios fondos de la
familia): los factsheets de Credicorp para estos fondos son reportes de
fondos de DESARROLLO / EN LIQUIDACION -- describen avance de proyectos,
balance y comentarios del administrador, pero NO traen una tabla estandar de
"Rentabilidad 1M/3M/12M/YTD" como los fondos de renta de otras
administradoras. La unica cifra de rentabilidad que aparece es, cuando
existe, una mencion suelta en el texto libre del comentario (ej.
"alcanzando una rentabilidad actual de UF+15,88%" o "Rentabilidad esperada
para el aportante: UF + 6,4%"), que no es comparable entre fondos ni entre
periodos -- no es una tabla de rentabilidad periodica, es una proyeccion o
un acumulado desde el inicio mencionado en prosa.

Por eso este agente no intenta parsear esas menciones sueltas (arriesgaria
mezclar "rentabilidad esperada" con "rentabilidad realizada", o tomar un
numero de otra frase por error) y mantiene estos 11 fondos en Categoria E,
con la nota especifica de por que no hay tabla que extraer.
"""
from __future__ import annotations

from pathlib import Path

from agentes.base import AgenteBase, registro_vacio, extraer_metadatos_comunes


class AgenteCredicorp(AgenteBase):
    administradora = "Credicorp"

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        texto = self._texto_pdf(pdf_path)
        r.update(extraer_metadatos_comunes(texto))
        # Moneda no se fija: estos fondos reportan valor cuota en CLP y en UF
        # simultaneamente (columnas paralelas) segun el fondo, sin una unica
        # "moneda del fondo" declarada -> se deja vacio en vez de adivinar.
        r["estado_categoria"] = "E"
        r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"
        r["notas"] = ("Reporte de fondo de desarrollo/en liquidacion: no trae tabla estandar de "
                      "rentabilidad periodica, solo menciones sueltas en el comentario del administrador "
                      "(rentabilidad esperada o acumulada desde el inicio, no comparable entre fondos).")
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteCredicorp().run_standalone())
