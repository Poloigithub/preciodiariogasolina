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
    except (ImportError, KeyError):
        now_spain = datetime.now()

    run_date_str = now_spain.strftime("%d/%m/%Y")
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
        "Diésel Premium": "#E53935",
        "GLP": "#43A047",
    }

    fig, ax = plt.subplots(figsize=(15, 6))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    date_range_days = (df["Fecha"].max() - df["Fecha"].min()).days

    endpoints = []
    for col in available:
        series = df[["Fecha", col]].dropna()
        if series.empty:
            continue
        ax.plot(
            series["Fecha"],
            series[col],
            marker="o",
            markersize=3,
            linewidth=1.8,
            color=colors.get(col),
            alpha=0.95,
        )
        endpoints.append({
            "col": col,
            "x": series["Fecha"].iloc[-1],
            "y": series[col].iloc[-1],
            "label_y": series[col].iloc[-1],
            "color": colors.get(col),
        })

    # Anti-overlap: spread labels that are too close
    y_vals = [e["y"] for e in endpoints]
    y_range = max(y_vals) - min(y_vals) if len(y_vals) > 1 else 1.0
    min_gap = y_range * 0.07
    endpoints.sort(key=lambda e: e["label_y"])
    for i in range(1, len(endpoints)):
        if endpoints[i]["label_y"] - endpoints[i - 1]["label_y"] < min_gap:
            endpoints[i]["label_y"] = endpoints[i - 1]["label_y"] + min_gap

    import matplotlib.transforms as _transforms
    blended = _transforms.blended_transform_factory(ax.transAxes, ax.transData)

    for ep in endpoints:
        needs_arrow = abs(ep["label_y"] - ep["y"]) > min_gap * 0.3
        # Draw label just outside the right edge of the axes
        ax.text(
            1.01, ep["label_y"],
            f"{ep['col']}: {ep['y']:.4f} €",
            transform=blended,
            va="center",
            ha="left",
            color=ep["color"],
            fontsize=8.5,
            fontweight="bold",
            clip_on=False,
        )
        # Draw a subtle connector line when label was shifted
        if needs_arrow:
            ax.annotate(
                "",
                xy=(ep["x"], ep["y"]),
                xytext=(ep["x"], ep["label_y"]),
                textcoords="data",
                annotation_clip=False,
                arrowprops=dict(arrowstyle="-", color=ep["color"], alpha=0.3, lw=0.7),
            )

    # X-axis: pick tick interval based on date range
    if date_range_days <= 14:
        ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    elif date_range_days <= 90:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    elif date_range_days <= 365:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b '%y"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))

    fig.autofmt_xdate(rotation=40, ha="right")
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=9)

    ax.set_title(
        "Media nacional de precios de carburantes (€/litro)",
        fontsize=14,
        fontweight="bold",
        pad=10,
        color="#212121",
    )
    ax.set_xlabel("")
    ax.set_ylabel("€/litro", fontsize=10, color="#555555")

    ax.grid(True, linestyle="--", alpha=0.35, color="#BBBBBB")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_alpha(0.3)
    ax.spines["bottom"].set_alpha(0.3)

    fig.text(
        0.5, 0.97,
        f"Último dato tomado el {run_date_str} a las {run_time_str} hora española",
        ha="center",
        fontsize=9,
        color="#666666",
        transform=fig.transFigure,
    )
    fig.text(
        0.5, 0.01,
        "Fuente: MITECO | Gráfico: @poloi.eurosky.social",
        ha="center",
        fontsize=8,
        color="#999999",
    )

    plt.tight_layout(rect=[0, 0.04, 0.82, 0.94])
    plt.savefig(CHART_FILE, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
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
