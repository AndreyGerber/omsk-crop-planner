"""
Jährliche Abfrage langfristiger Wetterdaten je Zone.
Wird per GitHub Actions Cron einmal pro Jahr (1. Januar) ausgeführt (siehe
.github/workflows/yearly_weather.yml).

Berechnet ZWEI Zeitfenster parallel aus EINEM API-Call pro Zone:
- 10 Jahre: reagiert schneller auf aktuelle Verschiebungen (kurzfristigerer Trend)
- 30 Jahre: WMO-Standard für Klimanormalperioden, robuster gegen Einzeljahr-Ausreißer

Beide Fenster werden aus derselben 30-Jahres-Rohdatenabfrage berechnet, statt
zwei getrennte Requests zu senden (weniger Last auf der API, ein Call reicht).

Quelle: Open-Meteo Archive API (kostenlos, kein API-Key nötig, Daten ab 1940
verfügbar über ERA5-Reanalyse).
"""

import os
import csv
from datetime import date

from zones import ZONES
from fetch_utils import fetch_with_retry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "long_term")

YEARS_LONG = 30  # WMO-Standard-Klimanormalperiode
YEARS_SHORT = 10  # kurzfristigerer Trend innerhalb desselben Datensatzes

# Vegetationsperiode grob Mai-September - kann später pro Zone verfeinert werden
SEASON_START_MD = "05-01"
SEASON_END_MD = "09-30"


def _aggregate(times, temps, precip, sunshine, from_year, end_year):
    """Aggregiert die Tagesdaten für ein bestimmtes Jahresfenster [from_year, end_year]."""
    idx = [i for i, t in enumerate(times) if from_year <= int(t[:4]) <= end_year]
    n_seasons = end_year - from_year + 1

    avg_temp = sum(temps[i] for i in idx) / len(idx)
    avg_precip_per_season = sum(precip[i] for i in idx) / n_seasons
    avg_sunshine_h_per_season = (sum(sunshine[i] for i in idx) / 3600) / n_seasons

    return {
        "temperatur_mittel_c": round(avg_temp, 1),
        "niederschlag_mittel_pro_saison_mm": round(avg_precip_per_season, 1),
        "sonnenstunden_mittel_pro_saison": round(avg_sunshine_h_per_season, 1),
    }


def fetch_zone_climate(zone_id, zone):
    end_year = date.today().year - 1  # letztes abgeschlossenes Jahr
    start_year_long = end_year - YEARS_LONG + 1
    start_year_short = end_year - YEARS_SHORT + 1

    params = {
        "latitude": zone["lat"],
        "longitude": zone["lon"],
        "start_date": f"{start_year_long}-{SEASON_START_MD}",
        "end_date": f"{end_year}-{SEASON_END_MD}",
        "daily": "temperature_2m_mean,precipitation_sum,sunshine_duration",
        "timezone": "Asia/Omsk",
    }

    data = fetch_with_retry(ARCHIVE_URL, params)
    daily = data["daily"]
    times = daily["time"]
    temps = daily["temperature_2m_mean"]
    precip = daily["precipitation_sum"]
    sunshine = daily["sunshine_duration"]

    stats_10y = _aggregate(times, temps, precip, sunshine, start_year_short, end_year)
    stats_30y = _aggregate(times, temps, precip, sunshine, start_year_long, end_year)

    return {
        "abfrage_datum": date.today().isoformat(),
        "zone_id": zone_id,
        "zone_name": zone["name_ru"],
        "zeitraum_10j_von": start_year_short,
        "zeitraum_10j_bis": end_year,
        "temperatur_mittel_c_10j": stats_10y["temperatur_mittel_c"],
        "niederschlag_mittel_pro_saison_mm_10j": stats_10y["niederschlag_mittel_pro_saison_mm"],
        "sonnenstunden_mittel_pro_saison_10j": stats_10y["sonnenstunden_mittel_pro_saison"],
        "zeitraum_30j_von": start_year_long,
        "zeitraum_30j_bis": end_year,
        "temperatur_mittel_c_30j": stats_30y["temperatur_mittel_c"],
        "niederschlag_mittel_pro_saison_mm_30j": stats_30y["niederschlag_mittel_pro_saison_mm"],
        "sonnenstunden_mittel_pro_saison_30j": stats_30y["sonnenstunden_mittel_pro_saison"],
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR, "yearly_climate_trend.csv")
    file_exists = os.path.isfile(out_file)

    rows = []
    for zone_id, zone in ZONES.items():
        print(f"Hole {YEARS_LONG}-Jahres-Rohdaten für Zone: {zone_id} (daraus {YEARS_SHORT}j + {YEARS_LONG}j berechnet)")
        rows.append(fetch_zone_climate(zone_id, zone))

    with open(out_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} Zeilen an {out_file} angehängt.")


if __name__ == "__main__":
    main()