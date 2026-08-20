"""
Wöchentliche Abfrage kurzfristiger Wetterdaten (letzte 7 Tage) je Zone.
Wird per GitHub Actions Cron einmal pro Woche ausgeführt (siehe
.github/workflows/weekly_weather.yml).

Quelle: Open-Meteo Archive API (kostenlos, kein API-Key nötig).
https://open-meteo.com/en/docs/historical-weather-api
"""

import os
import csv
from datetime import date, timedelta

from zones import ZONES
from fetch_utils import fetch_with_retry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "short_term")


def fetch_zone_week(zone_id, zone):
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=6)

    params = {
        "latitude": zone["lat"],
        "longitude": zone["lon"],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_mean,precipitation_sum,sunshine_duration",
        "timezone": "Asia/Omsk",
    }

    data = fetch_with_retry(ARCHIVE_URL, params)
    daily = data["daily"]

    avg_temp = sum(daily["temperature_2m_mean"]) / len(daily["temperature_2m_mean"])
    total_precip = sum(daily["precipitation_sum"])
    total_sunshine_h = sum(daily["sunshine_duration"]) / 3600  # Sekunden -> Stunden

    return {
        "abfrage_datum": date.today().isoformat(),
        "zeitraum_von": start.isoformat(),
        "zeitraum_bis": end.isoformat(),
        "zone_id": zone_id,
        "zone_name": zone["name_ru"],
        "temperatur_mittel_c": round(avg_temp, 1),
        "niederschlag_summe_mm": round(total_precip, 1),
        "sonnenstunden_summe": round(total_sunshine_h, 1),
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR, "weekly_weather.csv")
    file_exists = os.path.isfile(out_file)

    rows = []
    for zone_id, zone in ZONES.items():
        print(f"Hole Daten für Zone: {zone_id}")
        rows.append(fetch_zone_week(zone_id, zone))

    with open(out_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} Zeilen an {out_file} angehängt.")


if __name__ == "__main__":
    main()