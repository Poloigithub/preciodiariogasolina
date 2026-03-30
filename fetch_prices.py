#!/usr/bin/env python3
"""
Obtiene la media de precios de carburantes por tipo a nivel nacional
desde la API del Ministerio de Transición Ecológica y guarda los datos
en un CSV. También genera una gráfica de líneas en PNG.
"""

import csv
import os
import sys
from datetime import datetime, date

import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

API_URL = (
    "https://sedeaplicaciones.minetur.gob.es"
    "/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"
)

CSV_FILE = "precios_carburantes.csv"
CHART_FILE = "precios_carburantes.png"

# Mapeo de campo API → nombre legible
FUEL_FIELDS = {
    "Precio Gasolina 95 E5": "Gasolina 95 E5",
    "Precio Gasolina 98 E5": "Gasolina 98 E5",
    "Precio Gasoleo A": "Gasóleo A",
    "Precio Gasoleo Premium": "Gasóleo Premium",
    "Precio Gasoleo B": "Gasóleo B",
    "Precio Gases licuados del petróleo": "GLP",
    "Precio Gas Natural Comprimido": "Gas Natural Comprimido",
    "Precio Gas Natural Licuado": "Gas Natural Licuado",
    "Precio Hidrogeno": "Hidrógeno",
}


def parse_price(value: str) -> float | None:
    """Convierte un precio en string (coma decimal) a float. Devuelve None si está vacío."""
    value = value.strip()
    if not value:
        return None
    return float(value.replace(",", "."))


def fetch_averages() -> dict[str, float | None]:
    """Llama a la API y calcula la media nacional por tipo de carburante."""
    response = requests.get(API_URL, timeout=30)
    response.raise_for_status()
    data = response.json()

    stations = data.get("ListaEESSPrecio", [])
    if not stations:
        raise ValueError("La API devolvió una lista de estaciones vacía.")

    totals: dict[str, list[float]] = {field: [] for field in FUEL_FIELDS}

    for station in stations:
        for api_field in FUEL_FIELDS:
            price = parse_price(station.get(api_field, ""))
            if price is not None and price > 0:
                totals[api_field].append(price)

    averages: dict[str, float | None] = {}
    for api_field, label in FUEL_FIELDS.items():
        values = totals[api_field]
        averages[label] = round(sum(values) / len(values), 4) if values else None

    return averages


def append_to_csv(today: date, averages: dict[str, float | None]) -> None:
    """Añade una fila con la fecha y los precios medios al CSV."""
    date_str = today.strftime("%Y-%m-%d")
    labels = list(FUEL_FIELDS.values())
    fieldnames = ["Fecha"] + labels

    file_exists = os.path.isfile(CSV_FILE)

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        row: dict = {"Fecha": date_str}
        for label in labels:
            value = averages.get(label)
            row[label] = f"{value:.4f}" if value is not None else ""
        writer.writerow(row)

    print(f"[CSV] Fila añadida para {date_str}")


def generate_chart() -> None:
    """Lee el CSV completo y genera una gráfica de líneas en PNG."""
    df = pd.read_csv(CSV_FILE, parse_dates=["Fecha"])
    df = df.sort_values("Fecha")

    fuel_columns = [c for c in df.columns if c != "Fecha"]

    # Filtrar columnas que tengan al menos un valor no nulo
    available = [c for c in fuel_columns if df[c].notna().any()]

    if not available:
        print("[Chart] No hay datos suficientes para generar la gráfica.")
        return

    fig, ax = plt.subplots(figsize=(14, 7))

    for col in available:
        series = df[["Fecha", col]].dropna()
        if series.empty:
            continue
        ax.plot(series["Fecha"], series[col], marker="o", markersize=4, label=col)

    ax.set_title("Media nacional de precios de carburantes (€/litro)", fontsize=14, pad=15)
    ax.set_xlabel("Fecha")
    ax.set_ylabel("€/litro")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=45)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(CHART_FILE, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[Chart] Gráfica guardada en {CHART_FILE}")


def main() -> None:
    today = date.today()
    print(f"[Info] Obteniendo precios para {today}…")

    averages = fetch_averages()

    print("[Info] Medias nacionales:")
    for label, value in averages.items():
        display = f"{value:.4f} €/l" if value is not None else "sin datos"
        print(f"  {label}: {display}")

    append_to_csv(today, averages)
    generate_chart()
    print("[Info] Proceso completado.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[Error] {exc}", file=sys.stderr)
        sys.exit(1)
