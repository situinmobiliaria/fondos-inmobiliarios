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

Ronda 2 (seccion 2.4) pide intentar extraer esas menciones sueltas de TIR /
rentabilidad / multiplo / dividendos a columnas si aparecen. Se intenta, pero
NO se escribe el numero en una columna de Rent./TIR estandar: revisando el
texto de varios fondos, esas menciones son casi siempre "rentabilidad
ESPERADA para el aportante" (una condicion contractual/objetivo, ej. "UF +
6,4%"), no un resultado medido -- mezclarla con la columna TIR (que en el
resto del registro significa TIR REALIZADA) seria enganoso. Por eso, cuando
se encuentra una mencion, queda literal en "Notas" (con la aclaracion de que
es objetivo, no realizada) y las columnas numericas se dejan vacias.
"""
from __future__ import annotations

import re
from pathlib import Path

from agentes.base import AgenteBase, registro_vacio, extraer_metadatos_comunes

# Frases que SI son un resultado (no un objetivo/proyeccion) -- si aparecen,
# es razonable llevarlas a "Rent. Desde Inicio" (rentabilidad acumulada desde
# el inicio del fondo, que es conceptualmente lo mismo que reportan las demas
# administradoras en esa columna, solo que en UF y mencionado en prosa).
_PATRON_REALIZADA = re.compile(
    r"rentabilidad[^%\d]{0,60}?(?:actual|acumulada)[^%\d]{0,20}?(-?\d+[.,]\d+)\s*%", re.IGNORECASE)
# Frases que son un objetivo/proyeccion contractual, NO un resultado -- van a
# Notas como texto, nunca a una columna numerica.
_PATRON_OBJETIVO = re.compile(
    r"[Rr]entabilidad esperada[^%\d]{0,40}?(-?\d+[.,]\d+)\s*%")


class AgenteCredicorp(AgenteBase):
    administradora = "Credicorp"

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        texto = self._texto_pdf(pdf_path)
        r.update(extraer_metadatos_comunes(texto))
        # Moneda no se fija: estos fondos reportan valor cuota en CLP y en UF
        # simultaneamente (columnas paralelas) segun el fondo, sin una unica
        # "moneda del fondo" declarada -> se deja vacio en vez de adivinar.

        notas_extra = ""
        # el texto suele venir con columnas mezcladas (ej. "rentabilidad\nObjetivo
        # del Fondo actual de UF+15,88%"), asi que se busca sobre una version sin
        # saltos de linea ademas de la version normal, para no perder el match
        texto_plano = re.sub(r"\s+", " ", texto)

        m_real = _PATRON_REALIZADA.search(texto) or _PATRON_REALIZADA.search(texto_plano)
        if m_real:
            r["Rent. Desde Inicio"] = m_real.group(1).replace(".", ",")
            notas_extra = "Rentabilidad 'Desde Inicio' leida del texto libre del comentario (UF), no de una tabla."

        m_obj = _PATRON_OBJETIVO.search(texto) or _PATRON_OBJETIVO.search(texto_plano)
        if m_obj:
            valor = m_obj.group(1).replace(".", ",")
            notas_extra = (notas_extra + " " if notas_extra else "") + \
                f"El PDF menciona una rentabilidad OBJETIVO (no realizada) de UF+{valor}% para el aportante; no se carga en ninguna columna para no confundirla con un resultado medido."

        if r.get("Rent. Desde Inicio"):
            r["estado_categoria"] = "F"
            r["estado"] = "Rentabilidad extraida parcialmente (mencion suelta en texto libre)"
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"

        r["notas"] = ("Reporte de fondo de desarrollo/en liquidacion: no trae tabla estandar de "
                      "rentabilidad periodica. " + notas_extra).strip()
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteCredicorp().run_standalone())
