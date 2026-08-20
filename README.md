# omsk-crop-planner
find the best crop for area Omsl

Modell zur Auswahl optimaler Kulturen je Zone/Feld im Gebiet Omsk – unter
Berücksichtigung von Boden, Klimazone, kurz- und langfristigem Wetter sowie
Fruchtfolge-Historie.

## Projektstruktur

```
omsk-crop-planner/
├── .github/workflows/
│   ├── weekly_weather.yml     # Cron: jeden Montag – kurzfristige Wetterdaten
│   └── yearly_weather.yml     # Cron: jeden 1. Januar – 10-Jahres-Klimatrend
├── data/
│   ├── short_term/
│   │   └── weekly_weather.csv         (wird automatisch erzeugt/erweitert)
│   └── long_term/
│       └── yearly_climate_trend.csv   (wird automatisch erzeugt/erweitert)
├── scripts/
│   ├── zones.py               # zentrale Zonen-/Koordinaten-Definition
│   ├── fetch_utils.py         # Retry-/Backoff-Logik für API-Calls
│   ├── fetch_short_term.py    # wöchentlicher Fetch
│   └── fetch_long_term.py     # jährlicher Fetch
├── app.py                     # Streamlit-Prototyp (Kultur-Empfehlung)
├── requirements.txt
└── README.md
```

## Automatisierung

Beide Workflows laufen über GitHub Actions (kostenlos, kein eigener Server
nötig) und committen die neuen Daten automatisch zurück ins Repo:

- **Wöchentlich** (`weekly_weather.yml`): holt die Wetterdaten der letzten 7
  Tage je Zone → `data/short_term/weekly_weather.csv`
- **Jährlich** (`yearly_weather.yml`, jeden 1. Januar): holt den
  10-Jahres-Klimatrend je Zone → `data/long_term/yearly_climate_trend.csv`

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
      verfeinern (aktuell Platzhalter in `app.py`)
- [ ] `app.py` so anpassen, dass es die CSV-Daten aus `data/` einliest statt
      nur statischer Zonenwerte
- [ ] Mehrere Flächen gleichzeitig verarbeiten (CSV-Upload statt manueller
      Einzeleingabe)