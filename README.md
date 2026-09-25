# Scraper de Fondos Inmobiliarios

## Instalar dependencias

```
pip install pandas openpyxl pdfplumber playwright requests
python -m playwright install chromium
```

Para el fondo de Santander (PDF escaneado, categoría D) hace falta además, si se quiere hacer OCR:

```
pip install pytesseract pdf2image
```

más el binario de **Tesseract-OCR** y **poppler** instalados en el sistema (no vienen con pip).

## Correr todo

```
python master.py                     # todas las administradoras migradas
python master.py --adm "BTG Pactual" # solo una administradora
python master.py --solo-fallidos     # solo reprocesa fondos que no están OK
```

Esto descarga (si falta el PDF), extrae rentabilidad, actualiza `registro_rentabilidad.xlsx` y `fondos_data.json`, y regenera `diagnostico_fondos.xlsx`.

## Regenerar solo el diagnóstico o el dashboard

```
python build_diagnostico.py   # diagnostico_fondos.xlsx
python build_dashboard.py     # dashboard_fondos.html
```

`dashboard_fondos.html` es un archivo único que se abre con doble clic (los datos quedan incrustados adentro). Los gráficos usan Chart.js desde CDN, así que necesita conexión a internet la primera vez que se abre; si no hay internet, la tabla y los filtros funcionan igual.

## Probar un agente aislado

```
python -m agentes.toesca
python -m agentes.btg
```

Corre `descargar()` + `inspeccionar()` + `extraer()` solo para los fondos de esa administradora, usando el PDF ya descargado si existe.

## Estructura

- `agentes/base.py` — clase base (`descargar`, `inspeccionar`, `extraer`) + utilidades de parsing de texto PDF.
- `agentes/<administradora>.py` — un agente por administradora, con las particularidades de su sitio/factsheet documentadas en el docstring.
- `master.py` — orquestador.
- `build_diagnostico.py` / `build_dashboard.py` — generan los dos entregables de reporte.
- `registro_rentabilidad.xlsx` — una fila por fondo con los indicadores.
- `diagnostico_fondos.xlsx` — categoría de problema (A-G / OK) por fondo.
- `fondos_data.json` — mismos datos en JSON, usado por el dashboard.
