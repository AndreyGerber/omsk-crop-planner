"""
Jährliche Abfrage langfristiger Wetterdaten (10-Jahres-Mittel) je Zone.
Wird per GitHub Actions Cron einmal pro Jahr (1. Januar) ausgeführt (siehe
.github/workflows/yearly_weather.yml).

Quelle: Open-Meteo Archive API (kostenlos, kein API-Key nötig).
"""

import os
import csv
from datetime import date

from zones import ZONES
from fetch_utils import fetch_with_retry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "long_term")

YEARS_BACK = 10
# Vegetationsperiode grob Mai-September - kann später pro Zone verfeinert werden
SEASON_START_MD = "05-01"
SEASON_END_MD = "09-30"


def fetch_zone_10y(zone_id, zone):
    end_year = date.today().year - 1  # letztes abgeschlossenes Jahr
    start_year = end_year - YEARS_BACK + 1

    params = {
        "latitude": zone["lat"],
        "longitude": zone["lon"],
        "start_date": f"{start_year}-{SEASON_START_MD}",
        "end_date": f"{end_year}-{SEASON_END_MD}",
        "daily": "temperature_2m_mean,precipitation_sum,sunshine_duration",
        "timezone": "Asia/Omsk",
    }

    data = fetch_with_retry(ARCHIVE_URL, params)
    daily = data["daily"]

    n_days = len(daily["temperature_2m_mean"])
    n_seasons = end_year - start_year + 1

    avg_temp = sum(daily["temperature_2m_mean"]) / n_days
    avg_precip_per_season = sum(daily["precipitation_sum"]) / n_seasons
    avg_sunshine_h_per_season = (sum(daily["sunshine_duration"]) / 3600) / n_seasons

    return {
        "abfrage_datum": date.today().isoformat(),
        "zeitraum_von_jahr": start_year,
        "zeitraum_bis_jahr": end_year,
        "zone_id": zone_id,
        "zone_name": zone["name_ru"],
        "temperatur_mittel_c": round(avg_temp, 1),
        "niederschlag_mittel_pro_saison_mm": round(avg_precip_per_season, 1),
        "sonnenstunden_mittel_pro_saison": round(avg_sunshine_h_per_season, 1),
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR, "yearly_climate_trend.csv")
    file_exists = os.path.isfile(out_file)

    rows = []
    for zone_id, zone in ZONES.items():
        print(f"Hole 10-Jahres-Daten für Zone: {zone_id}")
        rows.append(fetch_zone_10y(zone_id, zone))

    with open(out_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} Zeilen an {out_file} angehängt.")


if __name__ == "__main__":
    main()