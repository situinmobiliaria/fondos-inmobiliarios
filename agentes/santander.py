"""
Agente Santander (Rentas Residenciales).

Categoria D -- el PDF descargado no tiene ninguna capa de texto (las 7
paginas devuelven '' con pdfplumber): es un escaneo/imagen.

Este agente intenta OCR con pytesseract + pdf2image SI estan instalados,
pero no los instala por si solo -- por instruccion del usuario
(INSTRUCCIONES_VSCODE.txt, seccion 4) hay que avisar que instalar antes de
correr OCR. En este entorno no estan disponibles (pytesseract / ocrmypdf /
poppler), asi que por ahora extraer() devuelve Categoria D con la nota de
que falta instalar:

    pip install pytesseract pdf2image
    + Tesseract-OCR (binario) y poppler (para pdf2image) en el PATH

Alternativa mencionada en fondos_pendientes.xlsx: ubicar una version
"nativa" (no escaneada) del mismo documento en el sitio de
santanderassetmanagement.cl.
"""
from __future__ import annotations

from pathlib import Path

from agentes.base import AgenteBase, registro_vacio


class AgenteSantander(AgenteBase):
    administradora = "Santander"

    def inspeccionar(self, pdf_path: Path) -> dict:
        info = super().inspeccionar(pdf_path)
        info["requiere_ocr"] = not info.get("tiene_texto")
        return info

    def extraer(self, pdf_path: Path) -> dict:
        r = registro_vacio()

        try:
            import pytesseract  # noqa: F401
            from pdf2image import convert_from_path  # noqa: F401
            ocr_disponible = True
        except ImportError:
            ocr_disponible = False

        if not ocr_disponible:
            r["estado_categoria"] = "D"
            r["estado"] = "PDF sin capa de texto (parece escaneado / imagen)"
            r["notas"] = ("pdfplumber no pudo extraer ningun texto del documento. Para OCR falta instalar: "
                          "pip install pytesseract pdf2image, + Tesseract-OCR y poppler en el PATH. "
                          "Alternativa: buscar una version nativa (no escaneada) en santanderassetmanagement.cl.")
            return r

        # Si en el futuro se instalan las dependencias, aqui se agregaria el
        # OCR pagina por pagina y luego se reutilizaria un extractor de texto
        # como en los demas agentes. Placeholder por ahora.
        r["estado_categoria"] = "D"
        r["estado"] = "OCR disponible pero extractor especifico aun no implementado"
        return r


if __name__ == "__main__":
    import asyncio
    asyncio.run(AgenteSantander().run_standalone())
