"""
Gestion de l'historique des envois en session Streamlit.
En production, vous pouvez remplacer par une base SQLite ou Supabase.
"""
import streamlit as st
from datetime import datetime


def log_submission(client_info: dict, filenames: list, drive_links: list, ocr_results: list):
    key = "submission_history"
    if key not in st.session_state:
        st.session_state[key] = []

    st.session_state[key].append({
        "date":         datetime.now().strftime("%d/%m/%Y %H:%M"),
        "client":       client_info.get("nom", "—"),
        "email":        client_info.get("email", "—"),
        "telephone":    client_info.get("telephone", "—"),
        "type":         client_info.get("type_doc", "—"),
        "periode":      client_info.get("periode", "—"),
        "fichiers":     filenames,
        "nb_fichiers":  len(filenames),
        "drive_links":  drive_links,
        "ocr_fields":   [r.get("fields", {}) for r in ocr_results],
        "statut":       "✅ Envoyé",
    })


def get_history() -> list:
    return st.session_state.get("submission_history", [])
