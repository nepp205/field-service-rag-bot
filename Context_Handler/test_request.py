# für diesen test muss der Docker container des context handlers laufen
# test für modulares debugging und testen
import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_TOKEN = os.getenv("WEBSERVER_TOKEN")

url = "http://localhost:5000/context"
token = SECRET_TOKEN
headers = {
    "Authorization": f"Bearer {token}",  # Token des webservers für Authentifizierung
    "Content-Type": "application/json"
}
data = {
    "query": "Mein Geschirrspüler zeigt den Fehler F-404 an was soll ich tun?",
    # "query": "Hab Fehler bei mein Produkt brauch Hilfe?",
    "model": "pdr 508"  # Optional: Filtern nach Modellname
}
response = requests.post(url, headers=headers, json=data)
print(json.dumps(response.json(), indent=2))