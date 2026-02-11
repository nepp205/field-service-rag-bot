import streamlit as st
import os

st.set_page_config(layout="wide")

# Header
st.markdown("# Field Service Support")
st.markdown("---")

# Begrüßung
st.markdown("### Techniker-Terminal")
st.markdown("Beschreiben Sie das Problem:")

# Input
col1, col2 = st.columns([3, 1])
with col1:
    user_input = st.text_input("", placeholder="Fehler E-404 Waschmaschine")
with col2:
    if st.button("Analysieren"):

        # Beispiel Output Area
        with st.container():
            st.markdown("### Analyse")
            st.markdown("""
            **Schritte:**
            1. Stromverbindung unterbrechen
            2. Kühlsystem prüfen  
            3. Filter reinigen
            
            **Quelle:** Handbuch Seite 12
            """)

# Footer
st.markdown("---")
st.caption("Field Service RAG Bot")
prompt = st.chat_input( "Wie kann ich Ihnen sonst noch helfen?")
if prompt:
    st.write(f"You entered: {prompt}")