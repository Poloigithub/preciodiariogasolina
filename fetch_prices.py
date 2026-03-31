#!/usr/bin/env python3
"""
Obtiene la media de precios nacionales de gasolinas, diésel y GLP
desde la API del Ministerio de Transición Ecológica.
Guarda los datos en CSV y genera una gráfica de líneas en PNG.
"""

import csv
import os
import sys
from datetime import date, datetime

import ssl
import time
import urllib3

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LegacyTLSAdapter(HTTPAdapter):
    """Adaptador que relaja las restricciones TLS para servidores del gobierno."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)
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

FUEL_FIELDS = {
    "Precio Gasolina 95 E5": "Gasolina 95",
    "Precio Gasolina 98 E5": "Gasolina 98",
    "Precio Gasoleo A": "Diésel",
    "Precio Gasoleo Premium": "Diésel Premium",
    "Precio Gases licuados del petróleo": "GLP",
}


def parse_price(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    return float(value.replace(",", "."))


def fetch_averages() -> dict[str, float | None]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }
    retry = Retry(total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session = requests.Session()
    session.mount("https://", LegacyTLSAdapter(max_retries=retry))

    response = session.get(API_URL, headers=headers, timeout=30, verify=False)
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
    labels = list(FUEL_FIELDS.values())
    fieldnames = ["Fecha"] + labels
    file_exists = os.path.isfile(CSV_FILE)

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        row: dict = {"Fecha": today.strftime("%Y-%m-%d")}
        for label in labels:
            value = averages.get(label)
            row[label] = f"{value:.4f}" if value is not None else ""
        writer.writerow(row)

    print(f"[CSV] Fila añadida para {today}")


def generate_chart() -> None:
    try:
        from zoneinfo import ZoneInfo
        now_spain = datetime.now(ZoneInfo("Europe/Madrid"))
    except ImportError:
        now_spain = datetime.now()
    run_time_str = now_spain.strftime("%H:%M")

    df = pd.read_csv(CSV_FILE, parse_dates=["Fecha"])
    df = df.sort_values("Fecha")

    fuel_columns = [c for c in df.columns if c != "Fecha"]
    available = [c for c in fuel_columns if df[c].notna().any()]

    if not available:
        print("[Chart] No hay datos suficientes para generar la gráfica.")
        return

    colors = {
        "Gasolina 95": "#2196F3",
        "Gasolina 98": "#9C27B0",
        "Diésel": "#FF9800",
        "Diésel Premium": "#F44336",
        "GLP": "#4CAF50",
    }

    fig, ax = plt.subplots(figsize=(13, 6))

    for col in available:
        series = df[["Fecha", col]].dropna()
        if series.empty:
            continue
        ax.plot(
            series["Fecha"],
            series[col],
            marker="o",
            markersize=4,
            linewidth=2,
            color=colors.get(col),
        )
        last_x = series["Fecha"].iloc[-1]
        last_y = series[col].iloc[-1]
        ax.annotate(
            f"{col}: {last_y:.4f} €",
            xy=(last_x, last_y),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            color=colors.get(col),
            fontsize=8.5,
            fontweight="bold",
        )

    ax.set_title(
        f"Media nacional de precios de carburantes (€/litro)\n"
        f"Último dato tomado a las {run_time_str} hora española",
        fontsize=13,
        pad=15,
    )
    ax.set_xlabel("Fecha")
    ax.set_ylabel("€/litro")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=45)
    ax.grid(True, linestyle="--", alpha=0.4)

    fig.text(
        0.5, 0.01,
        "Fuente: MITECO | Gráfico: @poloi.eurosky.social",
        ha="center",
        fontsize=8,
        color="#888888",
    )

    plt.tight_layout(rect=[0, 0.04, 1, 1])
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
