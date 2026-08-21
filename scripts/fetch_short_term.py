"""
Abfrage der Frühjahrswetterlage vor der Aussaat, je Zone.
Wird per GitHub Actions Cron einmal pro Woche ausgeführt (siehe
.github/workflows/weekly_weather.yml).

Es wird jetzt IMMER das Fenster vom 1. März bis zum Ende der
ersten Mai-Woche DES LAUFENDEN JAHRES abgefragt — also die tatsächliche
Vorsaison-Wetterlage, die für die Aussaatentscheidung zählt:
- Vor Fensterende (aktuell im Frühjahr): das Fenster wächst wöchentlich mit,
  bis einschließlich "heute" (Teildaten der laufenden Saison).
- Nach Fensterende (z.B. im Sommer/Herbst): das abgeschlossene Frühjahrsfenster
  dieses Jahres wird EINMALIG festgehalten; weitere wöchentliche Läufe
  überspringen die Abfrage, bis am 1. März des nächsten Jahres ein neues
  Fenster beginnt (kein sinnloses Neu-Abfragen bereits abgeschlossener Daten).

Quelle: Open-Meteo Archive API (kostenlos, kein API-Key nötig).
https://open-meteo.com/en/docs/historical-weather-api
"""

import os
import csv
from datetime import date

from zones import ZONES
from fetch_utils import fetch_with_retry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "short_term")

# Vorsaison-Fenster: 1. März bis Ende der ersten Mai-Woche (vereinfacht: 7. Mai)
WINDOW_START_MD = "03-01"
WINDOW_END_MD = "05-07"


def _get_window_for_year(year):
    start = date.fromisoformat(f"{year}-{WINDOW_START_MD}")
    end = date.fromisoformat(f"{year}-{WINDOW_END_MD}")
    return start, end


def _load_existing_rows(out_file):
    """Liest bestehende Zeilen, um bereits vollständig erfasste Fenster zu erkennen."""
    existing = {}
    if not os.path.isfile(out_file):
        return existing
    with open(out_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["zone_id"], row["zeitraum_von"])
            existing[key] = row["zeitraum_bis"]
    return existing


def fetch_zone_period(zone_id, zone, start, end):
    params = {
        "latitude": zone["lat"],
        "longitude": zone["lon"],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_mean,precipitation_sum,sunshine_duration",
        "timezone": "Asia/Omsk",
    }

    data = fetch_with_retry(ARCHIVE_URL, params, timeout=45)
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

    today = date.today()
    current_year = today.year
    window_start, window_end = _get_window_for_year(current_year)
    effective_end = min(today, window_end)
    window_finished = effective_end >= window_end

    existing = _load_existing_rows(out_file)

    rows = []
    for zone_id, zone in ZONES.items():
        key = (zone_id, window_start.isoformat())
        if window_finished and existing.get(key) == window_end.isoformat():
            print(f"Zone {zone_id}: Frühjahrsfenster {current_year} bereits vollständig erfasst, überspringe.")
            continue
        print(f"Hole Vorsaison-Daten {window_start}–{effective_end} für Zone {zone_id}")
        rows.append(fetch_zone_period(zone_id, zone, window_start, effective_end))

    if not rows:
        print("Keine neuen Daten — nichts zu schreiben.")
        return

    with open(out_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} Zeilen an {out_file} angehängt.")


if __name__ == "__main__":
    main()