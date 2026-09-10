import os
import requests
from typing import Optional, Tuple

# Obtener la clave de API desde las variables de entorno
GOOGLE_API_KEY = os.getenv("GOOGLE_GEOCODING_API_KEY")
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Convierte una dirección en coordenadas (lat, lng) usando Google Geocoding API.
    Retorna None si falla.
    """
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_GEOCODING_API_KEY no está configurada en el entorno.")
    
    if not address:
        return None
    
    params = {
        "address": address,
        "key": GOOGLE_API_KEY
    }
    
    try:
        response = requests.get(GEOCODE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data["status"] == "OK" and len(data["results"]) > 0:
            location = data["results"][0]["geometry"]["location"]
            return location["lat"], location["lng"]
        else:
            # Log del error si quieres
            print(f"Geocoding falló para '{address}': {data['status']}")
            return None
    except Exception as e:
        print(f"Error geocodificando '{address}': {e}")
        return None