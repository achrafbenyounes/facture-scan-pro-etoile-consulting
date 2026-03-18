"""
Intégration Google Drive — v2 Smart Filing.

Arborescence automatique :
  <racine_cabinet> /
    <Client — SIREN> /
      <Exercice> /
        <Catégorie comptable> /
          <MM_Mois> /
            facture_xxx.pdf
"""

import io
import json
import re
from datetime import datetime
from typing import Optional
import streamlit as st

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    from google.oauth2 import service_account
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False

SCOPES      = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def _get_service(credentials_json: str):
    if not DRIVE_AVAILABLE:
        raise ImportError("google-api-python-client non installé.")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _cache_key(parent_id, name):
    return f"drive_folder__{parent_id}__{name}"

def _get_cached(parent_id, name):
    return st.session_state.get(_cache_key(parent_id, name))

def _set_cached(parent_id, name, fid):
    st.session_state[_cache_key(parent_id, name)] = fid


def _sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _find_or_create_folder(service, name: str, parent_id: str) -> str:
    safe = _sanitize(name)
    cached = _get_cached(parent_id, safe)
    if cached:
        return cached
    q = (f"name='{safe}' and mimeType='{FOLDER_MIME}' "
         f"and '{parent_id}' in parents and trashed=false")
    res = service.files().list(q=q, fields="files(id)").execute()
    files = res.get("files", [])
    if files:
        fid = files[0]["id"]
    else:
        meta = {"name": safe, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        fid  = service.files().create(body=meta, fields="id").execute()["id"]
    _set_cached(parent_id, safe, fid)
    return fid


def _get_mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {"pdf":"application/pdf","jpg":"image/jpeg","jpeg":"image/jpeg",
            "png":"image/png","heic":"image/heic","webp":"image/webp"}.get(ext,"application/octet-stream")


def _build_filename(original: str, category_folder: str, invoice_date) -> str:
    date_str = (invoice_date or datetime.now()).strftime("%Y-%m-%d")
    cat_slug = category_folder.split("_")[0] if "_" in category_folder else category_folder
    ext  = original.rsplit(".", 1)[-1].lower() if "." in original else "pdf"
    base = re.sub(r'[^\w\-.]', '_', original.rsplit(".", 1)[0])[:40]
    return f"{date_str}_{cat_slug}_{base}.{ext}"


def smart_upload_to_drive(config: dict, file, drive_path: dict, invoice_date=None) -> dict:
    if not config.get("drive_enabled") or not config.get("drive_credentials_json"):
        return {"success": False, "error": "Drive non configuré."}
    try:
        service     = _get_service(config["drive_credentials_json"])
        root_id     = config["drive_root_folder_id"]
        client_id   = _find_or_create_folder(service, drive_path["client_folder"],   root_id)
        exercice_id = _find_or_create_folder(service, drive_path["exercice_folder"], client_id)
        category_id = _find_or_create_folder(service, drive_path["category_folder"], exercice_id)
        month_id    = _find_or_create_folder(service, drive_path["month_folder"],    category_id)
        new_filename = _build_filename(file.name, drive_path["category_folder"], invoice_date)
        file.seek(0)
        media    = MediaIoBaseUpload(io.BytesIO(file.read()), mimetype=_get_mime(file.name), resumable=True)
        uploaded = service.files().create(
            body={"name": new_filename, "parents": [month_id]},
            media_body=media, fields="id,webViewLink"
        ).execute()
        service.permissions().create(
            fileId=uploaded["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()
        file.seek(0)
        return {"success": True, "web_link": uploaded.get("webViewLink",""),
                "folder_path": drive_path["path_display"], "filename": new_filename,
                "file_id": uploaded["id"], "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def ensure_client_folders(config: dict, client_list: list) -> dict:
    if not config.get("drive_enabled") or not config.get("drive_credentials_json"):
        return {}
    try:
        service = _get_service(config["drive_credentials_json"])
        root_id = config["drive_root_folder_id"]
        result  = {}
        for client in client_list:
            siren  = re.sub(r'\s', '', client.get("siren", ""))
            suffix = f" — {siren[:9]}" if siren else ""
            fid    = _find_or_create_folder(service, f"{client['name']}{suffix}", root_id)
            result[client["name"]] = fid
        return result
    except Exception as e:
        return {"error": str(e)}
