# Nur zum Testen der Azure OpenAI Verbindung – wird nicht im produktiven Code verwendet
# Erstellt nach Azure OpenAI SDK Dokumentation, angepasst von Niklas

import os
from openai import AzureOpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()  # .env laden falls vorhanden (lokale entwicklung)
except Exception:
    pass

# verbindungsdaten aus umgebungsvariablen
client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2024-02-01",
)

# testanfrage um verbindung zu prüfen
response = client.chat.completions.create(
    model="gpt-4o-mini-main",
    messages=[{"role": "user", "content": "What is the capital of France?"}],
    max_tokens=100,
)

print(response.choices[0].message.content)
