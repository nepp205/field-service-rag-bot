import streamlit as st
import os

st.set_page_config(layout="wide")

# Header
st.markdown("# Field Service Support")
st.markdown("---")

# Chat Interface
st.markdown("### Techniker-Terminal")

# Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Chat Display
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat Input
if user_input := st.chat_input("Problem beschreiben..."):
    # User Message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # Bot Response
    with st.chat_message("assistant"):
        response = f"""
        **Diagnose für '{user_input}':**
        
        1. Stromverbindung trennen
        2. Kühlsystem inspizieren  
        3. Filter reinigen
        4. Testlauf starten
        
        **Status**: Erledigt in 15 Min
        """
        st.markdown(response)
        
        # Quellen Expander mit PDF-Viewer
        with st.expander("Dokumentation (Seite 12)"):
            # Mock PDF Base64 (später Marvin's PDFs)
            st.markdown("""
            **Handbuch XYZ - Seite 12**
            
            > "E-404 tritt bei Überhitzung auf. Kühler reinigen..."
            """)
            
            # PDF Viewer (streamlit.components)
            st.components.v1.iframe(
                src="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
                width=800, height=400
            )
    
    st.session_state.messages.append({"role": "assistant", "content": response})

# Sidebar
with st.sidebar:
    st.markdown("### Controls")
    if st.button("Chat zurücksetzen"):
        st.session_state.messages = []
        st.rerun()
