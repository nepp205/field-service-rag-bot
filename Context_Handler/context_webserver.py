# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt

from flask import Flask, request, jsonify
import Context_Handler as cH
from dotenv import load_dotenv
import os

load_dotenv()

webserver = Flask(__name__)

# Token für einfache Absicherung des Context-Endpunkts.
SECRET_TOKEN = os.getenv("WEBSERVER_TOKEN")

@webserver.route('/context', methods=['POST'])
def get_Context():
    # Nimmt Query + optionales Modell aus dem Request entgegen und liefert
    # den passenden Kontext aus der Vektor-Datenbank zurück
    # Authorization Header prüfen
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Missing Authorization header'}), 401
    
    # Token aus "Bearer <token>" extrahieren
    try:
        token = auth_header.split(' ')[1]
    except IndexError:
        return jsonify({'error': 'Invalid Authorization header format'}), 401
    
    # Token validieren
    if token != SECRET_TOKEN:
        return jsonify({'error': 'Invalid token'}), 401
    
    # Query und Model aus Request-Body auslesen
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': 'Missing query parameter'}), 400
    
    query = data['query']
    model = data.get('model', None)  # Optional: Model-Filter
    
    # Context abrufen
    context = cH.retrieve_context(query=query, model=model)
    return jsonify({'context': context})



######################## Test ###################################
if __name__ == "__main__":
    import requests
    import json

    url = "http://localhost:5000/context"
    token = SECRET_TOKEN

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    data = {
        "query": "Mein Geschirrspüler zeigt den Fehler F-404 an was soll ich tun?",
        "model": "pfd 401"  # Optional: Filtern nach Modellname
    }

    response = requests.post(url, headers=headers, json=data)
    print(json.dumps(response.json(), indent=2))