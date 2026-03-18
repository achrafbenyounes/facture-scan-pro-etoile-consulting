"""
Historique des envois — persisté en JSON local.
"""
import json
import os
import streamlit as st
from datetime import datetime

HISTORY_FILE = os.path.join(
    os.path.dirname(__file__), "..", ".streamlit", "history.json"
)

def _load() -> list:
    if "submission_history" in st.session_state:
        return st.session_state["submission_history"]
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                st.session_state["submission_history"] = data
                return data
    except Exception:
        pass
    st.session_state["submission_history"] = []
    return st.session_state["submission_history"]

def _save(history: list):
    st.session_state["submission_history"] = history
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def log_submission(client_info: dict, filenames: list, drive_links: list, ocr_results: list):
    history = _load()
    history.append({
        "date":         datetime.now().strftime("%d/%m/%Y %H:%M"),
        "date_iso":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        "client":       client_info.get("nom", "—"),
        "email":        client_info.get("email", ""),
        "telephone":    client_info.get("telephone", ""),
        "type":         client_info.get("type_doc", "—"),
        "periode":      client_info.get("periode", "—"),
        "fichiers":     filenames,
        "nb_fichiers":  len(filenames),
        "drive_links":  drive_links,
        "ocr_fields":   [r.get("fields", {}) for r in ocr_results],
        "statut":       "Envoyé",
    })
    _save(history)

def delete_file_entry(entry_index: int, filename: str):
    """
    Supprime UN fichier précis dans UNE entrée précise (par index).
    Evite toute suppression en cascade sur des fichiers homonymes.
    """
    history = _load()
    if entry_index < 0 or entry_index >= len(history):
        return
    entry = history[entry_index]
    fichiers    = entry.get("fichiers", [])
    drive_links = entry.get("drive_links", [])
    ocr_fields  = entry.get("ocr_fields", [])

    # Trouver l'index exact du fichier dans l'entrée
    try:
        file_pos = fichiers.index(filename)
    except ValueError:
        return

    new_fichiers    = fichiers[:file_pos] + fichiers[file_pos+1:]
    new_drive_links = [l for l in drive_links if l.get("name") != filename]
    new_ocr         = ocr_fields[:file_pos] + ocr_fields[file_pos+1:]

    if new_fichiers:
        history[entry_index]["fichiers"]    = new_fichiers
        history[entry_index]["drive_links"] = new_drive_links
        history[entry_index]["ocr_fields"]  = new_ocr
        history[entry_index]["nb_fichiers"] = len(new_fichiers)
    else:
        history.pop(entry_index)

    _save(history)

def get_history() -> list:
    return _load()