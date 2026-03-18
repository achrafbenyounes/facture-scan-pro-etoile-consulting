"""
Chargement de la configuration depuis st.secrets.
Supporte le mode multi-cabinets via un sélecteur en session.
"""
import streamlit as st


DEFAULTS = {
    "cabinet_name":     "Cabinet Comptable Demo",
    "comptable_email":  "comptable@exemple.fr",
    "smtp_host":        "smtp.gmail.com",
    "smtp_port":        587,
    "smtp_user":        "",
    "smtp_password":    "",
    "admin_password":   "admin1234",
    "drive_enabled":    False,
    "ocr_enabled":      False,
}


def _parse_bool(val):
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes")


def load_config(cabinet_key: str = "default") -> dict:
    """
    Charge la config pour un cabinet donné.

    Secrets attendus (mode single-cabinet) :
        CABINET_NAME, COMPTABLE_EMAIL, SMTP_HOST, SMTP_PORT,
        SMTP_USER, SMTP_PASSWORD, ADMIN_PASSWORD,
        DRIVE_ENABLED, DRIVE_CREDENTIALS_JSON, DRIVE_ROOT_FOLDER_ID,
        OCR_ENABLED

    Mode multi-cabinets — ajouter une section [cabinets.nom] dans secrets.toml :
        [cabinets.dupont]
        CABINET_NAME    = "Cabinet Dupont"
        COMPTABLE_EMAIL = "dupont@cabinet.fr"
        ...
    """
    try:
        secrets = st.secrets

        # ── Multi-cabinet : tente de lire la section dédiée ──────────────
        if "cabinets" in secrets and cabinet_key in secrets["cabinets"]:
            sec = secrets["cabinets"][cabinet_key]
        else:
            sec = secrets  # fallback sur la racine

        cfg = {
            "cabinet_name":            sec.get("CABINET_NAME",    DEFAULTS["cabinet_name"]),
            "comptable_email":         sec.get("COMPTABLE_EMAIL", DEFAULTS["comptable_email"]),
            "smtp_host":               sec.get("SMTP_HOST",       DEFAULTS["smtp_host"]),
            "smtp_port":           int(sec.get("SMTP_PORT",       DEFAULTS["smtp_port"])),
            "smtp_user":               sec.get("SMTP_USER",       DEFAULTS["smtp_user"]),
            "smtp_password":           sec.get("SMTP_PASSWORD",   DEFAULTS["smtp_password"]),
            "admin_password":          sec.get("ADMIN_PASSWORD",  DEFAULTS["admin_password"]),
            "drive_enabled":  _parse_bool(sec.get("DRIVE_ENABLED",  False)),
            "drive_credentials_json":  sec.get("DRIVE_CREDENTIALS_JSON", ""),
            "drive_root_folder_id":    sec.get("DRIVE_ROOT_FOLDER_ID", ""),
            "ocr_enabled":    _parse_bool(sec.get("OCR_ENABLED", True)),
            "google_vision_key":       sec.get("GOOGLE_VISION_API_KEY", ""),
        }
        return cfg

    except Exception:
        return dict(DEFAULTS)


def list_cabinets() -> dict[str, str]:
    """
    Retourne {clé: nom_affiché} pour tous les cabinets configurés.
    S'il n'y a pas de section [cabinets], retourne un seul cabinet 'default'.
    """
    try:
        secrets = st.secrets
        if "cabinets" in secrets:
            result = {}
            for key in secrets["cabinets"].keys():
                name = secrets["cabinets"][key].get("CABINET_NAME", key)
                result[key] = name
            return result
    except Exception:
        pass
    return {"default": load_config()["cabinet_name"]}


def get_active_cabinet() -> str:
    """Retourne la clé du cabinet actif (géré en session state)."""
    cabinets = list_cabinets()
    if len(cabinets) == 1:
        return list(cabinets.keys())[0]

    if "active_cabinet" not in st.session_state:
        st.session_state.active_cabinet = list(cabinets.keys())[0]

    # Sélecteur affiché dans la sidebar
    with st.sidebar:
        st.markdown("### 🏢 Cabinet")
        choice = st.selectbox(
            "Sélectionner",
            options=list(cabinets.keys()),
            format_func=lambda k: cabinets[k],
            key="cabinet_selector",
        )
        st.session_state.active_cabinet = choice

    return st.session_state.active_cabinet

