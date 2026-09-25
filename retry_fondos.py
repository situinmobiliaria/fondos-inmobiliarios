"""
Re-procesa solo los fondos que no tienen archivo descargado.
Lee registro_rentabilidad.xlsx, filtra estados fallidos y vuelve a scrapear.
"""

import asyncio
import sys
from pathlib import Path

import openpyxl

# Importa todo del scraper principal
from scraper_fondos import (
    leer_fondos, inicializar_registro, scrape_fondo,
    OUTPUT_DIR, REGISTRO_FILE
)

ESTADOS_EXITOSOS = {"descargado", "descargado (fallback)", "descargado (nueva tab)",
                    "descargado (visor)", "descargado (contenido)"}


def fondos_sin_descarga() -> set[tuple]:
    """Devuelve set de (administradora, nombre) que no tienen descarga exitosa."""
    if not Path(REGISTRO_FILE).exists():
        return set()
    wb = openpyxl.load_workbook(REGISTRO_FILE)
    ws = wb["Registro"]
    exitosos = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        administradora, nombre, _, _, estado = row[1], row[2], row[3], row[4], row[13]
        if estado and any(e in str(estado) for e in ESTADOS_EXITOSOS):
            exitosos.add((administradora, nombre))
    return exitosos


async def main():
    from playwright.async_api import async_playwright
    from datetime import datetime

    print("=" * 60)
    print("  Retry: Fondos sin descarga")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    todos = leer_fondos()
    exitosos = fondos_sin_descarga()

    pendientes = [
        f for f in todos
        if (f["administradora"], f["nombre"]) not in exitosos
    ]

    if not pendientes:
        print("\nTodos los fondos ya tienen descarga exitosa.")
        return

    print(f"\nFondos a reintentar: {len(pendientes)}")
    for f in pendientes:
        print(f"  - [{f['administradora']}] {f['nombre']}")

    wb = inicializar_registro()
    OUTPUT_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        for i, fondo in enumerate(pendientes, 1):
            print(f"\n[{i}/{len(pendientes)}] {fondo['nombre']}")
            await scrape_fondo(browser, fondo, wb)
            await asyncio.sleep(2)
        await browser.close()

    print("\n" + "=" * 60)
    print("  Retry completo.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
