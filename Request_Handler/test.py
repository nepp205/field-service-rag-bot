#Erstellt nach Anleitung von Azure OpenAI SDK Dokumentation, angepasst von mir (Niklas) für die Verwendung mit Azure OpenAI Service.
#nur zum testen der Verbindung und der Anfragen an das Modell, wird nicht im finalen Code benötigt
from openai import OpenAI
import os
#Umgebungsvariablen aus .env laden, falls vorhanden (lokale Entwicklung)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass



#Deklaration der benötigten Umgebungsvariablen
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
deployment_name = "gpt-4o-mini-main"
api_key = os.getenv("AZURE_OPENAI_API_KEY")
MAX_TOKENS = 100

# Initialisierung des OpenAI-Clients mit den Azure-spezifischen Parametern
client = OpenAI(
    base_url=endpoint,
    api_key=api_key
)

# Testanfrage an die Chat-Completions-API mit einem einfachen Prompt, um die Verbindung zu überprüfen.
completion = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {
            "role": "user",
            "content": "What is the capital of France?",
        }
    ],
)

print(completion.choices[0].message)