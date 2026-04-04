from flask import Flask, request, jsonify
import Context_Handler as cH

webserver = Flask(__name__)

SECRET_TOKEN = "z6875426jgbk0d9fut6t3427fgd32fgdfhsijugfgdgfksdhbghbhw5ziuogtzufbdvhjghrw78tg782r4gdhjcg"


@webserver.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint für Docker"""
    return jsonify({'status': 'healthy'}), 200


@webserver.route('/context', methods=['POST'])
def get_Context():
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
    
    # Query aus Request-Body auslesen
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': 'Missing query parameter'}), 400
    
    query = data['query']
    
    # Context abrufen
    context = cH.retrieve_context(query)
    return jsonify({'context': context})