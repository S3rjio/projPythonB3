from typing import Any, Dict, List
import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def search_cities(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """Recherche de villes via l'API de géocodage Open-Meteo.
    Lève requests.exceptions.RequestException en cas d'erreur réseau."""
    query = query.strip()
    if len(query) < 2:
        return []

    res = requests.get(
        GEOCODING_URL,
        params={"name": query, "count": count, "language": "fr", "format": "json"},
        timeout=5,
    )
    res.raise_for_status()
    return res.json().get("results", [])