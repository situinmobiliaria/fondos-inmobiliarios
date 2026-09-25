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

Segunda relectura (a pedido del usuario, "haz el esfuerzo de leer"): 2 de los
11 fondos (Renta Residencial II y III) SI traen una tabla limpia de "Valor
cuota" con dos filas fechadas -- "Inicio (DD-MM-AAAA) <valor>" y "Actual
(DD-MM-AAAA) <valor>". Con eso se puede CALCULAR una rentabilidad acumulada
desde el inicio (tecnica 4 de la Ronda 2, seccion 2.1: calcular desde valor
cuota cuando no hay tabla de rentabilidad). Ojo: es solo variacion de PRECIO
de la cuota entre esas 2 fechas -- no incluye dividendos repartidos en el
camino ni esta anualizada, asi que NO es directamente comparable con la
columna "Rent. Desde Inicio" de otras administradoras (que si suele incluir
dividendos). Por eso el valor va igual a esa columna (es lo mas parecido que
hay en el esquema), pero con una nota bien explicita sobre la diferencia de
metodologia. Para los otros 9 fondos se busco el mismo patron y no aparece
(o solo hay un valor de cuota inicial, sin un valor actual/reciente en texto
limpio) -- ahi si se mantiene la Categoria E.
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

_PATRON_ACTUAL = re.compile(r"Actual\s*\(([\d-]+)\)\s*([\d.,]+)")
_PATRON_INICIO = re.compile(r"Inicio\s*\(([\d-]+)\)\s*([\d.,]+)")


def _num_cl(s: str) -> float:
    """'33.885,00' (formato chileno: punto=miles, coma=decimal) -> 33885.00"""
    return float(s.replace(".", "").replace(",", "."))


def _calcular_rent_desde_valor_cuota(texto: str) -> tuple[str, str] | tuple[None, None]:
    """Busca las filas 'Inicio (fecha) valor' y 'Actual (fecha) valor' de la
    tabla de Valor Cuota y devuelve (rentabilidad_pct, nota) o (None, None) si
    no encuentra ambas filas."""
    m_ini = _PATRON_INICIO.search(texto)
    m_act = _PATRON_ACTUAL.search(texto)
    if not (m_ini and m_act):
        return None, None
    try:
        v_ini = _num_cl(m_ini.group(2))
        v_act = _num_cl(m_act.group(2))
    except ValueError:
        return None, None
    if v_ini <= 0:
        return None, None
    pct = (v_act / v_ini - 1) * 100
    nota = (f"Calculado desde Valor Cuota: {m_ini.group(2)} el {m_ini.group(1)} -> "
            f"{m_act.group(2)} el {m_act.group(1)}. Es variacion de PRECIO de la cuota "
            f"solamente (no incluye dividendos repartidos en el camino) y no esta "
            f"anualizada -- no es directamente comparable con 'Desde Inicio' de otras "
            f"administradoras, que si suele incluir dividendos.")
    return f"{pct:.2f}".replace(".", ","), nota


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

        calculado_desde_cuota = False
        if not r.get("Rent. Desde Inicio"):
            pct, nota_calc = _calcular_rent_desde_valor_cuota(texto)
            if pct:
                r["Rent. Desde Inicio"] = pct
                notas_extra = (notas_extra + " " if notas_extra else "") + nota_calc
                calculado_desde_cuota = True

        if r.get("Rent. Desde Inicio"):
            r["estado_categoria"] = "F"
            r["estado"] = ("Rentabilidad calculada desde Valor Cuota (Inicio vs Actual)" if calculado_desde_cuota
                            else "Rentabilidad extraida parcialmente (mencion suelta en texto libre)")
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"

        r["notas"] = ("Reporte de fondo de desarrollo/en liquidacion: no trae tabla estandar de "
                      "rentabilidad periodica. " + notas_extra).strip()
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteCredicorp().run_standalone())
