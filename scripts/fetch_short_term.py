"""
Abfrage der Frühjahrswetterlage vor der Aussaat, je Zone — mit TAGESGENAUER
Auflösung, nicht nur einem einzigen Durchschnittswert über die ganze Periode.

WARUM TAGESAUFLÖSUNG: Im Frühjahr ändern sich die Bedingungen (Tauwetter,
Kälterückfälle) oft innerhalb weniger Tage. Selbst ein Wochenmittel kann
einen kurzen Kälteeinbruch mitten in einer Tauperiode komplett verschlucken.
Die Open-Meteo-API liefert ohnehin Tageswerte — wir speichern sie jetzt
direkt, statt sie sofort zu einem einzigen Mittelwert zu verdichten.

ZWEI DATEIEN:
- data/short_term/daily_spring_weather.csv: EINE ZEILE PRO TAG UND ZONE,
  volle Auflösung. Wächst inkrementell — jede Woche werden nur die seit dem
  letzten Lauf neu vergangenen Tage angehängt (kein Neuabruf bereits
  gespeicherter Tage).
- data/short_term/weekly_weather.csv: kompakte Zusammenfassung (Mittelwert
  Temperatur, Summe Niederschlag/Sonnenstunden über das bisherige Fenster),
  berechnet AUS den lokal gespeicherten Tagesdaten (kein zusätzlicher
  API-Call nötig) — für schnelle Übersicht in der App.

FENSTER: 1. März bis Ende der ersten Mai-Woche (7. Mai) DES LAUFENDEN JAHRES.
Vor Fensterende wächst es wöchentlich mit; danach ist es fest eingefroren
und weitere Läufe überspringen die Abfrage bis zum 1. März des Folgejahres.

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

WINDOW_START_MD = "03-01"
WINDOW_END_MD = "05-07"


def _get_window_for_year(year):
    start = date.fromisoformat(f"{year}-{WINDOW_START_MD}")
    end = date.fromisoformat(f"{year}-{WINDOW_END_MD}")
    return start, end


def _load_daily_data(daily_file):
    """Liest die bestehende Tagesdaten-CSV. Gibt zurück:
    - rows_by_zone: {zone_id: [ {date, temp, precip, sun}, ... ]}
    - last_date_by_zone: {zone_id: letztes gespeichertes Datum als date-Objekt}
    """
    rows_by_zone = {}
    last_date_by_zone = {}
    if not os.path.isfile(daily_file):
        return rows_by_zone, last_date_by_zone

    with open(daily_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zone_id = row["zone_id"]
            d = date.fromisoformat(row["date"])
            rows_by_zone.setdefault(zone_id, []).append({
                "date": d,
                "temp": float(row["temperatur_c"]),
                "temp_min": float(row["temperatur_min_c"]),
                "precip": float(row["niederschlag_mm"]),
                "sun": float(row["sonnenstunden"]),
            })
            if zone_id not in last_date_by_zone or d > last_date_by_zone[zone_id]:
                last_date_by_zone[zone_id] = d

    return rows_by_zone, last_date_by_zone


def _fetch_daily_range(zone, start, end):
    """Holt Tageswerte für [start, end] und gibt eine Liste von Tages-Dicts zurück."""
    params = {
        "latitude": zone["lat"],
        "longitude": zone["lon"],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_mean,temperature_2m_min,precipitation_sum,sunshine_duration",
        "timezone": "Asia/Omsk",
    }
    data = fetch_with_retry(ARCHIVE_URL, params, timeout=45)
    daily = data["daily"]

    rows = []
    for i, day_str in enumerate(daily["time"]):
        rows.append({
            "date": date.fromisoformat(day_str),
            "temp": daily["temperature_2m_mean"][i],
            "temp_min": daily["temperature_2m_min"][i],
            "precip": daily["precipitation_sum"][i],
            "sun": daily["sunshine_duration"][i] / 3600,  # Sekunden -> Stunden
        })
    return rows


def _write_daily_rows(daily_file, new_rows_by_zone):
    """Hängt neue Tageszeilen an die Tagesdaten-CSV an."""
    file_exists = os.path.isfile(daily_file)
    all_new = []
    for zone_id, rows in new_rows_by_zone.items():
        zone_name = ZONES[zone_id]["name_ru"]
        for r in rows:
            all_new.append({
                "zone_id": zone_id,
                "zone_name": zone_name,
                "date": r["date"].isoformat(),
                "temperatur_c": round(r["temp"], 1),
                "temperatur_min_c": round(r["temp_min"], 1),
                "niederschlag_mm": round(r["precip"], 1),
                "sonnenstunden": round(r["sun"], 2),
            })

    if not all_new:
        return

    fieldnames = ["zone_id", "zone_name", "date", "temperatur_c", "temperatur_min_c", "niederschlag_mm", "sonnenstunden"]
    with open(daily_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(all_new)


def _find_last_frost(rows):
    """Letztes Datum mit Tagesminimum <= 0°C innerhalb der übergebenen Zeilen, oder None."""
    frost_dates = [r["date"] for r in rows if r["temp_min"] <= 0]
    return max(frost_dates) if frost_dates else None


def _find_warmup_start(rows, threshold=5.0, min_run_days=5):
    """
    Erster Tag einer mindestens `min_run_days`-tägigen Serie mit Tagesmittel
    >= threshold — praktikabler Indikator für "Boden wird bearbeitbar",
    statt eines bedeutungslosen Durchschnitts über die ganze Periode.
    """
    rows_sorted = sorted(rows, key=lambda r: r["date"])
    run_start = None
    run_len = 0
    for r in rows_sorted:
        if r["temp"] >= threshold:
            if run_len == 0:
                run_start = r["date"]
            run_len += 1
            if run_len >= min_run_days:
                return run_start
        else:
            run_len = 0
            run_start = None
    return None


def _compute_indicators(daily_rows, window_start, effective_end):
    """
    Berechnet agronomisch sinnvolle Kennzahlen aus den lokal gespeicherten
    Tagesdaten — statt eines einzelnen Temperaturmittels über die ganze
    (klimatisch sehr heterogene) Periode, das die eigentliche zeitliche
    Struktur (Frost -> Tauwetter -> stabile Wärme) verschlucken würde.
    """
    relevant = [r for r in daily_rows if window_start <= r["date"] <= effective_end]
    if not relevant:
        return None

    last_frost = _find_last_frost(relevant)
    warmup_start = _find_warmup_start(relevant)
    total_precip = sum(r["precip"] for r in relevant)
    days_covered = (effective_end - window_start).days + 1

    return {
        "letzter_beobachteter_frost": last_frost.isoformat() if last_frost else "не наблюдался",
        "tage_seit_letztem_frost": (effective_end - last_frost).days if last_frost else None,
        "beginn_stabiler_erwaermung": warmup_start.isoformat() if warmup_start else "ещё не наступило",
        "niederschlag_summe_mm_bisher": round(total_precip, 1),
        "tage_ausgewertet": days_covered,
    }


def _load_covered_windows(weekly_file):
    covered = {}
    if not os.path.isfile(weekly_file):
        return covered
    with open(weekly_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            covered[(row["zone_id"], row["zeitraum_von"])] = row["zeitraum_bis"]
    return covered


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    daily_file = os.path.join(OUTPUT_DIR, "daily_spring_weather.csv")
    weekly_file = os.path.join(OUTPUT_DIR, "weekly_weather.csv")

    today = date.today()
    current_year = today.year
    window_start, window_end = _get_window_for_year(current_year)
    effective_end = min(today, window_end)
    window_finished = effective_end >= window_end

    rows_by_zone, last_date_by_zone = _load_daily_data(daily_file)
    covered_windows = _load_covered_windows(weekly_file)

    new_rows_by_zone = {}
    for zone_id, zone in ZONES.items():
        last_date = last_date_by_zone.get(zone_id)
        fetch_from = window_start if last_date is None else last_date + timedelta(days=1)

        if fetch_from > effective_end:
            print(f"Zone {zone_id}: keine neuen Tage seit letztem Lauf, überspringe Abruf.")
            continue

        print(f"Hole Tagesdaten {fetch_from}–{effective_end} für Zone {zone_id}")
        new_rows = _fetch_daily_range(zone, fetch_from, effective_end)
        new_rows_by_zone[zone_id] = new_rows
        rows_by_zone.setdefault(zone_id, []).extend(new_rows)

    if new_rows_by_zone:
        _write_daily_rows(daily_file, new_rows_by_zone)
        total_new = sum(len(r) for r in new_rows_by_zone.values())
        print(f"{total_new} neue Tageszeilen an {daily_file} angehängt.")
    else:
        print("Keine neuen Tagesdaten — daily_spring_weather.csv unverändert.")

    # Zusammenfassung (weekly_weather.csv) aus den (jetzt aktuellen) Tagesdaten berechnen
    summary_rows = []
    for zone_id, zone in ZONES.items():
        key = (zone_id, window_start.isoformat())
        if window_finished and covered_windows.get(key) == window_end.isoformat():
            continue  # Fenster für dieses Jahr schon final zusammengefasst

        agg = _compute_indicators(rows_by_zone.get(zone_id, []), window_start, effective_end)
        if agg is None:
            continue

        summary_rows.append({
            "abfrage_datum": today.isoformat(),
            "zeitraum_von": window_start.isoformat(),
            "zeitraum_bis": effective_end.isoformat(),
            "zone_id": zone_id,
            "zone_name": zone["name_ru"],
            **agg,
        })

    if summary_rows:
        weekly_file_exists = os.path.isfile(weekly_file)
        with open(weekly_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
            if not weekly_file_exists:
                writer.writeheader()
            writer.writerows(summary_rows)
        print(f"{len(summary_rows)} Zusammenfassungs-Zeilen an {weekly_file} angehängt.")
    else:
        print("Keine neue Zusammenfassung nötig.")


if __name__ == "__main__":
    main()