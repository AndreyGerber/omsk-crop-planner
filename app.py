"""
Модель оптимального выбора культур — Омская область
Прототип на Streamlit
"""

import os
import csv
from collections import defaultdict
from datetime import date, timedelta

import streamlit as st
import pandas as pd

try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

st.set_page_config(page_title="Оптимизация посева — Омская область", layout="wide")


def render_wrapped_table(df, col_widths_pct=None):
    """
    Rendert eine DataFrame als HTML-Tabelle mit FESTEN Spaltenbreiten und
    Textumbruch (statt st.dataframe, das lange Texte abschneidet und
    horizontales Scrollen erzwingt).
    """
    n = len(df.columns)
    if col_widths_pct is None:
        col_widths_pct = [100 / n] * n

    colgroup = "".join(f'<col style="width:{w}%">' for w in col_widths_pct)
    header_cells = "".join(
        f'<th style="text-align:left;padding:8px 10px;border-bottom:2px solid #999;'
        f'font-weight:600;">{col}</th>'
        for col in df.columns
    )
    body_rows = ""
    for _, row in df.iterrows():
        cells = "".join(
            f'<td style="padding:8px 10px;border-bottom:1px solid #e0e0e0;'
            f'vertical-align:top;white-space:normal;word-wrap:break-word;'
            f'overflow-wrap:break-word;line-height:1.4;">{val}</td>'
            for val in row
        )
        body_rows += f"<tr>{cells}</tr>"

    html = (
        '<div style="width:100%;overflow-x:hidden;">'
        '<table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:0.9rem;">'
        f'<colgroup>{colgroup}</colgroup>'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{body_rows}</tbody>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_grouped_weekly_table(row_label, row_keys, row_display, metric_groups):
    """
    Rendert eine Tabelle mit ZWEISTUFIGEM Kopf: pro Metrik (z.B. "Осадки (мм)")
    eine Gruppenspalte, darunter je eine Unterspalte pro Jahr — damit man
    Werte über mehrere Jahre für dieselbe Woche direkt nebeneinander sieht,
    statt in langem Format untereinander (ein Jahr nach dem anderen).

    row_label: Beschriftung der ersten Spalte (z.B. "Неделя")
    row_keys: Liste der Zeilen-Schlüssel (z.B. ISO-Wochennummern), chronologisch
    row_display: dict {row_key: Anzeigetext für die erste Spalte}
    metric_groups: dict {Metrikname: {jahr: {row_key: wert}}}
    """
    jahre_pro_metrik = {
        metrik: sorted(jahre_dict.keys()) for metrik, jahre_dict in metric_groups.items()
    }
    gesamt_unterspalten = sum(len(js) for js in jahre_pro_metrik.values())
    row_label_width = 12
    rest_width = 100 - row_label_width
    sub_width = rest_width / gesamt_unterspalten if gesamt_unterspalten else rest_width

    colgroup = f'<col style="width:{row_label_width}%">'
    colgroup += "".join(
        f'<col style="width:{sub_width}%">'
        for metrik in metric_groups for _ in jahre_pro_metrik[metrik]
    )

    header_row1 = f'<th rowspan="2" style="text-align:left;padding:6px 8px;border-bottom:2px solid #999;border-right:1px solid #ccc;font-weight:600;vertical-align:bottom;">{row_label}</th>'
    for metrik in metric_groups:
        n_sub = len(jahre_pro_metrik[metrik])
        header_row1 += (
            f'<th colspan="{n_sub}" style="text-align:center;padding:6px 8px;'
            f'border-bottom:1px solid #ccc;border-right:2px solid #999;font-weight:600;">{metrik}</th>'
        )

    header_row2 = ""
    for metrik in metric_groups:
        for jahr in jahre_pro_metrik[metrik]:
            header_row2 += (
                f'<th style="text-align:center;padding:4px 6px;border-bottom:2px solid #999;'
                f'font-weight:500;color:#555;">{jahr}</th>'
            )

    body_rows = ""
    for rk in row_keys:
        cells = f'<td style="padding:6px 8px;border-bottom:1px solid #e0e0e0;border-right:1px solid #ccc;white-space:nowrap;">{row_display.get(rk, rk)}</td>'
        for metrik in metric_groups:
            for jahr in jahre_pro_metrik[metrik]:
                val = metric_groups[metrik][jahr].get(rk, "")
                cells += f'<td style="text-align:center;padding:6px 8px;border-bottom:1px solid #e0e0e0;">{val}</td>'
        body_rows += f"<tr>{cells}</tr>"

    html = (
        '<div style="width:100%;overflow-x:hidden;">'
        '<table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:0.85rem;">'
        f'<colgroup>{colgroup}</colgroup>'
        f'<thead><tr>{header_row1}</tr><tr>{header_row2}</tr></thead>'
        f'<tbody>{body_rows}</tbody>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# СПРАВОЧНЫЕ ДАННЫЕ (заглушки — в реальной версии заменяются на API/базу данных)
# ---------------------------------------------------------------------------

# Statische Zonen-Metadaten (Bodenprofile) — ändern sich kaum, bleiben daher
# als Referenztabelle im Code. zone_id entspricht 1:1 den IDs in
# scripts/zones.py, damit beide Teile des Projekts zusammenpassen.
ZONE_STATIC = {
    "north_taiga": {
        "name_ru": "Север (тайга)",
        "почвы_типичные": ["Подзолистая", "Серая лесная"],
    },
    "north_foreststeppe": {
        "name_ru": "Северная лесостепь",
        "почвы_типичные": ["Серая лесная", "Чернозём выщелоченный"],
    },
    "south_foreststeppe": {
        "name_ru": "Южная лесостепь",
        "почвы_типичные": ["Чернозём выщелоченный", "Чернозём обыкновенный"],
    },
    "steppe": {
        "name_ru": "Степь",
        "почвы_типичные": ["Чернозём обыкновенный", "Чернозём южный"],
    },
}

# Geo-Koordinaten je Zone (Zentroid entspricht scripts/zones.py) plus
# Breitengrad-Grenzen der ~100-km-Streifen, nur fuer die Kartendarstellung.
# Grenzen = Mittelpunkte zwischen benachbarten Zentroiden, mit Puffer an
# den aeusseren Raendern.
ZONE_MAP_INFO = {
    "north_taiga": {"lat_center": 57.5, "lon_center": 73.5, "lat_von": 58.25, "lat_bis": 56.75, "farbe": "#2b6cb0"},
    "north_foreststeppe": {"lat_center": 56.0, "lon_center": 73.5, "lat_von": 56.75, "lat_bis": 55.5, "farbe": "#38a169"},
    "south_foreststeppe": {"lat_center": 55.0, "lon_center": 73.3, "lat_von": 55.5, "lat_bis": 54.5, "farbe": "#d69e2e"},
    "steppe": {"lat_center": 54.0, "lon_center": 73.0, "lat_von": 54.5, "lat_bis": 53.5, "farbe": "#dd6b20"},
}
MAP_LON_WEST = 70.0
MAP_LON_EAST = 77.0

# Fallback-Klimawerte, falls noch keine CSV-Daten vorliegen (z.B. vor dem
# allerersten Workflow-Lauf) — damit die App nie abstürzt, nur mit alten
# Platzhaltern weiterläuft. Werte grob nach Nord-Süd-Gradient geschätzt.
CLIMATE_FALLBACK = {
    "north_taiga": {
        "осадки_мм": 320, "температура_ср": 15.5, "gdd": 1350,
        "trockenperiode": 12, "hitzetage": 2, "vegetationsfenster_tage": 105,
    },
    "north_foreststeppe": {
        "осадки_мм": 300, "температура_ср": 17.0, "gdd": 1500,
        "trockenperiode": 14, "hitzetage": 3, "vegetationsfenster_tage": 120,
    },
    "south_foreststeppe": {
        "осадки_мм": 280, "температура_ср": 18.5, "gdd": 1650,
        "trockenperiode": 15, "hitzetage": 6, "vegetationsfenster_tage": 130,
    },
    "steppe": {
        "осадки_мм": 250, "температура_ср": 19.5, "gdd": 1800,
        "trockenperiode": 17, "hitzetage": 10, "vegetationsfenster_tage": 140,
    },
}

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SHORT_TERM_CSV = os.path.join(REPO_ROOT, "data", "short_term", "weekly_weather.csv")
DAILY_SPRING_CSV = os.path.join(REPO_ROOT, "data", "short_term", "daily_spring_weather.csv")
LONG_TERM_CSV = os.path.join(REPO_ROOT, "data", "long_term", "yearly_climate_trend.csv")
PER_YEAR_CSV = os.path.join(REPO_ROOT, "data", "long_term", "yearly_per_year_metrics.csv")
MONTHLY_CSV = os.path.join(REPO_ROOT, "data", "long_term", "yearly_monthly_metrics.csv")
WEEKLY_CSV = os.path.join(REPO_ROOT, "data", "long_term", "yearly_weekly_metrics.csv")
CALIBRATION_CSV = os.path.join(REPO_ROOT, "data", "calibration", "actual_results.csv")

REFERENCE_YEAR_FOR_DOY = 2001  # Nicht-Schaltjahr, nur zur Umrechnung MM-DD -> Tag-des-Jahres

# Gewichtung beim Verschmelzen von 10-Jahres- und 30-Jahres-Klimawerten:
# höherer Wert = stärkere Betonung des jüngeren (volatileren, aber
# aktuelleren) 10-Jahres-Trends gegenüber der stabilen 30-Jahres-Norm.
TREND_GEWICHT_10J = 0.6


def _md_to_doy(md_str):
    """Rechnet ein 'MM-DD'-Datum (aus fetch_long_term.py) in einen Tag-des-Jahres um."""
    if not md_str or not isinstance(md_str, str) or "-" not in md_str:
        return None
    try:
        month, day = md_str.split("-")
        return date(REFERENCE_YEAR_FOR_DOY, int(month), int(day)).timetuple().tm_yday
    except (ValueError, TypeError):
        return None


def _doy_to_md(doy):
    """Rechnet einen Tag-des-Jahres zurück in ein 'MM-DD'-Datum um."""
    if doy is None:
        return None
    d = date(REFERENCE_YEAR_FOR_DOY, 1, 1) + timedelta(days=round(doy) - 1)
    return d.strftime("%m-%d")


def _blend_trend(val_10j, val_30j, weight_10j=TREND_GEWICHT_10J):
    """
    Verschmilzt 10-Jahres- und 30-Jahres-Wert zu einem gewichteten Klimawert,
    der den aktuellen Trend stärker berücksichtigt als eine reine 30-Jahres-
    Norm, aber trotzdem nicht komplett auf den volatileren 10-Jahres-Wert
    springt. Fällt auf den jeweils verfügbaren Wert zurück, falls einer fehlt.
    """
    if val_10j is None and val_30j is None:
        return None
    if val_10j is None:
        return val_30j
    if val_30j is None:
        return val_10j
    return round(weight_10j * val_10j + (1 - weight_10j) * val_30j, 2)


@st.cache_data(ttl=3600)
def load_latest_by_zone(csv_path, date_col="abfrage_datum"):
    """Lädt eine CSV und gibt pro zone_id nur die neueste Zeile zurück (als dict)."""
    if not os.path.isfile(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    if df.empty:
        return {}
    df[date_col] = pd.to_datetime(df[date_col])
    latest = df.sort_values(date_col).groupby("zone_id").tail(1)
    return latest.set_index("zone_id").to_dict("index")


@st.cache_data(ttl=3600)
def load_all_per_year(csv_path):
    """Lädt ALLE Einzeljahres-Zeilen (nicht nur die neueste) je Zone,
    für den Analog-Jahre-Vergleich. Gibt {zone_id: [Zeilen als dict, ...]} zurück."""
    if not os.path.isfile(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    if df.empty:
        return {}
    result = {}
    for zone_id, group in df.groupby("zone_id"):
        result[zone_id] = group.to_dict("records")
    return result


@st.cache_data(ttl=3600)
def load_all_monthly(csv_path):
    """
    Lädt die Monats-Zeitreihe (März-Oktober, jedes Jahr). Gibt
    {(zone_id, jahr): {monat: {niederschlag_mm, temperatur_mittel_c}}} zurück
    — schneller Zugriff auf einen beliebigen Monat eines beliebigen Jahres.
    """
    if not os.path.isfile(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    if df.empty:
        return {}
    result = {}
    for (zone_id, jahr), group in df.groupby(["zone_id", "jahr"]):
        result[(zone_id, int(jahr))] = {
            int(row["monat"]): {
                "niederschlag_mm": row["niederschlag_mm"],
                "temperatur_mittel_c": row["temperatur_mittel_c"],
            }
            for _, row in group.iterrows()
        }
    return result


@st.cache_data(ttl=3600)
def load_all_weekly(csv_path):
    """
    Lädt die Wochen-Zeitreihe (ISO-Kalenderwochen, März-Oktober, jedes Jahr).
    Gibt {(zone_id, jahr): [Wochen-Zeilen als dict, chronologisch sortiert]} zurück
    — feinere Auflösung als die Monatsdaten, zeigt Schwankungen INNERHALB
    eines Monats statt sie zu einem einzigen Mittelwert zu verdichten.
    """
    if not os.path.isfile(csv_path):
        return {}
    df = pd.read_csv(csv_path)
    if df.empty:
        return {}
    result = {}
    for (zone_id, jahr), group in df.groupby(["zone_id", "jahr"]):
        result[(zone_id, int(jahr))] = group.sort_values("iso_woche").to_dict("records")
    return result


@st.cache_data(ttl=3600)
def load_daily_spring(csv_path):
    """Lädt die tagesgenauen Frühjahrsdaten des LAUFENDEN Jahres (1. März – 7. Mai)."""
    if not os.path.isfile(csv_path):
        return pd.DataFrame()
    return pd.read_csv(csv_path)


def weekly_series_by_position(zone_id, jahr, weekly_data):
    """
    Wandelt die Wochendaten eines historischen Jahres in eine Reihe um, die
    nach POSITION (1., 2., 3. Woche der Saison) statt nach Kalenderdatum
    indiziert ist — dadurch lassen sich mehrere Jahre nebeneinander
    vergleichen, ohne die (zwischen Jahren leicht verschobenen) echten
    Kalenderdaten in derselben Spalte zu vermischen.
    """
    weeks = weekly_data.get((zone_id, jahr), [])
    weeks_sorted = sorted(weeks, key=lambda w: w["iso_woche"])
    return {
        pos: {"niederschlag_mm": w["niederschlag_mm"], "temperatur_mittel_c": w["temperatur_mittel_c"]}
        for pos, w in enumerate(weeks_sorted, start=1)
    }


def weekly_series_from_daily(daily_rows):
    """
    Aggregiert Tagesdaten (laufendes Jahr, März-Anfang Mai) zu Wochen und
    nummeriert sie nach Position ab 1 — analog zu weekly_series_by_position,
    damit beide Reihen direkt vergleichbar sind.
    """
    by_week = defaultdict(list)
    for r in daily_rows:
        d = date.fromisoformat(r["date"])
        iso_year, iso_week, _ = d.isocalendar()
        by_week[(iso_year, iso_week)].append(r)

    weeks_sorted = sorted(by_week.keys())
    result = {}
    for pos, key in enumerate(weeks_sorted, start=1):
        recs = by_week[key]
        result[pos] = {
            "niederschlag_mm": round(sum(float(r["niederschlag_mm"]) for r in recs), 1),
            "temperatur_mittel_c": round(sum(float(r["temperatur_c"]) for r in recs) / len(recs), 1),
        }
    return result




def characterize_harvest_wetness(zone_id, harvest_month, analog_years, monthly_data):
    """
    Vergleicht den Niederschlag im geschätzten Erntemonat der KONKRETEN
    Kultur zwischen den Analog-Jahren und dem 30-jährigen Durchschnitt
    (1996–2025) für genau diesen Monat.

    Zeigt die EINZELNEN Werte pro Analog-Jahr (nicht nur einen gemittelten
    Wert) — ein Durchschnitt kann große Schwankungen zwischen den Jahren
    verschlucken (z.B. ein sehr nasses + ein sehr trockenes Jahr ergeben
    zusammen einen unauffälligen Mittelwert). Tagesgenaue Wetterschätzung
    ist damit natürlich nicht möglich — dafür bräuchte es eine echte
    Wettervorhersage näher am Termin.

    Gibt ein Dict zurück (nicht einen fertigen Satz), damit der Aufrufer
    Datum und Feuchte-Einschätzung in GETRENNTEN Tabellenspalten anzeigen
    kann statt in einer überladenen Zelle.
    """
    if not analog_years or harvest_month is None:
        return None

    per_year = []
    for a in analog_years:
        key = (zone_id, a["jahr"])
        month_data = monthly_data.get(key, {}).get(harvest_month)
        if month_data is not None:
            per_year.append({"jahr": a["jahr"], "мм": round(month_data["niederschlag_mm"])})
    if not per_year:
        return None
    avg_analog = sum(y["мм"] for y in per_year) / len(per_year)

    baseline_years = [year for (zid, year) in monthly_data.keys() if zid == zone_id]
    baseline_precip = [
        vals[harvest_month]["niederschlag_mm"]
        for (zid, _), vals in monthly_data.items()
        if zid == zone_id and harvest_month in vals
    ]
    if not baseline_precip:
        return None
    baseline_avg = sum(baseline_precip) / len(baseline_precip)
    baseline_von = min(baseline_years) if baseline_years else None
    baseline_bis = max(baseline_years) if baseline_years else None

    if avg_analog > baseline_avg * 1.3:
        klass = "влажнее нормы"
    elif avg_analog < baseline_avg * 0.7:
        klass = "суше нормы"
    else:
        klass = "близко к норме"

    month_name = RU_MONTHS_PREPOSITIONAL[harvest_month - 1]
    norma_period = f"{baseline_von}–{baseline_bis} гг." if baseline_von else "многолетний период"

    po_godam_text = ", ".join(f"{y['jahr']} — {y['мм']} мм" for y in per_year)

    return {
        "класс": klass,
        "месяц": month_name,
        "по_годам": per_year,
        "похожие_года_мм": round(avg_analog),
        "норма_мм": round(baseline_avg),
        "норма_период": norma_period,
        "краткий_текст": (
            f"{klass} в {month_name} — по годам: {po_godam_text} "
            f"(норма {norma_period}: {round(baseline_avg)} мм)"
        ),
    }


CALIBRATION_FIELDS = [
    "zone_id", "zone_name", "crop_name", "jahr",
    "факт_дата_посева", "факт_дата_уборки", "факт_урожайность_ц_га",
    "заметки", "добавлено",
]


def load_calibration_data():
    """Lädt alle bisher eingetragenen realen Beobachtungen (kein Caching —
    soll sofort nach dem Speichern einer neuen Zeile aktuell sein)."""
    if not os.path.isfile(CALIBRATION_CSV):
        return pd.DataFrame(columns=CALIBRATION_FIELDS)
    df = pd.read_csv(CALIBRATION_CSV)
    return df


def save_calibration_entry(entry):
    """Hängt eine neue reale Beobachtung an die Kalibrierungsdatei an."""
    os.makedirs(os.path.dirname(CALIBRATION_CSV), exist_ok=True)
    file_exists = os.path.isfile(CALIBRATION_CSV)
    with open(CALIBRATION_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CALIBRATION_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)


def get_calibrated_yield(zone_id, crop_name, calibration_df):
    """
    Mittelt die tatsächlich eingetragene Urozhaynost für eine Zone/Kultur.
    Gibt (kalibrierter_wert, anzahl_beobachtungen) zurück, oder (None, 0)
    falls keine Beobachtungen vorliegen.
    """
    if calibration_df.empty:
        return None, 0
    subset = calibration_df[
        (calibration_df["zone_id"] == zone_id) & (calibration_df["crop_name"] == crop_name)
    ]
    subset = subset[subset["факт_урожайность_ц_га"].notna()]
    if subset.empty:
        return None, 0
    return round(subset["факт_урожайность_ц_га"].astype(float).mean(), 1), len(subset)


def find_analog_years(zone_id, current_frost_doy, current_niederschlag, per_year_data, top_n=3):
    """
    Findet die historischen Jahre, deren Vorsaison-Verlauf (Frosttermin +
    Niederschlag bis 7. Mai) dem aktuellen Jahr am ähnlichsten ist, und gibt
    deren tatsächlichen SAISON-Verlauf (GDD, Hitze, Trockenheit) zurück —
    als Anhaltspunkt dafür, wie sich Jahre mit einem vergleichbaren Frühling
    tatsächlich entwickelt haben (statt nur eines abstrakten Klimamittels).
    """
    rows = per_year_data.get(zone_id, [])
    candidates = []
    for r in rows:
        frost_doy = _md_to_doy(r["vorsaison_letzter_frost"][5:]) if isinstance(r.get("vorsaison_letzter_frost"), str) and r["vorsaison_letzter_frost"] else None
        niederschlag = r.get("vorsaison_niederschlag_mm")
        if frost_doy is None or niederschlag is None or pd.isna(niederschlag):
            continue

        # Ähnlichkeit: Frosttermin zählt stark (Hauptsignal), Niederschlag
        # schwächer (Sekundärsignal) — Werte normiert auf vergleichbare Skala.
        frost_diff = abs(frost_doy - current_frost_doy) if current_frost_doy is not None else 0
        niederschlag_diff = abs(niederschlag - current_niederschlag) / 10 if current_niederschlag is not None else 0
        distanz = frost_diff * 2 + niederschlag_diff

        candidates.append({
            "jahr": int(r["jahr"]),
            "distanz": distanz,
            "vorsaison_frost": r["vorsaison_letzter_frost"],
            "vorsaison_niederschlag": niederschlag,
            "saison_gdd": r.get("saison_gdd"),
            "saison_hitzetage": r.get("saison_hitzetage"),
            "saison_trockenperiode": r.get("saison_laengste_trockenperiode_tage"),
            "saison_temperatur": r.get("saison_temperatur_mittel_c"),
            "saison_niederschlag": r.get("saison_niederschlag_mm"),
            "herbstfrost_doy": r.get("erster_herbstfrost_doy"),
        })

    candidates.sort(key=lambda c: c["distanz"])
    return candidates[:top_n]


def _doy_to_readable(doy):
    """Tag-des-Jahres -> lesbares Datum ('DD Monat')."""
    if doy is None or (isinstance(doy, float) and pd.isna(doy)):
        return None
    d = date(REFERENCE_YEAR_FOR_DOY, 1, 1) + timedelta(days=round(doy) - 1)
    return f"{d.day} {RU_MONTHS_GENITIVE[d.month - 1]}"


def build_analog_narrative(zone, analog_years):
    """Baut aus den Analog-Jahren einen lesbaren Fließtext statt einer reinen Stichpunktliste."""
    if not analog_years:
        return None

    years_str = ", ".join(str(a["jahr"]) for a in analog_years)

    gdd_vals = [a["saison_gdd"] for a in analog_years if a["saison_gdd"] is not None]
    heat_vals = [a["saison_hitzetage"] for a in analog_years if a["saison_hitzetage"] is not None]
    dry_vals = [a["saison_trockenperiode"] for a in analog_years if a["saison_trockenperiode"] is not None]
    frost_doy_vals = [a["herbstfrost_doy"] for a in analog_years if a.get("herbstfrost_doy") is not None and not pd.isna(a.get("herbstfrost_doy"))]

    avg_gdd = sum(gdd_vals) / len(gdd_vals) if gdd_vals else None
    avg_heat = sum(heat_vals) / len(heat_vals) if heat_vals else None
    avg_dry = sum(dry_vals) / len(dry_vals) if dry_vals else None
    avg_frost_doy = sum(frost_doy_vals) / len(frost_doy_vals) if frost_doy_vals else None

    zone_gdd = zone.get("_gdd")
    if avg_gdd is not None and zone_gdd:
        if avg_gdd > zone_gdd * 1.08:
            charakter = "теплее обычного"
        elif avg_gdd < zone_gdd * 0.92:
            charakter = "холоднее обычного"
        else:
            charakter = "близко к обычной норме"
    else:
        charakter = "неизвестного характера"

    satz = f"Весна этого года по срокам заморозков и осадкам больше всего похожа на {years_str} годы. "
    satz += f"В эти годы лето было {charakter}"
    if avg_gdd is not None:
        satz += f" (в среднем {round(avg_gdd)} GDD"
        if avg_heat is not None:
            satz += f", {round(avg_heat)} жарких дней"
        if avg_dry is not None:
            satz += f", засуха до {round(avg_dry)} дней подряд"
        satz += ")"
    satz += ". "

    frost_readable = _doy_to_readable(avg_frost_doy)
    if frost_readable:
        satz += f"Первые осенние заморозки в эти годы приходили примерно **{frost_readable}**."
    else:
        satz += "Данных о сроках осенних заморозков в эти годы недостаточно."

    return satz


def build_zones():
    """Kombiniert statische Metadaten mit den neuesten CSV-Klimadaten (30j-Basis)."""
    long_term = load_latest_by_zone(LONG_TERM_CSV)
    short_term = load_latest_by_zone(SHORT_TERM_CSV)

    zones = {}
    for zone_id, meta in ZONE_STATIC.items():
        zone = dict(meta)
        lt = long_term.get(zone_id)
        fb = CLIMATE_FALLBACK[zone_id]

        if lt is not None and "waermesumme_gdd_mittel_30j" in lt:
            # Rohwerte 30j (stabile Klimanorm) und 10j (aktuellerer Trend) getrennt einlesen
            osadki_30j = lt["niederschlag_mittel_pro_saison_mm_30j"]
            temp_30j = lt["temperatur_mittel_c_30j"]
            gdd_30j = lt["waermesumme_gdd_mittel_30j"]
            trocken_30j = lt["laengste_trockenperiode_tage_mittel_30j"]
            hitze_30j = lt["hitzetage_ueber_30c_mittel_30j"]
            spring_doy_30j = _md_to_doy(lt.get("letzter_fruehjahrsfrost_datum_approx_30j"))
            fall_doy_30j = _md_to_doy(lt.get("erster_herbstfrost_datum_approx_30j"))

            osadki_10j = lt.get("niederschlag_mittel_pro_saison_mm_10j")
            temp_10j = lt.get("temperatur_mittel_c_10j")
            gdd_10j = lt.get("waermesumme_gdd_mittel_10j")
            trocken_10j = lt.get("laengste_trockenperiode_tage_mittel_10j")
            hitze_10j = lt.get("hitzetage_ueber_30c_mittel_10j")
            spring_doy_10j = _md_to_doy(lt.get("letzter_fruehjahrsfrost_datum_approx_10j"))
            fall_doy_10j = _md_to_doy(lt.get("erster_herbstfrost_datum_approx_10j"))

            # Geblendete Werte (Trend-Gewichtung) als OFFIZIELLE Werte fürs Scoring —
            # statt reiner 30-Jahres-Norm wird der jüngere 10-Jahres-Trend stärker
            # einbezogen (siehe TREND_GEWICHT_10J).
            zone["осадки_мм"] = _blend_trend(osadki_10j, osadki_30j)
            zone["температура_ср"] = _blend_trend(temp_10j, temp_30j)
            zone["_gdd"] = _blend_trend(gdd_10j, gdd_30j)
            zone["_trockenperiode"] = _blend_trend(trocken_10j, trocken_30j)
            zone["_hitzetage"] = _blend_trend(hitze_10j, hitze_30j)

            spring_doy_blend = _blend_trend(spring_doy_10j, spring_doy_30j)
            fall_doy_blend = _blend_trend(fall_doy_10j, fall_doy_30j)
            if spring_doy_blend is not None and fall_doy_blend is not None:
                zone["_vegetationsfenster_tage"] = round(fall_doy_blend - spring_doy_blend)
                zone["_letzter_fruehjahrsfrost"] = _doy_to_md(spring_doy_blend)
                zone["_erster_herbstfrost"] = _doy_to_md(fall_doy_blend)
            else:
                zone["_vegetationsfenster_tage"] = fb["vegetationsfenster_tage"]
                zone["_letzter_fruehjahrsfrost"] = lt.get("letzter_fruehjahrsfrost_datum_approx_30j", "неизвестно")
                zone["_erster_herbstfrost"] = lt.get("erster_herbstfrost_datum_approx_30j", "неизвестно")

            # Rohe 30j/10j-Werte weiterhin separat für Anzeige & Trend-Transparenz aufheben
            zone["_осадки_30j"] = osadki_30j
            zone["_температура_30j"] = temp_30j
            zone["_gdd_30j"] = gdd_30j
            zone["_osadki_10j"] = osadki_10j
            zone["_temperatura_10j"] = temp_10j
            zone["_gdd_10j"] = gdd_10j

            # Trend-Richtung/-Stärke für Transparenz in der UI
            if temp_10j is not None:
                zone["_temp_trend_delta"] = round(temp_10j - temp_30j, 1)
            else:
                zone["_temp_trend_delta"] = None
            if osadki_10j is not None:
                zone["_osadki_trend_delta"] = round(osadki_10j - osadki_30j, 1)
            else:
                zone["_osadki_trend_delta"] = None

            zone["_datenquelle"] = (
                f"CSV (Trend-Blend {int(TREND_GEWICHT_10J*100)}%×10J + {int((1-TREND_GEWICHT_10J)*100)}%×30J; "
                f"30J-Basis: {lt['zeitraum_30j_von']}–{lt['zeitraum_30j_bis']})"
            )
        else:
            zone["осадки_мм"] = fb["осадки_мм"]
            zone["температура_ср"] = fb["температура_ср"]
            zone["_gdd"] = fb["gdd"]
            zone["_trockenperiode"] = fb["trockenperiode"]
            zone["_hitzetage"] = fb["hitzetage"]
            zone["_vegetationsfenster_tage"] = fb["vegetationsfenster_tage"]
            zone["_letzter_fruehjahrsfrost"] = "неизвестно (заглушка)"
            zone["_erster_herbstfrost"] = "неизвестно (заглушка)"
            zone["_datenquelle"] = "Platzhalter (noch keine CSV-Daten gefunden)"

        st_data = short_term.get(zone_id)
        if st_data is not None:
            zone["_kurzfristig_zeitraum"] = f"{st_data['zeitraum_von']} – {st_data['zeitraum_bis']}"
            zone["_niederschlag_fruehjahr_bisher"] = st_data.get("niederschlag_summe_mm_bisher")
            zone["_tage_ausgewertet"] = int(st_data["tage_ausgewertet"]) if st_data.get("tage_ausgewertet") else None
            zone["_erwaermung_beginn_dieses_jahr"] = st_data.get("beginn_stabiler_erwaermung")

            frost_str = st_data.get("letzter_beobachteter_frost")
            if frost_str and frost_str != "не наблюдался":
                zone["_frost_dieses_jahr"] = frost_str
                zone["_frost_dieses_jahr_doy"] = _md_to_doy(frost_str[5:])  # "YYYY-MM-DD" -> "MM-DD"
                zone["_tage_seit_frost"] = st_data.get("tage_seit_letztem_frost")
            else:
                zone["_frost_dieses_jahr"] = "не наблюдался"
                zone["_frost_dieses_jahr_doy"] = None

            # Abweichung ggü. 30-jähriger Norm berechnen, wenn beides vorliegt
            norm_doy = _md_to_doy(zone.get("_letzter_fruehjahrsfrost"))
            if zone.get("_frost_dieses_jahr_doy") is not None and norm_doy is not None:
                zone["_frost_abweichung_tage"] = zone["_frost_dieses_jahr_doy"] - norm_doy
            else:
                zone["_frost_abweichung_tage"] = None

        zones[zone_id] = zone
    return zones


ZONES = build_zones()
PER_YEAR_DATA = load_all_per_year(PER_YEAR_CSV)
MONTHLY_DATA = load_all_monthly(MONTHLY_CSV)
WEEKLY_DATA = load_all_weekly(WEEKLY_CSV)
DAILY_SPRING_DF = load_daily_spring(DAILY_SPRING_CSV)


def render_zone_map(selected_zone_id):
    """Baut eine folium-Karte mit den 4 Klimazonen als farbige Breitengrad-Streifen."""
    m = folium.Map(
        location=[55.5, 73.5],
        zoom_start=6,
        tiles="CartoDB positron",
        attributionControl=False,  # Standard-Attribution (inkl. Leaflet-Praefix) deaktivieren
    )
    # Eigene, schlichte Attribution ohne Leaflet-Branding ergaenzen -- die
    # Namensnennung fuer OpenStreetMap/CARTO bleibt Pflicht, nur der
    # Leaflet-eigene Zusatz (inkl. Ukraine-Flagge) wird weggelassen.
    attribution_js = (
        f"L.control.attribution({{prefix: false, position: 'bottomright'}})"
        f".addTo({m.get_name()})"
        f".addAttribution('\u00a9 OpenStreetMap contributors \u00a9 CARTO');"
    )
    m.get_root().script.add_child(folium.Element(attribution_js))

    for zone_id, info in ZONE_MAP_INFO.items():
        is_selected = zone_id == selected_zone_id
        bounds = [
            [info["lat_bis"], MAP_LON_WEST],
            [info["lat_von"], MAP_LON_EAST],
        ]
        folium.Rectangle(
            bounds=bounds,
            color="#e53e3e" if is_selected else info["farbe"],
            weight=4 if is_selected else 1.5,
            fill=True,
            fill_color=info["farbe"],
            fill_opacity=0.35 if is_selected else 0.15,
            popup=ZONES[zone_id]["name_ru"],
            tooltip=ZONES[zone_id]["name_ru"],
        ).add_to(m)

        folium.Marker(
            location=[info["lat_center"], info["lon_center"]],
            tooltip=ZONES[zone_id]["name_ru"],
            icon=folium.Icon(
                color="red" if is_selected else "blue",
                icon="leaf" if is_selected else "info-sign",
            ),
        ).add_to(m)

    return m

# Jede Kultur jetzt zusätzlich mit:
# - необходимая_gdd: ungefähre Wärmesumme (Basis 5°C) bis zur Reife
# - макс_дней_засухи: wie viele aufeinanderfolgende trockene Tage die Kultur toleriert
# - жаростойкость: qualitative Hitzetoleranz (низкая/средняя/высокая)
# Alles Richtwerte aus allgemeiner Agrarliteratur — für den echten Einsatz zu verfeinern.
CROPS = {
    "Яровая пшеница": {
        "мин_дни_роста": 85, "необходимая_gdd": 1500, "макс_дней_засухи": 10, "жаростойкость": "средняя",
        "потребность_вода_мм": 250,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Чернозём южный", "Серая лесная"],
        "ph_мин": 5.5, "ph_макс": 7.0,
        "урожайность_ц_га": 22,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Ячмень": {
        "мин_дни_роста": 75, "необходимая_gdd": 1300, "макс_дней_засухи": 12, "жаростойкость": "высокая",
        "потребность_вода_мм": 220,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Чернозём южный", "Серая лесная", "Подзолистая"],
        "ph_мин": 5.5, "ph_макс": 7.5,
        "урожайность_ц_га": 24,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Овёс": {
        "мин_дни_роста": 80, "необходимая_gdd": 1400, "макс_дней_засухи": 8, "жаростойкость": "низкая",
        "потребность_вода_мм": 260,
        "подходящие_почвы": ["Подзолистая", "Серая лесная", "Чернозём выщелоченный"],
        "ph_мин": 5.0, "ph_макс": 7.0,
        "урожайность_ц_га": 20,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Горох": {
        "мин_дни_роста": 70, "необходимая_gdd": 1200, "макс_дней_засухи": 8, "жаростойкость": "низкая",
        "потребность_вода_мм": 230,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Серая лесная"],
        "ph_мин": 6.0, "ph_макс": 7.5,
        "урожайность_ц_га": 18,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "связывающий",
    },
    "Чечевица": {
        "мин_дни_роста": 75, "необходимая_gdd": 1300, "макс_дней_засухи": 14, "жаростойкость": "средняя",
        "потребность_вода_мм": 200,
        "подходящие_почвы": ["Чернозём обыкновенный", "Чернозём южный"],
        "ph_мин": 6.0, "ph_макс": 8.0,
        "урожайность_ц_га": 12,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "связывающий",
    },
    "Лён масличный": {
        "мин_дни_роста": 80, "необходимая_gdd": 1350, "макс_дней_засухи": 10, "жаростойкость": "средняя",
        "потребность_вода_мм": 210,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный", "Серая лесная"],
        "ph_мин": 5.5, "ph_макс": 7.0,
        "урожайность_ц_га": 9,
        "интервал_севооборота_лет": 3,
        "эффект_азот": "нейтральный",
    },
    "Рапс яровой": {
        "мин_дни_роста": 90, "необходимая_gdd": 1600, "макс_дней_засухи": 8, "жаростойкость": "низкая",
        "потребность_вода_мм": 280,
        "подходящие_почвы": ["Чернозём выщелоченный", "Чернозём обыкновенный"],
        "ph_мин": 5.8, "ph_макс": 7.2,
        "урожайность_ц_га": 14,
        "интервал_севооборота_лет": 4,
        "эффект_азот": "истощающий",
    },
    "Подсолнечник": {
        "мин_дни_роста": 110, "необходимая_gdd": 2000, "макс_дней_засухи": 16, "жаростойкость": "высокая",
        "потребность_вода_мм": 300,
        "подходящие_почвы": ["Чернозём обыкновенный", "Чернозём южный"],
        "ph_мин": 6.0, "ph_макс": 7.5,
        "урожайность_ц_га": 16,
        "интервал_севооборота_лет": 4,
        "эффект_азот": "истощающий",
    },
    "Гречиха": {
        "мин_дни_роста": 75, "необходимая_gdd": 1200, "макс_дней_засухи": 7, "жаростойкость": "низкая",
        "потребность_вода_мм": 240,
        "подходящие_почвы": ["Серая лесная", "Чернозём выщелоченный", "Подзолистая"],
        "ph_мин": 5.0, "ph_макс": 6.5,
        "урожайность_ц_га": 10,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
    "Озимая рожь": {
        "мин_дни_роста": 90, "необходимая_gdd": 1400, "макс_дней_засухи": 12, "жаростойкость": "высокая",
        "потребность_вода_мм": 240,
        "подходящие_почвы": ["Подзолистая", "Серая лесная", "Чернозём выщелоченный"],
        "ph_мин": 5.0, "ph_макс": 7.0,
        "урожайность_ц_га": 20,
        "интервал_севооборота_лет": 2,
        "эффект_азот": "нейтральный",
    },
}

# Профиль сроков посева: смещение (дней) относительно даты последнего
# весеннего заморозка в зоне. Отрицательное значение = можно сеять ДО
# заморозка (культура переносит лёгкие заморозки). Положительное = сеют
# ПОСЛЕ заморозка, чем чувствительнее культура — тем позже. "озимый" сеется
# осенью, формула через заморозок к нему не применяется.
SOWING_PROFILE = {
    "Яровая пшеница": {"тип_посева": "яровой", "смещение_дней": 0},
    "Ячмень": {"тип_посева": "яровой", "смещение_дней": -7},
    "Овёс": {"тип_посева": "яровой", "смещение_дней": -7},
    "Горох": {"тип_посева": "яровой", "смещение_дней": -5},
    "Чечевица": {"тип_посева": "яровой", "смещение_дней": 8},
    "Лён масличный": {"тип_посева": "яровой", "смещение_дней": 10},
    "Рапс яровой": {"тип_посева": "яровой", "смещение_дней": 15},
    "Подсолнечник": {"тип_посева": "яровой", "смещение_дней": 18},
    "Гречиха": {"тип_посева": "яровой", "смещение_дней": 12},
    "Озимая рожь": {"тип_посева": "озимый", "смещение_дней": None},
}

RU_MONTHS_GENITIVE = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

RU_MONTHS_PREPOSITIONAL = [
    "январе", "феврале", "марте", "апреле", "мае", "июне",
    "июле", "августе", "сентябре", "октябре", "ноябре", "декабре",
]

# Ab wie vielen ausgewerteten Tagen (von insgesamt 68 im Fenster 1.3.-7.5.)
# gilt der beobachtete Frost dieses Jahres als verlässlich genug, um die
# 30-jährige Norm zu ersetzen, statt nur als vorläufige Teilbeobachtung.
MIN_TAGE_FUER_AKTUELLEN_FROST = 60


def _estimate_sowing_doy(crop_name, zone):
    """
    Interne Hilfsfunktion: liefert (sowing_doy, quelle_hinweis) oder (None, None)
    falls keine Daten vorliegen. Wird sowohl fuer die Saat- als auch die
    Ernte-Schaetzung genutzt, damit beide konsistent dieselbe Basis nutzen.
    """
    profile = SOWING_PROFILE.get(crop_name)
    if profile is None or profile["тип_посева"] == "озимый":
        return None, None

    tage_ausgewertet = zone.get("_tage_ausgewertet") or 0
    frost_doy_aktuell = zone.get("_frost_dieses_jahr_doy")

    if frost_doy_aktuell is not None and tage_ausgewertet >= MIN_TAGE_FUER_AKTUELLEN_FROST:
        frost_doy = frost_doy_aktuell
        quelle_hinweis = " (по факт. заморозку этого года)"
    else:
        frost_doy = _md_to_doy(zone.get("_letzter_fruehjahrsfrost"))
        quelle_hinweis = ""

    if frost_doy is None:
        return None, None

    return frost_doy + profile["смещение_дней"], quelle_hinweis


def estimate_sowing_date(crop_name, zone):
    """
    Schaetzt das Saatdatum: озимые -> fester Herbsttext, яровые -> letzter
    Fruehjahrsfrost + kulturspezifischer Versatz in Tagen.

    Nutzt bevorzugt den TATSAECHLICH BEOBACHTETEN Frost dieses Jahres (aus den
    Fruehjahrs-Tagesdaten), falls das Beobachtungsfenster ausreichend
    abgeschlossen ist -- das macht die Schaetzung aktueller als eine reine
    30-Jahres-Norm. Faellt sonst auf die historische Norm zurueck.
    """
    profile = SOWING_PROFILE.get(crop_name)
    if profile is None:
        return "нет данных"
    if profile["тип_посева"] == "озимый":
        return "осень (конец августа — сентябрь)"

    sowing_doy, quelle_hinweis = _estimate_sowing_doy(crop_name, zone)
    if sowing_doy is None:
        return "нет данных о заморозках"

    sowing_date = date(REFERENCE_YEAR_FOR_DOY, 1, 1) + timedelta(days=sowing_doy - 1)
    return f"~{sowing_date.day} {RU_MONTHS_GENITIVE[sowing_date.month - 1]}{quelle_hinweis}"


def estimate_harvest_window(crop_name, zone):
    """
    Schaetzt den Erntezeitraum: Saatdatum + Mindest-Wachstumstage der Kultur.
    Prueft zusaetzlich, ob die geschaetzte Ernte gefaehrlich nah am (geblendeten)
    ersten Herbstfrost der Zone liegt -- dann Risikohinweis.

    WICHTIG: Dies ist eine reine Reifezeit-Schaetzung (Saatdatum + Mindesttage).
    Der Monat der geschaetzten Ernte (harvest_month) wird zusaetzlich
    zurueckgegeben, damit characterize_harvest_wetness() gezielt fuer GENAU
    diesen Monat nachschauen kann, wie nass/trocken vergleichbare
    historische Jahre dort waren -- statt eines pauschalen Draenage-Hinweises.
    """
    crop = CROPS.get(crop_name)
    profile = SOWING_PROFILE.get(crop_name)
    if crop is None or profile is None:
        return {"дата": "нет данных", "риск": False, "риск_текст": "", "harvest_month": None}
    if profile["тип_посева"] == "озимый":
        return {"дата": "лето следующего года (июль)", "риск": False, "риск_текст": "", "harvest_month": 7}

    sowing_doy, _ = _estimate_sowing_doy(crop_name, zone)
    if sowing_doy is None:
        return {"дата": "нет данных о заморозках", "риск": False, "риск_текст": "", "harvest_month": None}

    harvest_doy = sowing_doy + crop["мин_дни_роста"]
    harvest_date = date(REFERENCE_YEAR_FOR_DOY, 1, 1) + timedelta(days=harvest_doy - 1)
    date_str = f"~{harvest_date.day} {RU_MONTHS_GENITIVE[harvest_date.month - 1]}"

    fall_frost_doy = _md_to_doy(zone.get("_erster_herbstfrost"))
    risk = False
    risk_text = ""
    if fall_frost_doy is not None:
        zapas_dney = fall_frost_doy - harvest_doy
        if zapas_dney < 0:
            risk = True
            risk_text = f"⚠️ позже обычного первого заморозка ({zone.get('_erster_herbstfrost')})"
        elif zapas_dney < 10:
            risk = True
            risk_text = f"⚠️ близко к обычному заморозку (запас {zapas_dney} дн.)"

    return {"дата": date_str, "риск": risk, "риск_текст": risk_text, "harvest_month": harvest_date.month}


SOIL_TYPES_INFO = {
    "Чернозём южный": {
        "гумус": "4–6%",
        "типичная_зона": "Степь",
        "описание": "Самый южный и наименее плодородный из чернозёмов. Формируется в засушливых "
                     "степных условиях, тоньше гумусовый слой, но структура хорошая — неплохо "
                     "удерживает влагу. Подходит для засухоустойчивых культур.",
    },
    "Чернозём обыкновенный": {
        "гумус": "6–8%",
        "типичная_зона": "Южная лесостепь",
        "описание": "Промежуточный тип по плодородию — больше гумуса и влаги, чем у южного "
                     "чернозёма, но суше и беднее, чем выщелоченный.",
    },
    "Чернозём выщелоченный": {
        "гумус": "8–10%",
        "типичная_зона": "Северная лесостепь",
        "описание": "Один из самых плодородных типов почв в регионе — толстый гумусовый "
                     "горизонт, хорошо удерживает влагу и питательные вещества.",
    },
    "Серая лесная": {
        "гумус": "2–4%",
        "типичная_зона": "Переходная зона к лесу",
        "описание": "Переходный тип между чернозёмом и подзолистыми почвами. Менее плодородна, "
                     "чем чернозёмы, но лучше подзолистых почв севера.",
    },
    "Подзолистая": {
        "гумус": "<2%",
        "типичная_зона": "Север / тайга",
        "описание": "Самая бедная почва в регионе — низкое содержание гумуса, кислая реакция. "
                     "Требует более неприхотливых культур с низкими требованиями к плодородию.",
    },
}
SOIL_TYPES = list(SOIL_TYPES_INFO.keys())

DRAINAGE_INFO = {
    "Хороший дренаж": {
        "коэфф": 0.9,
        "описание": "Вода уходит быстро, за 1–3 часа после дождя на поверхности не остаётся луж. "
                     "Обычно песчаные/супесчаные почвы, участки на склоне или возвышенности.",
        "признаки": "Нет луж после дождя; почва рыхлая, комья легко рассыпаются; уклон местности заметен",
    },
    "Средний дренаж": {
        "коэфф": 1.0,
        "описание": "Типичная ситуация для большинства чернозёмов — вода уходит за 1–2 дня, "
                     "кратковременное переувлажнение после сильных дождей не страшно.",
        "признаки": "Лужи исчезают в течение суток; почва средней плотности",
    },
    "Застойное (сырое)": {
        "коэфф": 1.15,
        "описание": "Вода застаивается на несколько дней и дольше — плоский рельеф, глинистая "
                     "подпочва, близкие грунтовые воды или низина/пойма.",
        "признаки": "Лужи держатся 3+ дня; почва липкая, плохо крошится; растительность-индикатор "
                     "переувлажнения (осока, камыш)",
    },
}


# Пороговые значения "комфортных" хитдней по уровню жаростойкости —
# используются для расчёта штрафа за жару.
HEAT_TOLERANCE_THRESHOLDS = {"низкая": 3, "средняя": 8, "высокая": 15}


# ---------------------------------------------------------------------------
# ЛОГИКА РАСЧЁТА
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "почва": 18,
    "ph": 13,
    "окно": 18,
    "gdd": 13,
    "вода": 13,
    "жара": 5,
    "урожайность": 10,
    "предшественник": 10,
}


def score_crop(crop_name, crop, zone, soil_type, ph, drainage, weights, return_details=False, predecessor_effect=None):
    """
    Возвращает итоговый балл (0-100) пригодности культуры для заданных условий.

    weights: dict с ключами "почва", "ph", "окно", "gdd", "вода", "жара",
    "урожайность", "предшественник" — относительные приоритеты пользователя
    (не обязательно должны давать в сумме 100, функция нормирует сама).

    Каждый под-балл сначала нормируется в диапазон 0-1, затем комбинируется
    с весами пользователя.

    predecessor_effect: эффект_азот последней культуры на этом поле (или
    None, если неизвестно) — используется для оценки влияния предшественника.

    return_details=True: возвращает (итоговый_балл, sub_scores) вместо
    только числа — используется для текстового объяснения результата.
    """

    # 1. Соответствие типа почвы (0-1)
    if soil_type in crop["подходящие_почвы"]:
        soil_score = 1.0
    elif soil_type in zone["почвы_типичные"]:
        soil_score = 0.4  # почва не идеальна, но типична для зоны
    else:
        soil_score = 0.0

    # 2. Соответствие pH (0-1)
    if crop["ph_мин"] <= ph <= crop["ph_макс"]:
        ph_score = 1.0
    else:
        distance = min(abs(ph - crop["ph_мин"]), abs(ph - crop["ph_макс"]))
        ph_score = max(0.0, 1 - distance * 0.4)

    # 3. Вегетационное окно (0-1) — из РЕАЛЬНЫХ дат последнего весеннего
    # и первого осеннего заморозка (не просто "безморозные дни" как раньше)
    окно = zone["_vegetationsfenster_tage"]
    if окно >= crop["мин_дни_роста"]:
        запас = окно - crop["мин_дни_роста"]
        window_score = min(1.0, 0.6 + запас * 0.012)
    else:
        дефицит = crop["мин_дни_роста"] - окно
        window_score = max(0.0, 0.6 - дефицит * 0.06)

    # 4. Тепловая сумма / GDD (0-1) — хватает ли зоне тепла для вызревания
    gdd_zone = zone["_gdd"]
    gdd_needed = crop["необходимая_gdd"]
    if gdd_zone >= gdd_needed:
        избыток = gdd_zone - gdd_needed
        gdd_score = min(1.0, 0.6 + избыток * 0.0005)
    else:
        дефицит_gdd = gdd_needed - gdd_zone
        gdd_score = max(0.0, 0.6 - дефицит_gdd * 0.001)

    # 5. Водообеспеченность (0-1) — сумма осадков ПЛЮС риск длинной засухи
    осадки = zone["осадки_мм"]
    потребность = crop["потребность_вода_мм"]
    if drainage == "Застойное (сырое)":
        осадки *= 1.15
    elif drainage == "Хороший дренаж":
        осадки *= 0.9
    разница = abs(осадки - потребность)
    precip_score = max(0.0, 1 - разница / 225)

    засуха_зона = zone["_trockenperiode"]
    засуха_допуск = crop["макс_дней_засухи"]
    if засуха_зона <= засуха_допуск:
        dry_spell_score = 1.0
    else:
        превышение = засуха_зона - засуха_допуск
        dry_spell_score = max(0.0, 1 - превышение * 0.1)

    water_score = (precip_score + dry_spell_score) / 2

    # 6. Тепловой стресс (0-1) — количество жарких дней (>30°C) против
    # жаростойкости культуры
    хитдни_зона = zone["_hitzetage"]
    комфортный_порог = HEAT_TOLERANCE_THRESHOLDS[crop["жаростойкость"]]
    if хитдни_зона <= комфортный_порог:
        heat_score = 1.0
    else:
        превышение_жары = хитдни_зона - комфортный_порог
        heat_score = max(0.0, 1 - превышение_жары * 0.08)

    # 7. Урожайный потенциал (0-1, нормировано по максимуму в таблице)
    max_yield = max(c["урожайность_ц_га"] for c in CROPS.values())
    yield_score = min(1.0, crop["урожайность_ц_га"] / max_yield)

    # 8. Влияние предшественника (0-1) — насколько удачно сочетается азотный
    # эффект предыдущей культуры на этом поле с эффектом культуры-кандидата
    predecessor_score = predecessor_effect_score(predecessor_effect, crop["эффект_азот"])

    sub_scores = {
        "почва": soil_score,
        "ph": ph_score,
        "окно": window_score,
        "gdd": gdd_score,
        "вода": water_score,
        "жара": heat_score,
        "урожайность": yield_score,
        "предшественник": predecessor_score,
    }

    total_weight = sum(weights.values())
    if total_weight == 0:
        return (0.0, sub_scores) if return_details else 0.0

    score = sum(sub_scores[key] * weights[key] for key in sub_scores) / total_weight
    final_score = round(score * 100, 1)
    return (final_score, sub_scores) if return_details else final_score


FACTOR_LABELS = {
    "почва": "тип почвы",
    "ph": "кислотность почвы (pH)",
    "окно": "длина вегетационного окна",
    "gdd": "тепловая сумма (GDD)",
    "вода": "влагообеспеченность",
    "жара": "жаростойкость",
    "урожайность": "урожайный потенциал",
    "предшественник": "влияние предыдущей культуры (азот)",
}

# Bewertung (0-1), wie gut eine Kultur nach der jeweils VORHERIGEN Kultur auf
# demselben Feld passt — basierend auf эффект_азот (связывающий/нейтральный/
# истощающий). Eine stickstoffbindende Vorfrucht (z.B. Erbse) ist ideal vor
# einer stickstoffzehrenden Folgekultur; zwei zehrende Kulturen hintereinander
# sind ungünstig — unabhängig davon, ob es dieselbe Kultur ist oder nicht.
PREDECESSOR_EFFECT_TABLE = {
    ("связывающий", "истощающий"): 1.0,
    ("связывающий", "нейтральный"): 0.85,
    ("связывающий", "связывающий"): 0.8,
    ("истощающий", "истощающий"): 0.3,
    ("истощающий", "связывающий"): 1.0,
    ("истощающий", "нейтральный"): 0.6,
    ("нейтральный", "истощающий"): 0.6,
    ("нейтральный", "связывающий"): 0.8,
    ("нейтральный", "нейтральный"): 0.7,
}


def predecessor_effect_score(prev_effect, candidate_effect):
    """Score (0-1) für die Kombination Vorfrucht -> Kandidat, siehe PREDECESSOR_EFFECT_TABLE."""
    if prev_effect is None:
        return 0.7  # keine Historie bekannt -> neutral, weder Bonus noch Malus
    return PREDECESSOR_EFFECT_TABLE.get((prev_effect, candidate_effect), 0.6)


def get_predecessor_effect(history):
    """Ermittelt эффект_азот der zuletzt (juengstes Jahr) angebauten Kultur, oder None."""
    if not history:
        return None
    letztes_jahr = max(history.keys())
    letzte_kultur = history[letztes_jahr]
    return CROPS.get(letzte_kultur, {}).get("эффект_азот")


def explain_predecessor_relationship(crop_name, crop_azot_effect, history):
    """
    Erklaert IMMER (nicht nur wenn es zufaellig unter die Top-3-Faktoren faellt)
    die Beziehung zwischen der letzten Kultur auf dem Feld und dem aktuellen
    Kandidaten -- genau die Frage "beeinflussen sich Kulturen gegenseitig
    negativ/positiv".
    """
    if not history:
        return (
            f"Влияние предшественника для **{crop_name}**: история посевов пуста, "
            f"поэтому этот фактор оценён нейтрально (0.7 из 1.0)."
        )

    letztes_jahr = max(history.keys())
    letzte_kultur = history[letztes_jahr]
    letzter_effekt = CROPS.get(letzte_kultur, {}).get("эффект_азот")
    score = predecessor_effect_score(letzter_effekt, crop_azot_effect)

    if score >= 0.95:
        charakter = "отличное сочетание — азот, оставшийся после предшественника, пойдёт на пользу"
    elif score >= 0.75:
        charakter = "хорошее сочетание"
    elif score >= 0.55:
        charakter = "нейтральное сочетание — заметного влияния друг на друга нет"
    else:
        charakter = "неудачное сочетание — обе культуры истощают почву без восстановления азота между ними"

    return (
        f"Влияние предшественника для **{crop_name}**: в {letztes_jahr} году на поле "
        f"росла **{letzte_kultur}** ({letzter_effekt} эффект на азот), у {crop_name} — "
        f"{crop_azot_effect} эффект. Это {charakter}."
    )


def explain_best_crop(crop_name, sub_scores, weights, top_n=3):
    """
    Erklärt, WARUM eine Kultur den höchsten Score bekam — zeigt die
    Faktoren, die (Teilwert × Gewicht) am meisten zum Gesamtergebnis
    beigetragen haben, nicht nur den nackten Endwert.
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return f"**{crop_name}** — недостаточно данных для объяснения (все веса на нуле)."

    contributions = {k: sub_scores[k] * weights[k] / total_weight * 100 for k in sub_scores}
    top_factors = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    parts = [f"{FACTOR_LABELS[k]} ({round(v, 1)} балла)" for k, v in top_factors]

    return f"**{crop_name}** получила наивысший балл прежде всего благодаря: {', '.join(parts)}."


def explain_weak_crop(crop_name, sub_scores, weights, top_n=3):
    """
    Erklärt, WARUM eine (nicht durch Rotation blockierte) Kultur schlecht
    abschneidet — zeigt die Faktoren mit dem größten Punktverlust
    (Gewicht × fehlender Teilwert), nicht nur den nackten Endwert.
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return f"**{crop_name}** — недостаточно данных для объяснения (все веса на нуле)."

    deficits = {k: (1 - sub_scores[k]) * weights[k] / total_weight * 100 for k in sub_scores}
    worst_factors = sorted(deficits.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    worst_factors = [(k, v) for k, v in worst_factors if v > 0.5]  # nur nennenswerte Schwächen
    if not worst_factors:
        return f"**{crop_name}** получила невысокий балл из-за небольшого отставания сразу по нескольким параметрам."
    parts = [f"{FACTOR_LABELS[k]} (потеряно {round(v, 1)} балла)" for k, v in worst_factors]

    return f"**{crop_name}** получила невысокий балл из-за: {', '.join(parts)}."


def compare_two_crops(name1, sub_scores1, name2, sub_scores2, weights, top_n=3, threshold=0.5):
    """
    Vergleicht zwei Kulturen direkt: zeigt, in welchen Faktoren die eine
    gegenüber der anderen einen Punktvorteil hat (gewichteter Beitrag),
    in beide Richtungen — statt nur die Endsumme gegenüberzustellen.
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return ""

    contrib1 = {k: sub_scores1[k] * weights[k] / total_weight * 100 for k in sub_scores1}
    contrib2 = {k: sub_scores2[k] * weights[k] / total_weight * 100 for k in sub_scores2}
    diffs = {k: contrib1[k] - contrib2[k] for k in contrib1}

    wins1 = sorted([(k, v) for k, v in diffs.items() if v > threshold], key=lambda kv: kv[1], reverse=True)[:top_n]
    wins2 = sorted([(k, v) for k, v in diffs.items() if v < -threshold], key=lambda kv: kv[1])[:top_n]

    parts = []
    if wins1:
        txt1 = ", ".join(f"{FACTOR_LABELS[k]} (+{round(v, 1)} балла)" for k, v in wins1)
        parts.append(f"**{name1}** выигрывает у **{name2}** по: {txt1}.")
    if wins2:
        txt2 = ", ".join(f"{FACTOR_LABELS[k]} (+{round(-v, 1)} балла)" for k, v in wins2)
        parts.append(f"**{name2}**, в свою очередь, лучше по: {txt2}.")

    if not parts:
        return f"**{name1}** и **{name2}** показывают очень похожие результаты по всем параметрам."
    return " ".join(parts)


def explain_rotation_exclusion(crop_name, crop_data, history, reason=None):
    """Erklärt, warum eine Kultur ausgeschlossen wurde — Wiederholung ODER Nährstoffkette."""
    if reason == "истощение":
        letztes_jahr = max(history.keys())
        letzte_kultur = history[letztes_jahr]
        return (
            f"**{crop_name}** исключена: в {letztes_jahr} году на поле уже росла истощающая "
            f"почву культура ({letzte_kultur}), а {crop_name} тоже истощающая — две истощающие "
            f"культуры подряд истощат почву без восстановления азота."
        )

    gap = crop_data["интервал_севооборота_лет"]
    letzte_jahre = [year for year, planted in history.items() if planted == crop_name]
    if not letzte_jahre:
        return f"**{crop_name}** исключена из-за севооборота (требуется интервал {gap} г.)."
    letztes_jahr = max(letzte_jahre)
    return (
        f"**{crop_name}** исключена: уже сеялась на этом поле в {letztes_jahr} году, "
        f"а минимальный интервал севооборота для неё — {gap} г."
    )




def build_blocked_table(blocked_df, history):
    """
    Baut eine ZWECKMAESSIGE Tabelle fuer ausgeschlossene Kulturen -- zeigt
    Grund, geforderten Rotationsabstand und wann zuletzt gesaet wurde, statt
    einfach dieselben (hier irrelevanten) Anbau-Eigenschaften wie in der
    Haupttabelle zu wiederholen.
    """
    rows = []
    for _, row in blocked_df.iterrows():
        crop_name = row["Культура"]
        reason = row.get("Причина_блокировки", "")
        gap = CROPS[crop_name]["интервал_севооборота_лет"]

        if reason == "истощение":
            letztes_jahr = max(history.keys())
            letzte_kultur = history[letztes_jahr]
            causa_text = f"Истощение почвы (после {letzte_kultur})"
            posev_text = f"{letztes_jahr} — {letzte_kultur}"
            gap_text = "—"
            svoboden_text = "—"
        else:
            letzte_jahre = [year for year, planted in history.items() if planted == crop_name]
            letztes_jahr = max(letzte_jahre) if letzte_jahre else None
            causa_text = "Повтор культуры"
            posev_text = f"{letztes_jahr} год" if letztes_jahr else "—"
            gap_text = f"{gap} г."
            svoboden_text = f"{letztes_jahr + gap} год" if letztes_jahr else "—"

        rows.append({
            "Культура": crop_name,
            "Причина исключения": causa_text,
            "Когда сеялась/росла": posev_text,
            "Треб. интервал": gap_text,
            "Свободна с": svoboden_text,
        })
    return pd.DataFrame(rows)

def apply_rotation_filter(ranked_df, history):
    """
    Убирает культуры, которые нарушают минимальный интервал севооборота
    (та же самая культура слишком рано), А ТАКЖЕ культуры, которые продолжают
    цепочку истощения почвы (две истощающие культуры подряд — даже если это
    РАЗНЫЕ культуры) — оба случая помечаются с указанием причины.
    """
    current_year = max(history.keys()) + 1 if history else None
    letztes_jahr = max(history.keys()) if history else None
    letzte_kultur = history.get(letztes_jahr) if letztes_jahr is not None else None
    letzter_effekt = CROPS.get(letzte_kultur, {}).get("эффект_азот") if letzte_kultur else None

    filtered = []
    for _, row in ranked_df.iterrows():
        crop_name = row["Культура"]
        gap = CROPS[crop_name]["интервал_севооборота_лет"]
        blocked = False
        reason = ""

        # Grund 1: exakte Wiederholung derselben Kultur innerhalb des Mindestintervalls
        for year, planted_crop in history.items():
            if planted_crop == crop_name and current_year is not None:
                if (current_year - year) < gap:
                    blocked = True
                    reason = "повтор"
                    break

        # Grund 2: Nährstoff-Erschöpfungskette — zwei ИСТОЩАЮЩИЕ Kulturen in
        # Folge, unabhängig davon ob es dieselbe Kultur ist oder nicht
        if not blocked and letzter_effekt == "истощающий" and CROPS[crop_name]["эффект_азот"] == "истощающий":
            blocked = True
            reason = "истощение"

        row["Разрешено севооборотом"] = "Нет" if blocked else "Да"
        row["Причина_блокировки"] = reason
        filtered.append(row)
    return pd.DataFrame(filtered)


# ---------------------------------------------------------------------------
# ИНТЕРФЕЙС
# ---------------------------------------------------------------------------

st.title("🌾 Модель оптимального выбора культур — Омская область")
st.caption("Прототип: подбор 8–10 лучших культур для конкретного поля с учётом почвы, климата зоны и истории севооборота")

if not os.path.isfile(LONG_TERM_CSV) and not os.path.isfile(SHORT_TERM_CSV):
    st.info(
        "ℹ️ Пока не найдено ни одного файла с данными в `data/`. Используются "
        "заглушки. Запустите workflow'ы в GitHub Actions и сделайте `git pull`, "
        "чтобы подтянуть реальные климатические данные."
    )

st.header("1. Параметры почвы поля")
col1, col2 = st.columns(2)
with col1:
    soil_type = st.selectbox("Тип почвы", SOIL_TYPES)
    ph = st.slider("pH почвы", min_value=4.0, max_value=8.5, value=6.5, step=0.1)
with col2:
    humus = st.number_input("Содержание гумуса (%)", min_value=0.0, max_value=15.0, value=5.0, step=0.1)
    drainage = st.selectbox("Дренаж", ["Хороший дренаж", "Средний дренаж", "Застойное (сырое)"])

selected_soil_info = SOIL_TYPES_INFO[soil_type]
st.caption(
    f"**{soil_type}** — гумус обычно {selected_soil_info['гумус']}, типичная зона: "
    f"{selected_soil_info['типичная_зона']}. {selected_soil_info['описание']}"
)
with st.expander("Сравнение всех типов почв"):
    soil_table = pd.DataFrame([
        {"Тип почвы": name, "Гумус": info["гумус"], "Типичная зона": info["типичная_зона"]}
        for name, info in SOIL_TYPES_INFO.items()
    ])
    render_wrapped_table(soil_table, col_widths_pct=[25, 15, 60])

selected_drainage_info = DRAINAGE_INFO[drainage]
st.caption(f"**{drainage}**: {selected_drainage_info['описание']}")
with st.expander("Что означает каждый уровень дренажа"):
    drainage_table = pd.DataFrame([
        {
            "Дренаж": name,
            "Признаки на поле": info["признаки"],
            "Влияние на расчёт": f"×{info['коэфф']} к осадкам зоны",
        }
        for name, info in DRAINAGE_INFO.items()
    ])
    render_wrapped_table(drainage_table, col_widths_pct=[18, 55, 27])
    st.caption(
        "Плохой дренаж эффективно увеличивает доступную влагу для растений (вода дольше "
        "остаётся в почве), хороший дренаж — уменьшает её, даже при одинаковом количестве "
        "осадков в зоне."
    )

st.header("2. Зона расположения поля")
zone_id = st.selectbox(
    "Агроклиматическая зона (полоса ~100 км)",
    list(ZONES.keys()),
    format_func=lambda zid: ZONES[zid]["name_ru"],
)
zone = ZONES[zone_id]

if FOLIUM_AVAILABLE:
    zone_map = render_zone_map(zone_id)
    st_folium(zone_map, width=None, height=420, returned_objects=[])
else:
    st.info(
        "ℹ️ Для отображения карты установите дополнительные пакеты: "
        "`pip install folium streamlit-folium` и перезапустите приложение."
    )

# Analog-Jahre-Prognose — bewusst SICHTBAR, nicht in einem eingeklappten
# Expander versteckt, da das der zentrale "Vorhersage"-Baustein der App ist.
analog_years = find_analog_years(
    zone_id,
    zone.get("_frost_dieses_jahr_doy"),
    zone.get("_niederschlag_fruehjahr_bisher"),
    PER_YEAR_DATA,
)
if analog_years:
    st.subheader("🔮 Похожие по погоде годы")
    st.caption(
        "Как это работает: берутся данные ЭТОГО года с 1 марта по 7 мая "
        "(даты заморозков + сумма осадков) — от начала до конца этого периода. "
        "Затем среди всех лет 1996–2025 ищутся 3 года, у которых этот же "
        "период (1 марта – 7 мая) прошёл максимально похоже. Ниже — именно "
        "эти 3 года, у которых начало сезона выглядело так же, как в этом году."
    )
    narrative = build_analog_narrative(zone, analog_years)
    if narrative:
        st.write(narrative)

    with st.expander("📊 Показать погодные данные похожих лет"):
        st.write("**Сводные показатели по каждому похожему году** (эти же параметры учитываются в расчёте балла пригодности):")
        summary_rows = []
        for a in analog_years:
            herbstfrost_doy = a.get("herbstfrost_doy")
            herbstfrost_readable = _doy_to_readable(herbstfrost_doy) if herbstfrost_doy is not None and not pd.isna(herbstfrost_doy) else "нет данных"
            summary_rows.append({
                "Год": a["jahr"],
                "Заморозок весной (до 7 мая)": a["vorsaison_frost"],
                "Осадки до 7 мая": f"{a['vorsaison_niederschlag']} мм",
                "Ср. темп. сезона (май-сент.)": f"{a['saison_temperatur']} °C" if a.get("saison_temperatur") is not None else "—",
                "Осадки сезона (май-сент.)": f"{a['saison_niederschlag']} мм" if a.get("saison_niederschlag") is not None else "—",
                "Тепловая сумма GDD": a["saison_gdd"],
                "Жарких дней (>30°C)": a["saison_hitzetage"],
                "Засуха (дней подряд)": a["saison_trockenperiode"],
                "Первый осенний заморозок": herbstfrost_readable,
            })
        summary_df = pd.DataFrame(summary_rows)
        render_wrapped_table(summary_df, col_widths_pct=[7, 14, 11, 13, 13, 12, 12, 10, 8])

        st.write("**Погода по неделям в похожих годах** (март–октябрь):")

        # Positions-basierte Reihen (Woche 1, 2, 3... der Saison) für jedes
        # Analog-Jahr — Kalenderdaten variieren leicht zwischen Jahren,
        # daher NICHT nach echtem Datum ausrichten, sondern nach Position
        # innerhalb der Saison (vermeidet vermischte/verwirrende Datumsangaben).
        temp_series = {}
        precip_series = {}

        current_year_label = f"{date.today().year} (текущий)"
        if not DAILY_SPRING_DF.empty:
            current_daily_rows = DAILY_SPRING_DF[DAILY_SPRING_DF["zone_id"] == zone_id].to_dict("records")
            if current_daily_rows:
                current_weekly = weekly_series_from_daily(current_daily_rows)
                if current_weekly:
                    temp_series[current_year_label] = {p: v["temperatur_mittel_c"] for p, v in current_weekly.items()}
                    precip_series[current_year_label] = {p: v["niederschlag_mm"] for p, v in current_weekly.items()}

        analog_temp_series = {}
        analog_precip_series = {}
        for a in analog_years:
            jahr_str = str(a["jahr"])
            pos_series = weekly_series_by_position(zone_id, a["jahr"], WEEKLY_DATA)
            analog_temp_series[jahr_str] = {p: v["temperatur_mittel_c"] for p, v in pos_series.items()}
            analog_precip_series[jahr_str] = {p: v["niederschlag_mm"] for p, v in pos_series.items()}

        temp_series.update(analog_temp_series)
        precip_series.update(analog_precip_series)

        if temp_series:
            st.caption(
                f"**Температура по неделям, °C** (ось X — номер недели сезона; линии — "
                f"{current_year_label}, пока доступны только данные до начала мая, вместе с похожими годами):"
            )
            temp_chart_df = pd.DataFrame(temp_series).sort_index()
            temp_chart_df.index.name = "Неделя сезона"
            st.line_chart(temp_chart_df)

            st.caption("**Осадки по неделям, мм** (ось X — номер недели сезона):")
            precip_chart_df = pd.DataFrame(precip_series).sort_index()
            precip_chart_df.index.name = "Неделя сезона"
            st.bar_chart(precip_chart_df)

        if analog_temp_series:
            show_weekly_table = st.checkbox("Показать точную таблицу по неделям", key=f"weekly_table_{zone_id}")
            if show_weekly_table:
                row_keys = sorted({p for series in analog_temp_series.values() for p in series})
                row_display = {p: f"Неделя {p}" for p in row_keys}

                render_grouped_weekly_table(
                    row_label="Неделя",
                    row_keys=row_keys,
                    row_display=row_display,
                    metric_groups={
                        "Осадки (мм)": analog_precip_series,
                        "Температура (°C)": analog_temp_series,
                    },
                )
        else:
            st.caption("Понедельные данные для похожих лет не найдены.")
elif "_kurzfristig_zeitraum" in zone:
    st.info(
        "ℹ️ Похожих лет не найдено — недостаточно исторических данных для сравнения "
        "(нужен файл yearly_per_year_metrics.csv с данными по годам)."
    )

with st.expander("Климатические параметры выбранной зоны"):
    st.caption(
        f"Используемые ниже значения — это взвешенная смесь 10-летнего и "
        f"30-летнего периодов ({int(TREND_GEWICHT_10J*100)}% / {int((1-TREND_GEWICHT_10J)*100)}%), "
        f"чтобы учитывать актуальный климатический тренд, а не только "
        f"устаревшую многолетнюю норму."
    )
    st.write(f"- Вегетационное окно: **{zone['_vegetationsfenster_tage']} дней** "
             f"(с {zone['_letzter_fruehjahrsfrost']} по {zone['_erster_herbstfrost']})")
    st.write(f"- Осадки за сезон: **{zone['осадки_мм']} мм**")
    st.write(f"- Средняя температура: **{zone['температура_ср']} °C**")
    st.write(f"- Тепловая сумма (GDD, база 5°C): **{zone['_gdd']}**")
    st.write(f"- Длиннейшая засуха в среднем: **{zone['_trockenperiode']} дней подряд**")
    st.write(f"- Жарких дней (>30°C) в среднем: **{zone['_hitzetage']}**")
    if zone.get("_osadki_30j") is not None:
        st.write(
            f"- Исходные значения — 30-летняя норма: **{zone['_температура_30j']} °C**, "
            f"**{zone['_осадки_30j']} мм**, GDD **{zone['_gdd_30j']}**"
        )
    if "_osadki_10j" in zone and zone["_osadki_10j"] is not None:
        trend_temp = zone.get("_temp_trend_delta")
        trend_text = ""
        if trend_temp is not None:
            if trend_temp > 0:
                trend_text = f" (тренд: теплее на {trend_temp}°C за 10 лет)"
            elif trend_temp < 0:
                trend_text = f" (тренд: холоднее на {abs(trend_temp)}°C за 10 лет)"
            else:
                trend_text = " (без изменений)"
        st.write(
            f"- Исходные значения — 10-летний тренд: **{zone['_temperatura_10j']} °C**, "
            f"**{zone['_osadki_10j']} мм**, GDD **{zone['_gdd_10j']}**{trend_text}"
        )
    if "_kurzfristig_zeitraum" in zone:
        st.write(
            f"- Данные текущей весны ({zone['_kurzfristig_zeitraum']}, "
            f"{zone.get('_tage_ausgewertet', '?')} дней учтено):"
        )
        if zone.get("_frost_dieses_jahr") == "не наблюдался":
            st.write("  - Заморозков в отслеживаемый период не зафиксировано")
        elif zone.get("_frost_dieses_jahr"):
            st.write(f"  - Последний фактический заморозок: **{zone['_frost_dieses_jahr']}**")
            abweichung = zone.get("_frost_abweichung_tage")
            if abweichung is not None and abweichung > 0:
                st.write(f"    \u2192 на **{abweichung} дн. позже** 30-летней нормы")
            elif abweichung is not None and abweichung < 0:
                st.write(f"    \u2192 на **{abs(abweichung)} дн. раньше** 30-летней нормы")
            elif abweichung == 0:
                st.write("    \u2192 совпадает с 30-летней нормой")
        erwaermung = zone.get("_erwaermung_beginn_dieses_jahr")
        if erwaermung not in (None, "ещё не наступило"):
            st.write(f"  - Начало устойчивого потепления (\u22655°C, 5+ дней подряд): **{erwaermung}**")
        niederschlag_bisher = zone.get("_niederschlag_fruehjahr_bisher")
        if niederschlag_bisher is not None:
            st.write(f"  - Осадки с начала марта: **{niederschlag_bisher} мм**")
    st.caption(f"Источник данных: {zone.get('_datenquelle', 'неизвестно')}")

st.header("3. История севооборота на этом поле")
st.caption("Укажите, что сеялось в последние годы (оставьте «Не сеялось», если данных нет)")
history = {}
current_year = 2026
hist_cols = st.columns(4)
for i, offset in enumerate([4, 3, 2, 1]):
    year = current_year - offset
    with hist_cols[i]:
        crop_choice = st.selectbox(
            f"{year} год",
            ["Не сеялось"] + list(CROPS.keys()),
            key=f"hist_{year}",
        )
        if crop_choice != "Не сеялось":
            history[year] = crop_choice

st.header("4. Приоритеты при выборе культуры")
st.caption(
    "Здесь определяется, насколько важен каждый параметр для итогового расчёта. "
    "Например: 100% — учитывается только этот параметр, все остальные не влияют на результат. "
    "20% — этот параметр составляет 20% итоговой оценки, и так далее для каждого ползунка "
    "отдельно. Сумма всех ползунков должна быть ровно 100%."
)

with st.expander("ℹ️ Что означает каждый параметр"):
    param_definitions = pd.DataFrame([
        {
            "Параметр": "Тип почвы",
            "Определение": "Тип почвы — это классификация грунта по его происхождению, составу и свойствам (структура, содержание глины/песка, органических веществ). Разные типы по-разному удерживают воду, питательные вещества и воздух, что определяет, какие культуры на них хорошо растут. Полный список типов и их характеристик — см. таблицу «Сравнение всех типов почв» выше.",
        },
        {
            "Параметр": "pH почвы",
            "Определение": "pH почвы — это мера её кислотности или щёлочности по шкале от 0 до 14. Показатель 7 означает нейтральную среду, ниже 7 — кислую, а выше 7 — щёлочную. Этот уровень определяет, могут ли растения брать из земли нужные им полезные элементы — даже при достаточном количестве удобрений при неподходящем pH растение может их не получать.",
        },
        {
            "Параметр": "Вегетационное окно",
            "Определение": "Вегетационный период (окно) — это отрезок времени в году, когда температура достаточно тёплая для активного роста растений — от последнего весеннего заморозка до первого осеннего. Вне этого окна заморозки могут повредить или убить растения. В Омской области этот период заметно короче, чем в южных регионах, из-за резко-континентального сибирского климата — долгой зимы и позднего прихода тепла весной. В модели это окно вычисляется из реальных дат заморозков за 30 лет по выбранной зоне, а не задаётся вручную.",
        },
        {
            "Параметр": "Тепловая сумма (GDD)",
            "Определение": "Тепловая сумма, или сумма активных температур (Growing Degree Days) — показатель, отражающий количество «эффективного» тепла, накопленного за вегетационный период. Считается как сумма превышений среднесуточной температуры над порогом 5°C за каждый день сезона. Разным культурам требуется разное количество тепла, чтобы пройти полный цикл развития — от прорастания до полного созревания.",
        },
        {
            "Параметр": "Влагообеспеченность",
            "Определение": "Влагообеспеченность — это совокупная характеристика того, насколько растению хватает влаги в течение сезона: как по общему объёму осадков, так и по равномерности их выпадения. Даже при достаточной сумме осадков за сезон длительный засушливый период в критическую фазу роста (например, во время цветения) может серьёзно снизить урожай.",
        },
        {
            "Параметр": "Жаростойкость",
            "Определение": "Жаростойкость — способность растения переносить повышенные температуры (выше 30°C) без потери продуктивности. При сильной жаре у растений нарушается фотосинтез, ускоряется испарение влаги, а у некоторых культур повреждается пыльца во время цветения, что снижает завязываемость семян/плодов.",
        },
        {
            "Параметр": "Урожайность",
            "Определение": "Урожайность — это количество продукции (в центнерах с гектара, ц/га), которое культура обычно даёт при благоприятных условиях. Это справочный, «паспортный» показатель культуры — он не зависит от конкретного поля или зоны, а отражает её общий потенциал по сравнению с другими культурами.",
        },
        {
            "Параметр": "Влияние предшественника",
            "Определение": "Насколько удачно культура-кандидат сочетается с той культурой, что росла на этом поле в прошлом году, по азотному эффекту. Азотфиксирующие культуры (горох, чечевица) обогащают почву азотом — после них хорошо сеять азотоистощающие культуры (рапс, подсолнечник). Две истощающие культуры подряд, наоборот, обедняют почву без восстановления.",
        },
    ])
    render_wrapped_table(param_definitions, col_widths_pct=[18, 82])

    show_formulas = st.checkbox("🔬 Показать точные формулы (для тех, кому интересна математика)")
    if show_formulas:
        param_explanation = pd.DataFrame([
            {
                "Параметр": "Тип почвы",
                "Что измеряет": "Совпадает ли тип почвы поля с подходящими почвами культуры",
                "Формула": "1.0 при точном совпадении · 0.4 если почва типична для зоны, но не идеальна для культуры · 0.0 иначе",
                "Источник данных": "Выбор пользователя (шаг 1) + список подходящих почв культуры",
            },
            {
                "Параметр": "pH почвы",
                "Что измеряет": "Попадает ли pH поля в оптимальный диапазон культуры",
                "Формула": "Внутри диапазона: 1.0 · Вне диапазона: 1 − (отклонение в ед. pH) × 0.4  →  напр. 1 ед. вне = 0.6, 2.5 ед. вне = 0",
                "Источник данных": "Слайдер pH (шаг 1) + диапазон ph_мин/ph_макс культуры",
            },
            {
                "Параметр": "Вегетационное окно",
                "Что измеряет": "Хватает ли дней между последним весенним и первым осенним заморозком",
                "Формула": "Если хватает: min(1.0; 0.6 + излишек_дней × 0.012) — макс. балл уже при +33 днях излишка. "
                           "Если не хватает: max(0; 0.6 − дефицит_дней × 0.06) — обнуляется уже при дефиците в 10 дней",
                "Источник данных": "CSV (даты заморозков, 30л. норма) + мин_дни_роста культуры",
            },
            {
                "Параметр": "Тепловая сумма (GDD)",
                "Что измеряет": "Хватает ли зоне накопленного тепла (база 5°C) для вызревания",
                "Формула": "Если хватает: min(1.0; 0.6 + излишек_GDD × 0.0005) — макс. балл при +800 GDD излишка. "
                           "Если не хватает: max(0; 0.6 − дефицит_GDD × 0.001) — обнуляется при дефиците 600 GDD",
                "Источник данных": "CSV (тепловая сумма, 30л. норма) + необходимая_gdd культуры",
            },
            {
                "Параметр": "Влагообеспеченность",
                "Что измеряет": "Осадки И риск длинной засухи — среднее двух под-баллов",
                "Формула": "(а) Осадки: осадки_зоны × коэфф_дренажа (0.9/1.0/1.15), затем max(0; 1 − |разница с потребностью| / 225). "
                           "(б) Засуха: 1.0 если засуха_зоны ≤ допуск культуры, иначе max(0; 1 − превышение_дней × 0.1). "
                           "Итог = среднее (а) и (б)",
                "Источник данных": "CSV (осадки + засуха, 30л. норма), дренаж (шаг 1) + параметры культуры",
            },
            {
                "Параметр": "Жаростойкость",
                "Что измеряет": "Выдержит ли культура типичное число жарких дней (>30°C) в зоне",
                "Формула": "Порог по категории: низкая=3 дня, средняя=8, высокая=15. "
                           "В пределах порога: 1.0. Сверх порога: max(0; 1 − превышение_дней × 0.08)",
                "Источник данных": "CSV (жаркие дни, 30л. норма) + категория жаростойкости культуры",
            },
            {
                "Параметр": "Урожайность",
                "Что измеряет": "Потенциальная урожайность культуры относительно максимума в таблице",
                "Формула": "урожайность_культуры / максимальная_урожайность_среди_всех_культур — от условий поля/зоны НЕ зависит",
                "Источник данных": "Справочная таблица культур (фиксированные значения)",
            },
            {
                "Параметр": "Влияние предшественника",
                "Что измеряет": "Насколько удачно азотный эффект культуры-кандидата сочетается с азотным эффектом культуры, росшей на поле в прошлом году",
                "Формула": "Таблица сочетаний: связывающий→истощающий = 1.0 (идеально) · истощающий→истощающий = 0.3 (плохо) · "
                           "истощающий→связывающий = 1.0 (восстановление) · нет истории = 0.7 (нейтрально)",
                "Источник данных": "История посевов (шаг 3) + эффект_азот культуры-предшественника и культуры-кандидата",
            },
        ])
        render_wrapped_table(param_explanation, col_widths_pct=[14, 24, 42, 20])
        st.caption(
            "Итоговый балл каждого параметра лежит в диапазоне 0–1, затем умножается на вес "
            "(ползунок ниже) и суммируется. Все коэффициенты (0.012, 0.06, 0.0005 и т.д.) — "
            "экспертные оценки для прототипа, подлежат калибровке на реальных данных об урожаях."
        )

    st.info(
        "⚠️ **Важно**: балл (0–1) по каждому параметру вычисляется автоматически ОТДЕЛЬНО "
        "для каждой культуры — вы его не выбираете напрямую. Например, ваш pH почвы один "
        "и тот же для всех культур, но диапазон pH_мин/pH_макс у каждой культуры свой — "
        "поэтому один и тот же pH может дать балл 1.0 для одной культуры и 0.6 для другой. "
        "Ползунки ниже задают только вес (важность) каждого параметра в итоговой сумме, "
        "а не саму оценку."
    )

    show_deviation_table = st.checkbox("📐 Показать таблицу «отклонение → балл»")
    if show_deviation_table:
        deviation_rows = [
            {"Параметр": "Тип почвы", "Ситуация": "Точное совпадение", "Балл": "1.0"},
            {"Параметр": "Тип почвы", "Ситуация": "Типична для зоны, но не идеальна", "Балл": "0.4"},
            {"Параметр": "Тип почвы", "Ситуация": "Не подходит совсем", "Балл": "0.0"},
            {"Параметр": "pH почвы", "Ситуация": "В пределах диапазона культуры", "Балл": "1.0"},
            {"Параметр": "pH почвы", "Ситуация": "0.5 ед. за пределами диапазона", "Балл": "0.8"},
            {"Параметр": "pH почвы", "Ситуация": "1.0 ед. за пределами диапазона", "Балл": "0.6"},
            {"Параметр": "pH почвы", "Ситуация": "1.5 ед. за пределами диапазона", "Балл": "0.4"},
            {"Параметр": "pH почвы", "Ситуация": "2.0 ед. за пределами диапазона", "Балл": "0.2"},
            {"Параметр": "pH почвы", "Ситуация": "2.5 ед. и более за пределами", "Балл": "0.0"},
            {"Параметр": "Вегетационное окно", "Ситуация": "Запас 33+ дней сверх минимума культуры", "Балл": "1.0"},
            {"Параметр": "Вегетационное окно", "Ситуация": "Запас 20 дней", "Балл": "0.84"},
            {"Параметр": "Вегетационное окно", "Ситуация": "Запас 10 дней", "Балл": "0.72"},
            {"Параметр": "Вегетационное окно", "Ситуация": "Ровно впритык (0 запаса)", "Балл": "0.6"},
            {"Параметр": "Вегетационное окно", "Ситуация": "Не хватает 2 дней", "Балл": "0.48"},
            {"Параметр": "Вегетационное окно", "Ситуация": "Не хватает 5 дней", "Балл": "0.3"},
            {"Параметр": "Вегетационное окно", "Ситуация": "Не хватает 10 дней и более", "Балл": "0.0"},
            {"Параметр": "Тепловая сумма (GDD)", "Ситуация": "Излишек 800+ GDD", "Балл": "1.0"},
            {"Параметр": "Тепловая сумма (GDD)", "Ситуация": "Излишек 400 GDD", "Балл": "0.8"},
            {"Параметр": "Тепловая сумма (GDD)", "Ситуация": "Ровно впритык (0 излишка)", "Балл": "0.6"},
            {"Параметр": "Тепловая сумма (GDD)", "Ситуация": "Дефицит 300 GDD", "Балл": "0.3"},
            {"Параметр": "Тепловая сумма (GDD)", "Ситуация": "Дефицит 600 GDD и более", "Балл": "0.0"},
            {"Параметр": "Влагообеспеченность (осадки)", "Ситуация": "Осадки точно совпадают с потребностью", "Балл": "1.0"},
            {"Параметр": "Влагообеспеченность (осадки)", "Ситуация": "Разница 112 мм", "Балл": "0.5"},
            {"Параметр": "Влагообеспеченность (осадки)", "Ситуация": "Разница 225 мм и более", "Балл": "0.0"},
            {"Параметр": "Влагообеспеченность (засуха)", "Ситуация": "Засуха зоны в пределах допуска культуры", "Балл": "1.0"},
            {"Параметр": "Влагообеспеченность (засуха)", "Ситуация": "Превышение допуска на 4 дня", "Балл": "0.6"},
            {"Параметр": "Влагообеспеченность (засуха)", "Ситуация": "Превышение допуска на 10 дней и более", "Балл": "0.0"},
            {"Параметр": "Жаростойкость", "Ситуация": "Жаркие дни зоны в пределах порога культуры", "Балл": "1.0"},
            {"Параметр": "Жаростойкость", "Ситуация": "Превышение порога на 6 дней", "Балл": "0.52"},
            {"Параметр": "Жаростойкость", "Ситуация": "Превышение порога на 12.5 дней и более", "Балл": "0.0"},
        ]
        render_wrapped_table(pd.DataFrame(deviation_rows), col_widths_pct=[24, 46, 30])

WEIGHT_KEYS = {
    "почва": "w_soil", "ph": "w_ph", "окно": "w_window", "gdd": "w_gdd",
    "вода": "w_water", "жара": "w_heat", "урожайность": "w_yield",
    "предшественник": "w_predecessor",
}


def _normalize_weights_to_100(weights):
    """Skaliert Gewichte proportional so, dass sie exakt 100 ergeben (Largest-Remainder-Methode)."""
    total = sum(weights.values())
    keys = list(weights.keys())
    if total == 0:
        base, rest = divmod(100, len(keys))
        return {k: base + (1 if i < rest else 0) for i, k in enumerate(keys)}
    raw = {k: v / total * 100 for k, v in weights.items()}
    floored = {k: int(raw[k]) for k in keys}
    remainder = 100 - sum(floored.values())
    order = sorted(keys, key=lambda k: raw[k] - floored[k], reverse=True)
    result = dict(floored)
    for k in order[:remainder]:
        result[k] += 1
    return result


weight_row1 = st.columns(4)
with weight_row1[0]:
    w_soil = st.slider("Тип почвы", 0, 100, DEFAULT_WEIGHTS["почва"], key="w_soil", help="Насколько важно точное совпадение почвы")
with weight_row1[1]:
    w_ph = st.slider("pH почвы", 0, 100, DEFAULT_WEIGHTS["ph"], key="w_ph", help="Насколько важен диапазон pH культуры")
with weight_row1[2]:
    w_window = st.slider("Вегетационное окно", 0, 100, DEFAULT_WEIGHTS["окно"], key="w_window", help="Насколько важен запас дней между заморозками")
with weight_row1[3]:
    w_gdd = st.slider("Тепловая сумма (GDD)", 0, 100, DEFAULT_WEIGHTS["gdd"], key="w_gdd", help="Насколько важно, чтобы зоне хватало тепла для вызревания")

weight_row2 = st.columns(4)
with weight_row2[0]:
    w_water = st.slider("Влагообеспеченность", 0, 100, DEFAULT_WEIGHTS["вода"], key="w_water", help="Осадки + риск длинной засухи")
with weight_row2[1]:
    w_heat = st.slider("Жаростойкость", 0, 100, DEFAULT_WEIGHTS["жара"], key="w_heat", help="Насколько важна устойчивость к жарким дням")
with weight_row2[2]:
    w_yield = st.slider("Урожайность", 0, 100, DEFAULT_WEIGHTS["урожайность"], key="w_yield", help="Насколько важен потенциальный урожай (ц/га)")
with weight_row2[3]:
    w_predecessor = st.slider("Влияние предшественника", 0, 100, DEFAULT_WEIGHTS["предшественник"], key="w_predecessor", help="Насколько важно, какая культура росла на поле в прошлом году (азотный эффект)")

user_weights = {
    "почва": w_soil,
    "ph": w_ph,
    "окно": w_window,
    "gdd": w_gdd,
    "вода": w_water,
    "жара": w_heat,
    "урожайность": w_yield,
    "предшественник": w_predecessor,
}

total_w = sum(user_weights.values())
weights_valid = (total_w == 100)

if weights_valid:
    st.success(
        "Сумма приоритетов: 100% ✅ — "
        + " · ".join(f"{k}: {v}%" for k, v in user_weights.items())
    )
else:
    st.error(f"Сумма приоритетов должна быть ровно 100%. Сейчас: {total_w}%.")
    if st.button("⚖️ Нормализовать до 100%"):
        normalized = _normalize_weights_to_100(user_weights)
        for weight_key, session_key in WEIGHT_KEYS.items():
            st.session_state[session_key] = normalized[weight_key]
        st.rerun()

st.header("5. Калибровка по фактическим данным (опционально)")
st.caption(
    "Модель использует справочную урожайность из общей агрономической литературы — "
    "она НЕ откалибрована под конкретно ваши поля. Здесь можно было бы вносить "
    "реальные наблюдения за прошлые годы (что сеяли, когда взошло/убрали, какая "
    "была урожайность), и модель начала бы использовать средний ФАКТИЧЕСКИЙ урожай "
    "вместо справочного значения."
)
st.caption("🔒 Раздел пока отключён (в разработке) — ввод данных недоступен.")

calibration_df = load_calibration_data()

with st.form("calibration_form", clear_on_submit=True):
    cal_cols = st.columns(4)
    with cal_cols[0]:
        cal_zone_id = st.selectbox(
            "Зона", list(ZONES.keys()), format_func=lambda zid: ZONES[zid]["name_ru"], key="cal_zone", disabled=True
        )
    with cal_cols[1]:
        cal_crop = st.selectbox("Культура", list(CROPS.keys()), key="cal_crop", disabled=True)
    with cal_cols[2]:
        cal_year = st.number_input("Год", min_value=1990, max_value=2100, value=date.today().year - 1, step=1, key="cal_year", disabled=True)
    with cal_cols[3]:
        cal_yield = st.number_input("Факт. урожайность (ц/га)", min_value=0.0, max_value=200.0, value=20.0, step=0.5, key="cal_yield", disabled=True)

    cal_cols2 = st.columns(3)
    with cal_cols2[0]:
        cal_sowing = st.text_input("Факт. дата посева (напр. 12 мая)", key="cal_sowing", disabled=True)
    with cal_cols2[1]:
        cal_harvest = st.text_input("Факт. дата уборки (напр. 20 августа)", key="cal_harvest", disabled=True)
    with cal_cols2[2]:
        cal_notes = st.text_input("Заметки (необязательно)", key="cal_notes", disabled=True)

    submitted = st.form_submit_button("💾 Сохранить наблюдение", disabled=True)
    if submitted:
        save_calibration_entry({
            "zone_id": cal_zone_id,
            "zone_name": ZONES[cal_zone_id]["name_ru"],
            "crop_name": cal_crop,
            "jahr": int(cal_year),
            "факт_дата_посева": cal_sowing,
            "факт_дата_уборки": cal_harvest,
            "факт_урожайность_ц_га": cal_yield,
            "заметки": cal_notes,
            "добавлено": date.today().isoformat(),
        })
        st.success(f"Сохранено: {cal_crop}, {ZONES[cal_zone_id]['name_ru']}, {cal_year} год.")
        st.rerun()

if not calibration_df.empty:
    with st.expander(f"📋 Внесённые наблюдения ({len(calibration_df)})"):
        st.dataframe(calibration_df, use_container_width=True, hide_index=True)

    active_overrides = []
    for (zid, cname), _ in calibration_df.groupby(["zone_id", "crop_name"]):
        cal_val, n_obs = get_calibrated_yield(zid, cname, calibration_df)
        if cal_val is not None:
            справочная = CROPS.get(cname, {}).get("урожайность_ц_га")
            active_overrides.append({
                "Зона": ZONES.get(zid, {}).get("name_ru", zid),
                "Культура": cname,
                "Справочная урожайность": справочная,
                "Калиброванная (факт.)": cal_val,
                "Набл.": n_obs,
            })
    if active_overrides:
        st.write("**Активные калибровки** (используются вместо справочных значений при моделировании):")
        render_wrapped_table(pd.DataFrame(active_overrides), col_widths_pct=[22, 22, 20, 20, 16])

st.divider()

if st.button("🚀 Начать моделирование", type="primary", disabled=(not weights_valid)):
    results = []
    sub_scores_by_crop = {}
    predecessor_effect = get_predecessor_effect(history)
    for crop_name, crop in CROPS.items():
        cal_yield, n_obs = get_calibrated_yield(zone_id, crop_name, calibration_df)
        if cal_yield is not None:
            effective_crop = dict(crop)
            effective_crop["урожайность_ц_га"] = cal_yield
            urozhay_display = f"{cal_yield} (факт., {n_obs} набл.)"
        else:
            effective_crop = crop
            urozhay_display = f"{crop['урожайность_ц_га']} (справочно)"

        s, sub_scores = score_crop(
            crop_name, effective_crop, zone, soil_type, ph, drainage, user_weights,
            return_details=True, predecessor_effect=predecessor_effect,
        )
        sub_scores_by_crop[crop_name] = sub_scores
        harvest = estimate_harvest_window(crop_name, zone)
        harvest_display = harvest["дата"] + (f" {harvest['риск_текст']}" if harvest["риск"] else "")
        results.append({
            "Культура": crop_name,
            "Балл пригодности": s,
            "Ориентировочный посев": estimate_sowing_date(crop_name, zone),
            "Ориентировочная уборка": harvest_display,
            "Урожайность (ц/га)": urozhay_display,
            "Треб. GDD": crop["необходимая_gdd"],
            "Мин. дней роста": crop["мин_дни_роста"],
            "Жаростойкость": crop["жаростойкость"],
            "Эффект на азот": crop["эффект_азот"],
        })

    ranked_df = pd.DataFrame(results).sort_values("Балл пригодности", ascending=False).reset_index(drop=True)
    ranked_df = apply_rotation_filter(ranked_df, history)

    st.header("Результат моделирования")

    allowed_df = ranked_df[ranked_df["Разрешено севооборотом"] == "Да"].head(10)
    blocked_df = ranked_df[ranked_df["Разрешено севооборотом"] == "Нет"]

    st.subheader("✅ Рекомендованные культуры (с учётом севооборота)")
    result_col_widths = [12, 9, 12, 18, 12, 8, 9, 9, 11]  # Summe = 100, "Уборка" breiter wegen Risikohinweis
    render_wrapped_table(allowed_df.drop(columns=["Разрешено севооборотом", "Причина_блокировки"]), col_widths_pct=result_col_widths)

    if not blocked_df.empty:
        with st.expander("⛔ Культуры, исключённые из-за севооборота"):
            blocked_display_df = build_blocked_table(blocked_df, history)
            render_wrapped_table(blocked_display_df, col_widths_pct=[16, 24, 22, 16, 22])

    st.subheader("📝 Почему именно эти культуры")
    if not allowed_df.empty:
        best_crop_name = allowed_df.iloc[0]["Культура"]
        st.write(explain_best_crop(best_crop_name, sub_scores_by_crop[best_crop_name], user_weights))
        st.write(explain_predecessor_relationship(best_crop_name, CROPS[best_crop_name]["эффект_азот"], history))

        if len(allowed_df) > 1:
            second_crop_name = allowed_df.iloc[1]["Культура"]
            st.write(
                compare_two_crops(
                    best_crop_name, sub_scores_by_crop[best_crop_name],
                    second_crop_name, sub_scores_by_crop[second_crop_name],
                    user_weights,
                )
            )

            weakest_crop_name = allowed_df.iloc[-1]["Культура"]
            st.write(explain_weak_crop(weakest_crop_name, sub_scores_by_crop[weakest_crop_name], user_weights))
            st.write(explain_predecessor_relationship(weakest_crop_name, CROPS[weakest_crop_name]["эффект_азот"], history))

    if not blocked_df.empty:
        for _, row in blocked_df.iterrows():
            crop_name_blocked = row["Культура"]
            reason = row.get("Причина_блокировки", "")
            st.write(explain_rotation_exclusion(crop_name_blocked, CROPS[crop_name_blocked], history, reason=reason))

    st.caption(
        "Балл пригодности рассчитан на основе соответствия почвы, pH, вегетационного окна "
        "(по реальным датам заморозков), тепловой суммы (GDD), водообеспеченности с учётом "
        "риска засухи, жаростойкости и урожайного потенциала. Это прототип — веса и "
        "справочные значения культур подлежат уточнению. Данные по погоде похожих лет — "
        "см. раздел «🔮 Похожие по погоде годы» выше."
    )

    drainage_hinweise = {
        "Хороший дренаж": "поле обычно готово к технике уже через 1-3 дня после дождя — "
                           "риск задержки уборки из-за переувлажнения почвы минимален.",
        "Средний дренаж": "после сильных дождей в августе-сентябре дайте полю 1-2 дня на подсыхание "
                           "перед заездом техники — типично для большинства чернозёмов.",
        "Застойное (сырое)": "⚠️ при выбранном дренаже вода может застаиваться на несколько дней — "
                              "закладывайте ЗАПАС в несколько дней сверх расчётной даты уборки, "
                              "особенно если август-сентябрь окажутся дождливыми.",
    }
    st.caption(
        f"**О готовности поля к технике**: {drainage_hinweise.get(drainage, '')} "
        "Это общая оценка по типу дренажа — отдельного прогноза погоды на август-сентябрь "
        "модель пока не строит (данные охватывают только период до начала мая)."
    )