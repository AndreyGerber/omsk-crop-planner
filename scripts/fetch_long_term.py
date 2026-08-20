"""
Jährliche Abfrage agronomischer Klimakennzahlen je Zone.
Wird per GitHub Actions Cron einmal pro Jahr (1. Januar) ausgeführt (siehe
.github/workflows/yearly_weather.yml).

WARUM KEINE EINFACHEN SAISONMITTELWERTE:
Ein reiner Mai-September-Durchschnitt verschluckt genau die Informationen,
die für die Anbauplanung zählen: Timing von Frost/Trockenheit, Extremereignisse,
Streuung zwischen Jahren. Stattdessen werden hier pro Jahr agronomisch
relevante Kennzahlen berechnet und erst danach über 10/30 Jahre gemittelt:

- Wärmesumme (Growing Degree Days, Basis 5°C) — bestimmt Reifegeschwindigkeit
- Letzter Frühjahrsfrost / erster Herbstfrost — bestimmt nutzbare Vegetationszeit
- Längste zusammenhängende Trockenperiode — oft ertragsentscheidender als
  die Niederschlagssumme
- Anzahl Hitzetage (>30°C) — Stressindikator, geht in einem Mittelwert unter

Ein einzelner API-Call pro Zone holt Rohdaten von April bis Oktober über den
vollen 30-Jahres-Zeitraum (breiter als die eigentliche Mai-September-Kernsaison,
damit auch Frühjahrs-/Herbstfrost außerhalb der Kernsaison erfasst wird).
Daraus werden alle Kennzahlen pro Jahr berechnet, dann für 10j- und
30j-Fenster aggregiert.

Quelle: Open-Meteo Archive API (kostenlos, kein API-Key nötig, Daten ab 1940
verfügbar über ERA5-Reanalyse).
"""

import os
import csv
import time
from datetime import date, timedelta
from collections import defaultdict

from zones import ZONES
from fetch_utils import fetch_with_retry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "long_term")

YEARS_LONG = 30  # WMO-Standard-Klimanormalperiode
YEARS_SHORT = 10  # kurzfristigerer Trend innerhalb desselben Datensatzes

# Rohdaten-Abfragefenster: breiter als die Kernsaison, damit Frost VOR/NACH
# der eigentlichen Mai-September-Periode erfasst wird.
FETCH_START_MD = "04-01"
FETCH_END_MD = "10-31"

# Agronomische Kernsaison für GDD/Niederschlag/Hitzetage/Trockenperiode
CORE_SEASON_MONTHS = (5, 9)
# Suchfenster für Frost-Ereignisse
SPRING_FROST_MONTHS = (4, 5)
FALL_FROST_MONTHS = (9, 10)

BASE_TEMP_GDD = 5.0       # Basistemperatur für Wärmesumme (Getreide-Standard)
HEAT_THRESHOLD_C = 30.0   # ab dieser Max-Temperatur zählt ein Tag als Hitzetag
DRY_DAY_THRESHOLD_MM = 1.0  # unter diesem Niederschlag zählt ein Tag als "trocken"

REFERENCE_YEAR_FOR_DOY = 2001  # Nicht-Schaltjahr, nur zur Umrechnung Tag-des-Jahres -> Datum


def _longest_dry_spell(records):
    """Längste Folge aufeinanderfolgender Tage mit Niederschlag unter der Trockenschwelle."""
    longest = current = 0
    for r in records:
        if r["precip"] < DRY_DAY_THRESHOLD_MM:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _compute_year_metrics(year_records):
    """Berechnet alle Kennzahlen für EIN Kalenderjahr aus dessen Tagesdaten."""
    year_records = sorted(year_records, key=lambda r: r["date"])
    core = [r for r in year_records if CORE_SEASON_MONTHS[0] <= r["date"].month <= CORE_SEASON_MONTHS[1]]
    spring = [r for r in year_records if SPRING_FROST_MONTHS[0] <= r["date"].month <= SPRING_FROST_MONTHS[1]]
    fall = [r for r in year_records if FALL_FROST_MONTHS[0] <= r["date"].month <= FALL_FROST_MONTHS[1]]

    if not core:
        return None

    gdd = sum(max(0.0, r["mean"] - BASE_TEMP_GDD) for r in core)
    precip_sum = sum(r["precip"] for r in core)
    sun_sum_h = sum(r["sun"] for r in core) / 3600
    heat_days = sum(1 for r in core if r["max"] > HEAT_THRESHOLD_C)
    dry_spell = _longest_dry_spell(core)
    temp_mean = sum(r["mean"] for r in core) / len(core)

    last_spring_frost = None
    for r in spring:
        if r["min"] <= 0:
            last_spring_frost = r["date"]  # letztes Vorkommen im Fenster behalten

    first_fall_frost = None
    for r in fall:
        if r["min"] <= 0:
            first_fall_frost = r["date"]
            break

    return {
        "gdd": gdd,
        "precip_mm": precip_sum,
        "sun_h": sun_sum_h,
        "heat_days": heat_days,
        "dry_spell_days": dry_spell,
        "temp_mean_c": temp_mean,
        "last_spring_frost_doy": last_spring_frost.timetuple().tm_yday if last_spring_frost else None,
        "first_fall_frost_doy": first_fall_frost.timetuple().tm_yday if first_fall_frost else None,
    }


def _doy_to_md_string(mean_doy):
    """Rechnet einen (gemittelten) Tag-des-Jahres zurück in ein lesbares MM-DD-Datum."""
    if mean_doy is None:
        return None
    ref_date = date(REFERENCE_YEAR_FOR_DOY, 1, 1) + timedelta(days=round(mean_doy) - 1)
    return ref_date.strftime("%m-%d")


def _aggregate_window(per_year_metrics, years_wanted):
    """Mittelt die pro-Jahr-Kennzahlen über ein gewünschtes Jahresfenster."""
    subset = [per_year_metrics[y] for y in years_wanted if y in per_year_metrics and per_year_metrics[y]]
    n = len(subset)

    def avg(key):
        vals = [s[key] for s in subset if s[key] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    spring_frost_vals = [s["last_spring_frost_doy"] for s in subset if s["last_spring_frost_doy"] is not None]
    fall_frost_vals = [s["first_fall_frost_doy"] for s in subset if s["first_fall_frost_doy"] is not None]
    mean_spring_doy = sum(spring_frost_vals) / len(spring_frost_vals) if spring_frost_vals else None
    mean_fall_doy = sum(fall_frost_vals) / len(fall_frost_vals) if fall_frost_vals else None

    return {
        "temperatur_mittel_c": avg("temp_mean_c"),
        "niederschlag_mittel_pro_saison_mm": avg("precip_mm"),
        "sonnenstunden_mittel_pro_saison": avg("sun_h"),
        "waermesumme_gdd_mittel": avg("gdd"),
        "hitzetage_ueber_30c_mittel": avg("heat_days"),
        "laengste_trockenperiode_tage_mittel": avg("dry_spell_days"),
        "letzter_fruehjahrsfrost_datum_approx": _doy_to_md_string(mean_spring_doy),
        "erster_herbstfrost_datum_approx": _doy_to_md_string(mean_fall_doy),
        "jahre_ohne_erkannten_fruehjahrsfrost": n - len(spring_frost_vals),
        "anzahl_jahre_in_auswertung": n,
    }


CHUNK_SIZE_YEARS = 10  # Größe der einzelnen API-Anfragen, statt 30 Jahre am Stück


def _fetch_chunk(zone, chunk_start_year, chunk_end_year):
    params = {
        "latitude": zone["lat"],
        "longitude": zone["lon"],
        "start_date": f"{chunk_start_year}-{FETCH_START_MD}",
        "end_date": f"{chunk_end_year}-{FETCH_END_MD}",
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum,sunshine_duration",
        "timezone": "Asia/Omsk",
    }
    data = fetch_with_retry(ARCHIVE_URL, params, timeout=60, request_gap_seconds=3.0)
    daily = data["daily"]
    return [
        {
            "date": date.fromisoformat(daily["time"][i]),
            "mean": daily["temperature_2m_mean"][i],
            "max": daily["temperature_2m_max"][i],
            "min": daily["temperature_2m_min"][i],
            "precip": daily["precipitation_sum"][i],
            "sun": daily["sunshine_duration"][i],
        }
        for i in range(len(daily["time"]))
    ]


def fetch_zone_climate(zone_id, zone):
    end_year = date.today().year - 1  # letztes abgeschlossenes Jahr
    start_year_long = end_year - YEARS_LONG + 1
    start_year_short = end_year - YEARS_SHORT + 1

    # Abfrage in ~10-Jahres-Häppchen statt einer großen 30-Jahres-Anfrage,
    # um Timeouts und Rate-Limits bei der API zu vermeiden.
    records = []
    chunk_start = start_year_long
    while chunk_start <= end_year:
        chunk_end = min(chunk_start + CHUNK_SIZE_YEARS - 1, end_year)
        print(f"  Chunk {chunk_start}-{chunk_end} für Zone {zone_id}")
        records.extend(_fetch_chunk(zone, chunk_start, chunk_end))
        chunk_start = chunk_end + 1

    by_year = defaultdict(list)
    for r in records:
        by_year[r["date"].year].append(r)

    per_year_metrics = {year: _compute_year_metrics(recs) for year, recs in by_year.items()}

    years_10 = range(start_year_short, end_year + 1)
    years_30 = range(start_year_long, end_year + 1)

    stats_10y = _aggregate_window(per_year_metrics, years_10)
    stats_30y = _aggregate_window(per_year_metrics, years_30)

    row = {
        "abfrage_datum": date.today().isoformat(),
        "zone_id": zone_id,
        "zone_name": zone["name_ru"],
        "zeitraum_10j_von": start_year_short,
        "zeitraum_10j_bis": end_year,
    }
    row.update({f"{k}_10j": v for k, v in stats_10y.items()})
    row["zeitraum_30j_von"] = start_year_long
    row["zeitraum_30j_bis"] = end_year
    row.update({f"{k}_30j": v for k, v in stats_30y.items()})

    return row


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR, "yearly_climate_trend.csv")
    file_exists = os.path.isfile(out_file)

    rows = []
    for i, (zone_id, zone) in enumerate(ZONES.items()):
        print(f"Hole {YEARS_LONG}-Jahres-Rohdaten für Zone: {zone_id} (April-Oktober, daraus alle Kennzahlen berechnet)")
        rows.append(fetch_zone_climate(zone_id, zone))
        if i < len(ZONES) - 1:
            time.sleep(5)  # kurze Pause zwischen Zonen, zusätzlich zur Pause zwischen Chunks

    with open(out_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} Zeilen an {out_file} angehängt.")


if __name__ == "__main__":
    main()