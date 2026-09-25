"""
Agente Ameris (7 fondos: Renta Industrial II, Renta Reisdencial, Rentas y
Desarrollos Aconcagua, Desarrollo Inmobiliario IX, UPC Desarrollo
Inmobiliario, Desarrollo Inmobiliario Uno, Megacentro Buenaventura).

Particularidades:
- ameris.cl no publica un factsheet por fondo en su sitio publico -- solo un
  link generico a "asset-management/real-state". Para 3 fondos (Desarrollo
  Inmobiliario IX, Renta Reisdencial, UPC Desarrollo Inmobiliario) se
  consiguio un "informe mensual" exportado desde Power BI, que trae
  graficos (evolucion de valor cuota, dividendos) pero NINGUNA tabla
  numerica de rentabilidad en el texto -- se confirma Categoria E.
- Para los otros 4 fondos no se encontro ni siquiera ese informe: lo unico
  disponible son los Estados Financieros (EEFF), que no traen rentabilidad
  periodica -> Categoria G (administradora no publica factsheet), igual que
  en el diagnostico original. Ver fondos_pendientes.xlsx para el detalle de
  que se necesitaria (confirmar con la administradora si existe un factsheet
  en otro canal).
"""
from __future__ import annotations

from pathlib import Path

from agentes.base import AgenteBase, registro_vacio, extraer_metadatos_comunes

SIN_FACTSHEET = {
    "Renta Industrial II", "Rentas y Desarrollos Aconcagua",
    "Desarrollo Inmobiliario Uno", "Megacentro Buenaventura",
}


class AgenteAmeris(AgenteBase):
    administradora = "Ameris"

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()
        nombre_fondo = pdf_path.parent.name
        texto = self._texto_pdf(pdf_path)
        r.update(extraer_metadatos_comunes(texto))

        if nombre_fondo in SIN_FACTSHEET:
            r["estado_categoria"] = "G"
            r["estado"] = "La administradora no publica factsheet/ficha para este fondo"
            r["notas"] = "Se descargaron los Estados Financieros como mejor alternativa disponible; no contienen rentabilidad periodica lista para usar."
        else:
            r["estado_categoria"] = "E"
            r["estado"] = "OK - documento correcto, pero rentabilidad en formato grafico (no extraible por texto)"
            r["notas"] = "Informe mensual exportado de Power BI: solo trae graficos (valor cuota, dividendos), sin tabla numerica de rentabilidad."
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteAmeris().run_standalone())
