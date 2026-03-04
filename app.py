import streamlit as st
import streamlit.components.v1 as components
from typing import List, Dict

# Optional: versuche das RAG-Modul zu laden. Wenn vorhanden, wird es benutzt.
try:
    from rag_core import RAG, InMemoryRetriever, SimpleLLM  # type: ignore
    _RAG_AVAILABLE = True
except Exception:
    RAG = None  # type: ignore
    InMemoryRetriever = None  # type: ignore
    _RAG_AVAILABLE = False


def safe_rerun() -> None:
    """Versucht, Streamlits experimental rerun aufzurufen, falls vorhanden.

    Einige Streamlit-Versionen exportieren `st.experimental_rerun`, andere nicht.
    Diese Hilfsfunktion vermeidet AttributeError auf älteren/neuen Versionen.
    """
    rerun = getattr(st, "experimental_rerun", None)
    if callable(rerun):
        try:
            rerun()
        except Exception:
            # Falls ein Fehler beim Auslösen auftritt, ignorieren und weiterlaufen.
            pass


def init_session_state() -> None:
    """Initialisiert benötigte Session-State Felder."""
    st.set_page_config(layout="wide")
    st.session_state.setdefault("messages", [])  # Liste[Dict]: {role: 'user'|'assistant', content: str}


def render_header() -> None:
    """Kopfbereich mit Titel und kurzer Begrüßung für Techniker."""
    st.title("Field Service Support")
    st.markdown("Freundliche, knappe Begrüßung für Techniker. Beschreibe kurz das Problem oben im Chat-Feld.")
    st.markdown("---")


def generate_dummy_response(user_input: str) -> Dict:
    """Erzeugt eine formatierte Dummy-Antwort und zugehörige Dokumentations-Metadaten.

    Hier Tobias: später RAG-Chain einsetzen — diese Funktion soll die RAG-Query aufrufen
    und ein dict mit keys 'content', 'source_quote', 'pdf_url' zurückgeben.
    """
    # Dummy formatted numbered steps (Markdown)
    content = (
        f"**Diagnose für:** {user_input}\n\n"
        "1. Stromverbindung trennen und Spannungsversorgung prüfen.\n"
        "2. Sichtprüfung des Kühlsystems (Belüftung, Lüfter).\n"
        "3. Filter und Wärmeübertrager auf Verunreinigungen prüfen und reinigen.\n"
        "4. Gerät neu starten und Funktionstest ausführen.\n\n"
        "**Hinweis:** Falls das Problem weiterhin besteht, Logdaten sichern und Support kontaktieren."
    )

    # Falls das RAG-Modul verfügbar ist, nutze es (Tobias/Marvin später ersetzen)
    if _RAG_AVAILABLE:
        try:
            # Wenn ein SimpleLLM vorhanden ist, übergeben wir es an RAG (Tobias kann hier seine Chain einsetzen)
            try:
                llm = SimpleLLM()
            except Exception:
                llm = None
            rag = RAG(retriever=InMemoryRetriever(), llm=llm)
            return rag.answer(user_input)
        except Exception:
            # Falls es bei der RAG-Nutzung ein Problem gibt, fällt die Funktion zurück
            pass

    # Dummy source quote and PDF (Marvin: hier später echte Quelle / PDF-Basis einbinden)
    source_quote = 'E-404 tritt bei Überhitzung auf. Kühler reinigen und Filter prüfen.'
    pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"

    return {"content": content, "source_quote": source_quote, "pdf_url": pdf_url}


def render_documentation(source_quote: str, pdf_url: str) -> None:
    """Rendert den Dokumentations-Expander mit Zitat und PDF-Viewer."""
    with st.expander("Dokumentation"):
        # Zitat anzeigen
        st.markdown(f"> {source_quote}")

        # PDF-Viewer: Platzhalter-URL; später ersetzt durch Marvins PDF-Service
        components.iframe(src=pdf_url, width=700, height=420)


def render_chat_area() -> None:
    """Rendert den Chatverlauf (Historie) und das Eingabefeld.

    Beim Absenden wird die Dummy-Antwort generiert und in `st.session_state.messages` angehängt.
    """
    st.header("Techniker-Terminal")

    # Chatverlauf anzeigen
    for msg in st.session_state.messages:
        role = msg.get("role", "assistant")
        with st.chat_message(role):
            st.markdown(msg.get("content", ""))

            # Wenn es eine Assistant-Nachricht ist, zeigen wir darunter die Dokumentation an
            if role == "assistant":
                # Die Metadaten (quote/pdf) sind in msg.get('meta') gespeichert, falls vorhanden
                meta = msg.get("meta", {})
                source_quote = meta.get("source_quote", "")
                pdf_url = meta.get("pdf_url", "")
                if source_quote or pdf_url:
                    render_documentation(source_quote or "", pdf_url or "")

    # Eingabefeld für neue Nachrichten
    user_input = st.chat_input("Problem beschreiben...")
    if user_input:
        # Benutzer-Nachricht speichern
        st.session_state.messages.append({"role": "user", "content": user_input})

        # Antwort erzeugen (hier Dummy). Tobias: statt generate_dummy_response() die RAG-Chain aufrufen
        resp = generate_dummy_response(user_input)

        # Assistant-Nachricht inklusive Meta-Infos speichern
        st.session_state.messages.append({
            "role": "assistant",
            "content": resp["content"],
            "meta": {"source_quote": resp["source_quote"], "pdf_url": resp["pdf_url"]},
        })

    # Neu rendern: einige Streamlit-Versionen haben st.experimental_rerun entfernt.
    # Wir versuchen einen sicheren Aufruf, falls verfügbar; ansonsten verlassen
    # wir die Funktion und Streamlit führt bei der nächsten Interaktion ein Re-run aus.
    safe_rerun()


def render_sidebar() -> None:
    """Rendert die Sidebar mit Controls (z.B. Chat zurücksetzen)."""
    with st.sidebar:
        st.header("Controls")
        if st.button("Chat zurücksetzen"):
            st.session_state.messages = []
            safe_rerun()


def main() -> None:
    init_session_state()
    render_header()

    # Layout: Hauptbereich wird für Chat genutzt; Sidebar ist oben durch st.sidebar()-Block
    render_chat_area()
    render_sidebar()


if __name__ == "__main__":
    main()
