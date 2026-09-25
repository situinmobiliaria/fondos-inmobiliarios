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

Un solo comando deja todo al día: descarga (si falta el PDF más reciente — si ya está el último no lo vuelve a bajar), extrae rentabilidad, actualiza `registro_rentabilidad.xlsx` (hojas **Registro** e **Historico**) y `fondos_data.json`, regenera `diagnostico_fondos.xlsx`, y al final regenera `dashboard_fondos.html` y `docs/index.html` automáticamente.

La hoja **Historico** de `registro_rentabilidad.xlsx` guarda una fila por fondo y por fecha de reporte (no se pisa entre corridas), para ver la evolución en el tiempo — el dashboard la usa para el mini-gráfico de evolución en la ficha de cada fondo.

## Regenerar solo el diagnóstico o el dashboard

```
python build_diagnostico.py   # diagnostico_fondos.xlsx
python build_dashboard.py     # dashboard_fondos.html + docs/index.html
```

`dashboard_fondos.html` es un archivo único que se abre con doble clic (los datos **y Chart.js** quedan incrustados adentro — funciona sin internet). `docs/index.html` es una copia idéntica pensada para publicarse con GitHub Pages.

Si se actualiza Chart.js alguna vez, hay que volver a descargar el bundle una vez a mano:
```
curl -L "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.1/chart.umd.min.js" -o vendor/chart.umd.min.js
```

## Probar un agente aislado

```
python -m agentes.toesca
python -m agentes.btg
```

Corre `descargar()` + `inspeccionar()` + `extraer()` solo para los fondos de esa administradora, usando el PDF ya descargado si existe.

## Estructura

- `agentes/base.py` — clase base (`descargar`, `inspeccionar`, `extraer`) + utilidades de parsing de texto PDF, incluyendo `leer_ultimo_valor_grafico()` (lee valores de gráficos cuyas etiquetas de dato son texto real en el PDF, separándolas por posición del eje).
- `agentes/<administradora>.py` — un agente por administradora, con las particularidades de su sitio/factsheet documentadas en el docstring.
- `master.py` — orquestador (descarga + extrae + registro + histórico + diagnóstico + dashboard, todo en un comando).
- `build_diagnostico.py` / `build_dashboard.py` — generan los dos entregables de reporte.
- `registro_rentabilidad.xlsx` — hoja **Registro** (una fila por fondo, estado actual) + hoja **Historico** (una fila por fondo y fecha de reporte).
- `diagnostico_fondos.xlsx` — categoría de problema (A-G / OK) por fondo.
- `fondos_data.json` — mismos datos en JSON (no usado por el dashboard, que ya trae los datos incrustados; queda como referencia/export).
- `vendor/chart.umd.min.js` — Chart.js descargado una vez, para que el dashboard no dependa de internet.
- `docs/index.html` — copia del dashboard para publicar con GitHub Pages.

## Repositorio

Código y factsheets viven en `github.com/situinmobiliaria/fondos-inmobiliarios` (repo público — se decidió así para poder usar GitHub Pages con el plan actual de la organización). Dashboard publicado en **https://situinmobiliaria.github.io/fondos-inmobiliarios/**.

## Limitaciones conocidas

- **Ameris y Asset**: sus agentes (`agentes/ameris.py`, `agentes/asset.py`) tienen la lógica de navegación (clic en categoría → clic en fondo → expandir documentos) escrita según capturas de pantalla, pero **no se pudo probar contra el sitio real** (este entorno de desarrollo no tiene acceso a internet). Correr `python -m agentes.ameris` / `python -m agentes.asset` con conexión real para validar y ajustar selectores si hace falta.
- **BICE**: bloqueo anti-bot confirmado, requiere descarga manual (ver notas del agente).
- **Santander**: PDF escaneado, requiere instalar OCR (ver sección de instalación).
- **Credicorp / Frontal Trust**: son fondos de desarrollo/liquidación, sus informes no traen una tabla de rentabilidad periódica — se extraen menciones sueltas de rentabilidad del texto libre cuando existen (ver Notas de cada fondo), pero la mayoría queda sin dato porque genuinamente no está publicado.
