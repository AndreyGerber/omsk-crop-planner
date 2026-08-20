"""
Gemeinsame Hilfsfunktionen für die Wetter-Skripte.
Enthält Retry-mit-Backoff, um bei kurzzeitigen API-Fehlern nicht sofort
abzubrechen, und einen Mindestabstand zwischen Requests (Höflichkeits-Limit,
auch wenn Open-Meteo bei dieser Frequenz nie an echte Rate-Limits stößt).
"""

import time
import requests


def fetch_with_retry(url, params, max_retries=3, backoff_seconds=5, request_gap_seconds=1.5, timeout=20):
    """
    Führt einen GET-Request mit Retry-Logik aus.
    - max_retries: Anzahl Versuche bei Fehler
    - backoff_seconds: Basis-Wartezeit, verdoppelt sich pro Versuch (exponentiell)
    - request_gap_seconds: Pause NACH einem erfolgreichen Call, bevor der nächste
      Zonen-Request gestartet wird (Selbstbeschränkung der Anfragen)
    - timeout: maximale Wartezeit auf die API-Antwort in Sekunden. Größere
      Zeiträume (z.B. 30 Jahre Tagesdaten) brauchen mehr als den Standardwert.
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            time.sleep(request_gap_seconds)
            return response.json()
        except requests.RequestException as e:
            last_error = e
            wait = backoff_seconds * (2 ** (attempt - 1))
            print(f"[Versuch {attempt}/{max_retries}] Fehler: {e} -> warte {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Alle {max_retries} Versuche fehlgeschlagen. Letzter Fehler: {last_error}")