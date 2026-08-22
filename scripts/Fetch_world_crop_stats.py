"""
Jährlicher Abruf weltweiter und russischer Anbau-/Ertragsstatistik (FAOSTAT),
je Kultur — reine HISTORIE, keine Preis- oder Marktprognose.

WARUM NUR HISTORIE: Preisentwicklung hängt von Angebot, Nachfrage, Politik,
Wechselkursen ab — dort ist jede Vorhersage im Kern Zufall. Was sich aber
sauber und faktenbasiert auswerten lässt: wie viel von einer Kultur in den
letzten Jahren weltweit UND in Russland angebaut/geerntet wurde, und ob die
Tendenz steigend oder fallend ist.

WICHTIGER HINWEIS ZUR DATENAKTUALITÄT: FAOSTAT veröffentlicht neue Zahlen
erst 1-2 Jahre nach der jeweiligen Saison (Stand Ende 2025 z.B. nur Daten bis
2024). Das "neueste verfügbare Jahr" ist NIE das laufende Jahr — das Skript
markiert das neueste Jahr explizit, statt so zu tun, als wäre es aktuell.

KEINE GERATENEN ZAHLENCODES: FAOSTAT-Codes für Länder/Kulturen/Kennzahlen
werden zur Laufzeit über die offizielle Code-Liste NACH NAMEN aufgelöst
(nicht hartkodiert) — ein falscher geratener Code würde sonst stillschweigend
leere Daten liefern, ohne dass man es bemerkt.

Quelle: FAOSTAT API (kostenlos, kein Key nötig).
https://www.fao.org/faostat/en/#data/QCL
"""

import os
import csv
import re
import time
from datetime import date

from fetch_utils import fetch_with_retry

BASE_URL = "https://faostatservices.fao.org/api/v1"
DOMAIN = "QCL"  # "Crops and livestock products"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "economics")

YEARS_BACK = 15  # wie viele Jahre Historie angefragt werden (FAOSTAT liefert nur, was tatsächlich existiert)

# Unsere Kultur-Namen -> Suchbegriff für den FAOSTAT-Item-Namen (englisch).
# FAOSTAT-Itemnamen ändern sich gelegentlich leicht zwischen Revisionen,
# daher wird per Teilstring-Suche (nicht exakter Gleichheit) gesucht.
CROP_SEARCH_TERMS = {
    "Яровая пшеница": "Wheat",
    "Ячмень": "Barley",
    "Овёс": "Oats",
    "Горох": "Peas, dry",
    "Чечевица": "Lentils",
    "Лён масличный": "Linseed",
    "Рапс яровой": "Rape or colza seed",
    "Подсолнечник": "Sunflower seed",
    "Гречиха": "Buckwheat",
    "Озимая рожь": "Rye",
}

AREA_SEARCH_TERMS = {
    "world": "World",
    "russia": "Russian Federation",
}

ELEMENT_SEARCH_TERMS = {
    "area_harvested_ha": "Area harvested",
    "production_t": "Production",
}


def _fetch_code_list(dimension):
    """Holt die vollständige Code-Liste (Code + Name) für eine Dimension (area/item/element)."""
    url = f"{BASE_URL}/en/codes/{dimension}/{DOMAIN}"
    data = fetch_with_retry(url, params={}, timeout=30)
    # Antwortstruktur: {"data": [{"code": "...", "label": "..."}, ...]} — Feldnamen
    # koennen je nach API-Version leicht variieren, daher tolerant auslesen.
    entries = data.get("data", [])
    result = []
    for e in entries:
        code = e.get("code") or e.get("Code") or e.get("id")
        label = e.get("label") or e.get("Label") or e.get("name") or e.get("Name") or ""
        if code is not None:
            result.append({"code": str(code), "label": str(label)})
    return result


def _resolve_by_name(code_list, search_term, exact=False):
    """
    Findet den/die Code(s), deren Label search_term als GANZES WORT enthaelt
    (nicht als reine Teilzeichenkette -- sonst wuerde z.B. "Wheat" faelschlich
    auch "Buckwheat" treffen). Gibt (code, label) des ERSTEN Treffers zurueck,
    oder (None, None) falls keiner. Loggt eine Warnung bei 0 oder >1 Treffern,
    damit stille Fehlzuordnungen auffallen.
    """
    term_lower = search_term.lower()
    if exact:
        matches = [e for e in code_list if e["label"].lower() == term_lower]
    else:
        pattern = re.compile(r"\b" + re.escape(term_lower) + r"\b")
        matches = [e for e in code_list if pattern.search(e["label"].lower())]

    if not matches:
        print(f"  ⚠️  Kein Treffer fuer '{search_term}' -- wird uebersprungen.")
        return None, None
    if len(matches) > 1:
        print(f"  ⚠️  {len(matches)} Treffer fuer '{search_term}': "
              f"{[m['label'] for m in matches]} -- nehme den ersten ('{matches[0]['label']}').")
    return matches[0]["code"], matches[0]["label"]


def _fetch_data(item_code, area_code, element_code, start_year, end_year):
    """Holt die eigentlichen Zeitreihendaten für eine Item/Area/Element-Kombination."""
    url = f"{BASE_URL}/en/data/{DOMAIN}"
    params = {
        "area": area_code,
        "item": item_code,
        "element": element_code,
        "year": ",".join(str(y) for y in range(start_year, end_year + 1)),
        "show_codes": "false",
        "show_unit": "true",
        "show_flags": "false",
        "null_values": "false",
    }
    data = fetch_with_retry(url, params=params, timeout=30)
    return data.get("data", [])


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR, "world_crop_stats.csv")

    end_year = date.today().year - 1  # FAOSTAT hat aktuelle Jahre ohnehin nie
    start_year = end_year - YEARS_BACK + 1

    print("Löse Area-Codes auf...")
    area_codes_list = _fetch_code_list("area")
    resolved_areas = {}
    for key, term in AREA_SEARCH_TERMS.items():
        code, label = _resolve_by_name(area_codes_list, term, exact=True)
        if code:
            resolved_areas[key] = {"code": code, "label": label}
            print(f"  {key}: '{label}' (Code {code})")

    print("Löse Element-Codes auf...")
    element_codes_list = _fetch_code_list("element")
    resolved_elements = {}
    for key, term in ELEMENT_SEARCH_TERMS.items():
        code, label = _resolve_by_name(element_codes_list, term, exact=True)
        if code:
            resolved_elements[key] = {"code": code, "label": label}
            print(f"  {key}: '{label}' (Code {code})")

    print("Löse Item-Codes auf...")
    item_codes_list = _fetch_code_list("item")
    resolved_items = {}
    for crop_name, term in CROP_SEARCH_TERMS.items():
        code, label = _resolve_by_name(item_codes_list, term, exact=False)
        if code:
            resolved_items[crop_name] = {"code": code, "label": label}
            print(f"  {crop_name} -> '{label}' (Code {code})")

    if not resolved_areas or not resolved_elements or not resolved_items:
        print("Nicht genug Codes aufgelöst — breche ab, ohne Daten zu holen.")
        return

    rows = []
    total_calls = len(resolved_items) * len(resolved_areas) * len(resolved_elements)
    call_i = 0
    for crop_name, item_info in resolved_items.items():
        for area_key, area_info in resolved_areas.items():
            for element_key, element_info in resolved_elements.items():
                call_i += 1
                print(f"[{call_i}/{total_calls}] {crop_name} / {area_key} / {element_key}")
                try:
                    records = _fetch_data(
                        item_info["code"], area_info["code"], element_info["code"],
                        start_year, end_year,
                    )
                except RuntimeError as e:
                    print(f"  ⚠️  Fehler, überspringe: {e}")
                    continue

                for r in records:
                    year = r.get("Year") or r.get("year")
                    value = r.get("Value") or r.get("value")
                    unit = r.get("Unit") or r.get("unit") or ""
                    if year is None or value is None:
                        continue
                    rows.append({
                        "crop_name_ru": crop_name,
                        "faostat_item": item_info["label"],
                        "area_scope": area_key,
                        "element": element_key,
                        "year": int(year),
                        "value": float(value),
                        "unit": unit,
                        "abfrage_datum": date.today().isoformat(),
                    })
                time.sleep(0.6)  # Selbstbeschränkung, ~2 Anfragen/Sekunde laut FAOSTAT-Richtwert

    if not rows:
        print("Keine Daten erhalten — Datei wird nicht geschrieben.")
        return

    # Datei wird komplett NEU geschrieben (nicht angehängt) — das Datenvolumen
    # ist klein (~10 Kulturen x 2 Regionen x 2 Kennzahlen x ~15 Jahre), und so
    # werden auch nachträgliche FAOSTAT-Revisionen älterer Jahre korrekt erfasst.
    fieldnames = ["crop_name_ru", "faostat_item", "area_scope", "element", "year", "value", "unit", "abfrage_datum"]
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} Zeilen nach {out_file} geschrieben (Jahre {start_year}-{end_year}).")


if __name__ == "__main__":
    main()