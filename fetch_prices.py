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

    BG       = "#ffffff"
    GRID     = "#e5e7eb"
    TEXT     = "#111827"
    SUBTEXT  = "#6b7280"

    colors = {
        "Gasolina 95":    "#2563eb",
        "Gasolina 98":    "#7c3aed",
        "Diésel":         "#d97706",
        "Diésel Premium": "#dc2626",
        "GLP":            "#059669",
    }

    fig, ax = plt.subplots(figsize=(15, 6))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    date_range_days = (df["Fecha"].max() - df["Fecha"].min()).days

    endpoints = []
    for col in available:
        series = df[["Fecha", col]].dropna()
        if series.empty:
            continue
        ax.plot(
            series["Fecha"],
            series[col],
            color=colors.get(col, "#888888"),
            linewidth=2.0,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=2,
        )
        last_x = series["Fecha"].iloc[-1]
        last_y = series[col].iloc[-1]
        ax.scatter([last_x], [last_y], color=colors.get(col, "#888888"), s=22, zorder=3)
        endpoints.append({
            "col": col,
            "x": last_x,
            "y": last_y,
            "label_y": last_y,
            "color": colors.get(col, "#888888"),
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
        needs_connector = abs(ep["label_y"] - ep["y"]) > min_gap * 0.3
        ax.text(
            1.015, ep["label_y"],
            f"{ep['col']}  {ep['y']:.4f} €",
            transform=blended,
            va="center",
            ha="left",
            color=ep["color"],
            fontsize=8.5,
            fontweight="bold",
            clip_on=False,
        )
        if needs_connector:
            ax.annotate(
                "",
                xy=(ep["x"], ep["y"]),
                xytext=(ep["x"], ep["label_y"]),
                textcoords="data",
                annotation_clip=False,
                arrowprops=dict(arrowstyle="-", color=ep["color"], alpha=0.25, lw=0.6),
            )

    # X-axis adaptive tick interval
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

    fig.autofmt_xdate(rotation=0, ha="center")
    ax.tick_params(axis="x", length=0, labelsize=8, colors=SUBTEXT, pad=6)
    ax.tick_params(axis="y", length=0, labelsize=8, colors=SUBTEXT)

    # Y-axis on the right, formatted with € symbol
    ax.yaxis.set_label_position("right")
    ax.yaxis.tick_right()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.2f} €"))

    # Minimal spines: only thin bottom line
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_linewidth(0.6)
    ax.spines["bottom"].set_color(GRID)

    # Subtle horizontal grid only
    ax.yaxis.grid(True, linestyle=(0, (1, 3)), linewidth=0.6, color=GRID, zorder=0)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    ax.set_xlabel("")
    ax.set_ylabel("")

    # Title block — left-aligned
    fig.text(
        0.01, 0.97,
        "Media nacional de precios de carburantes",
        ha="left", va="top",
        fontsize=13, fontweight="bold",
        color=TEXT,
        transform=fig.transFigure,
    )
    fig.text(
        0.01, 0.91,
        f"€/litro  ·  Último dato: {run_date_str} a las {run_time_str} hora española",
        ha="left", va="top",
        fontsize=9,
        color=SUBTEXT,
        transform=fig.transFigure,
    )

    # Footer
    fig.text(
        0.01, 0.02,
        "Fuente: MITECO | Gráfico: @poloi.eurosky.social",
        ha="left", va="bottom",
        fontsize=7.5,
        color=SUBTEXT,
        transform=fig.transFigure,
    )

    plt.tight_layout(rect=[0, 0.06, 0.80, 0.88])
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
