"""
Zentrale Definition der Omsk-Zonen mit Koordinaten (Zentroid je 100-km-Band).
Wird von beiden Fetch-Skripten (kurzfristig & langfristig) importiert,
damit es nur EINE Quelle der Wahrheit für Zonen-Koordinaten gibt.
"""

ZONES = {
    "north_taiga": {
        "name_ru": "Север (тайга)",
        "lat": 57.5,
        "lon": 73.5,
    },
    "north_foreststeppe": {
        "name_ru": "Северная лесостепь",
        "lat": 56.0,
        "lon": 73.5,
    },
    "south_foreststeppe": {
        "name_ru": "Южная лесостепь",
        "lat": 55.0,
        "lon": 73.3,
    },
    "steppe": {
        "name_ru": "Степь",
        "lat": 54.0,
        "lon": 73.0,
    },
}