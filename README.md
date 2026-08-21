# omsk-crop-planner

Modell zur Auswahl optimaler Kulturen je Zone/Feld im Gebiet Omsk – unter
Berücksichtigung von Boden, Klimazone, kurz- und langfristigem Wetter sowie
Fruchtfolge-Historie.

## Projektstruktur

```
omsk-crop-planner/
├── .github/workflows/
│   ├── spring_preseason_weather.yml   # Cron: jeden Montag – Frühjahrs-Vorsaisondaten
│   └── yearly_weather.yml             # Cron: jeden 1. Januar – agronomische Klimakennzahlen
├── data/
│   ├── short_term/
│   │   ├── daily_spring_weather.csv   # Tagesgenaue Werte, 1. März – 7. Mai (wird automatisch erzeugt)
│   │   └── weekly_weather.csv         # Daraus abgeleitete Indikatoren (Frost/Erwärmung/Regen)
│   └── long_term/
│       └── yearly_climate_trend.csv   # 10j/30j-Kennzahlen: GDD, Frostfenster, Trockenheit, Hitze
├── scripts/
│   ├── zones.py               # zentrale Zonen-/Koordinaten-Definition
│   ├── fetch_utils.py         # Retry-/Backoff-Logik für API-Calls
│   ├── fetch_short_term.py    # Frühjahrs-Vorsaison-Fetch (tagesgenau)
│   └── fetch_long_term.py     # jährlicher Fetch (agronomische Klimakennzahlen)
├── app.py                     # Streamlit-Prototyp (Kultur-Empfehlung)
├── requirements.txt
└── README.md
```

## Automatisierung

Beide Workflows laufen über GitHub Actions (kostenlos, kein eigener Server
nötig) und committen die neuen Daten automatisch zurück ins Repo:

- **`spring_preseason_weather.yml`** (jeden Montag): holt tagesgenaue
  Wetterdaten für das Fenster 1. März – 7. Mai des laufenden Jahres. Vor
  Fensterende wächst das Fenster wöchentlich mit; danach überspringt das
  Skript den Abruf automatisch bis zum 1. März des Folgejahres (keine
  unnötigen API-Calls). Aus den Tagesdaten werden Indikatoren wie "letzter
  beobachteter Frost" und "Beginn stabiler Erwärmung" abgeleitet — bewusst
  KEIN simpler Temperaturmittelwert über die ganze (klimatisch sehr
  heterogene) Periode, da der die wichtige zeitliche Struktur verschlucken
  würde.
- **`yearly_weather.yml`** (jeden 1. Januar): holt agronomische
  Klimakennzahlen je Zone — Wärmesumme (GDD), Frühjahrs-/Herbstfrostfenster,
  längste Trockenperiode, Hitzetage — jeweils für ein 10-Jahres- und ein
  30-Jahres-Fenster. Überspringt Zonen, die für das aktuelle Jahr bereits
  erfasst sind (kein Duplikat bei mehrfachem manuellem Start).

Beide lassen sich zusätzlich manuell über den "Run workflow"-Button im
Actions-Tab von GitHub auslösen (`workflow_dispatch`).

Datenquelle: [Open-Meteo Archive API](https://open-meteo.com/en/docs/historical-weather-api)
– kostenlos, kein API-Key nötig.

## Lokales Setup

```bash
pip install -r requirements.txt

# Streamlit-App starten
streamlit run app.py

# Wetter-Fetch manuell testen
cd scripts
python fetch_short_term.py
python fetch_long_term.py
```

## Nächste Schritte

- [ ] Zonen-Koordinaten und Kultur-Referenztabelle mit echten Agrardaten
      verfeinern (aktuell Richtwerte in `app.py`)
- [ ] `app.py` auf das neue Schema von `weekly_weather.csv` umstellen
      (Frost-/Erwärmungsindikatoren statt altem Temperaturmittel-Schema)
- [ ] Mehrere Flächen gleichzeitig verarbeiten (CSV-Upload statt manueller
      Einzeleingabe)
- [ ] `daily_spring_weather.csv` in der App visualisieren (z.B. Temperatur-
      verlauf über die Vorsaison als Diagramm)