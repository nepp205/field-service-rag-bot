"""Field-Service-Bot – Streamlit Entry Point.

This module serves as the main UI layer of the Field-Service RAG bot.
It is built with Streamlit and acts as the front-end shell that will
eventually integrate with the RAG backend (rag_core) and the FastAPI
request handler (requesthandler).

Usage:
    streamlit run app.py
"""

import streamlit as st

# Page title and current team status overview
st.title("🔧 Field-Service-Bot v2")
st.header("Status")
st.success("✅ Niklas – UI")
st.info("⏳ Marvin – Data / Vector DB")
st.info("⏳ Tobias – RAG / LLM Chain")

st.caption("Repo ready – Team loslegen!")
