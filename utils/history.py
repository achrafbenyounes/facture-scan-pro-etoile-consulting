"""
Historique des envois — persisté en JSON avec bytes base64.
Les bytes des fichiers sont encodés en base64 et sauvegardés dans history.json
pour permettre le téléchargement même après redémarrage de l'application.
"""
import json, os, base64
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

def log_submission(client_info: dict, filenames: list, drive_links: list,
                   ocr_results: list, file_bytes_map: dict = None):
    """
    file_bytes_map : { filename: bytes }
    Les bytes sont encodés en base64 et persistés dans history.json.
    """
    history = _load()

    # Encoder les bytes en base64 pour la persistance JSON
    b64_map = {}
    if file_bytes_map:
        for fname, fbytes in file_bytes_map.items():
            if fbytes:
                try:
                    b64_map[fname] = base64.b64encode(fbytes).decode("utf-8")
                except Exception:
                    pass

    history.append({
        "date":          datetime.now().strftime("%d/%m/%Y %H:%M"),
        "date_iso":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        "client":        client_info.get("nom", "—"),
        "email":         client_info.get("email", ""),
        "telephone":     client_info.get("telephone", ""),
        "type":          client_info.get("type_doc", "—"),
        "periode":       client_info.get("periode", "—"),
        "fichiers":      filenames,
        "nb_fichiers":   len(filenames),
        "drive_links":   drive_links,
        "ocr_fields":    [r.get("fields", {}) for r in ocr_results],
        "statut":        "Envoyé",
        "file_bytes_b64": b64_map,   # bytes persistés en base64
    })
    _save(history)

def get_file_bytes(entry_index: int, filename: str) -> tuple:
    """
    Retourne (bytes, mime_type) pour un fichier donné.
    Fonctionne même après redémarrage grâce à la persistance base64.
    """
    history = _load()
    if entry_index < 0 or entry_index >= len(history):
        return None, None
    entry = history[entry_index]

    # Chercher d'abord dans file_bytes_b64 (persisté)
    b64_map = entry.get("file_bytes_b64", {})
    b64     = b64_map.get(filename)
    if b64:
        try:
            data = base64.b64decode(b64)
        except Exception:
            data = None
    else:
        # Fallback : file_bytes_map en session (compat ancienne version)
        fbm  = entry.get("file_bytes_map", {})
        data = fbm.get(filename)

    if not data:
        return None, None

    ext  = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime = {
        "pdf":  "application/pdf",
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
        "png":  "image/png",
        "heic": "image/heic",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")
    return data, mime

def delete_file_entry(entry_index: int, filename: str):
    history = _load()
    if entry_index < 0 or entry_index >= len(history):
        return
    entry       = history[entry_index]
    fichiers    = entry.get("fichiers", [])
    drive_links = entry.get("drive_links", [])
    ocr_fields  = entry.get("ocr_fields", [])
    b64_map     = entry.get("file_bytes_b64", {})

    try:
        file_pos = fichiers.index(filename)
    except ValueError:
        return

    new_fichiers    = fichiers[:file_pos] + fichiers[file_pos+1:]
    new_drive_links = [l for l in drive_links if l.get("name") != filename]
    new_ocr         = ocr_fields[:file_pos] + ocr_fields[file_pos+1:]
    b64_map.pop(filename, None)

    if new_fichiers:
        history[entry_index]["fichiers"]       = new_fichiers
        history[entry_index]["drive_links"]    = new_drive_links
        history[entry_index]["ocr_fields"]     = new_ocr
        history[entry_index]["nb_fichiers"]    = len(new_fichiers)
        history[entry_index]["file_bytes_b64"] = b64_map
    else:
        history.pop(entry_index)

    _save(history)

def get_history() -> list:
    return _load()