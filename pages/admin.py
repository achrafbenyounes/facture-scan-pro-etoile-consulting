"""
Page espace comptable : dashboard protégé par mot de passe.
"""
import hashlib
import streamlit as st
import pandas as pd
from datetime import datetime

from utils.history import get_history


def _check_password(password: str, config: dict) -> bool:
    h = hashlib.sha256(password.encode()).hexdigest()
    ref = hashlib.sha256(config.get("admin_password", "admin1234").encode()).hexdigest()
    return h == ref


def render_admin_page(config: dict):
    if "admin_logged" not in st.session_state:
        st.session_state.admin_logged = False

    # ── Login ──────────────────────────────────────────────────────────────
    if not st.session_state.admin_logged:
        st.markdown("""
        <div class="card">
            <div class="card-title">🔐 Connexion espace comptable</div>
        </div>
        """, unsafe_allow_html=True)

        pwd = st.text_input("Mot de passe", type="password", placeholder="••••••••")
        if st.button("Se connecter"):
            if _check_password(pwd, config):
                st.session_state.admin_logged = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")
        return

    # ── Dashboard ──────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="card">
        <div class="card-title">📊 Tableau de bord — {config.get('cabinet_name','')}</div>
    </div>
    """, unsafe_allow_html=True)

    history = get_history()
    nb_envois    = len(history)
    nb_clients   = len(set(h["client"] for h in history)) if history else 0
    nb_fichiers  = sum(h.get("nb_fichiers", 0) for h in history)
    nb_drive     = sum(1 for h in history if h.get("drive_links"))
    nb_ocr       = sum(1 for h in history if any(h.get("ocr_fields", [])))

    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-box"><div class="stat-num">{nb_envois}</div><div class="stat-label">Envois reçus</div></div>
        <div class="stat-box"><div class="stat-num">{nb_clients}</div><div class="stat-label">Clients actifs</div></div>
        <div class="stat-box"><div class="stat-num">{nb_fichiers}</div><div class="stat-label">Fichiers reçus</div></div>
        <div class="stat-box"><div class="stat-num">{nb_drive}</div><div class="stat-label">Dépôts Drive</div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Intégrations actives ──────────────────────────────────────────────
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        badge = "badge-ok" if config.get("smtp_user") else "badge-warn"
        label = "Actif" if config.get("smtp_user") else "Non configuré"
        st.markdown(f'📧 Email SMTP &nbsp; <span class="{badge}">{label}</span>', unsafe_allow_html=True)
    with col_b:
        badge = "badge-ok" if config.get("drive_enabled") else "badge-warn"
        label = "Actif" if config.get("drive_enabled") else "Désactivé"
        st.markdown(f'☁️ Google Drive &nbsp; <span class="{badge}">{label}</span>', unsafe_allow_html=True)
    with col_c:
        badge = "badge-ok" if config.get("ocr_enabled") else "badge-warn"
        label = "Actif" if config.get("ocr_enabled") else "Désactivé"
        st.markdown(f'🔍 OCR &nbsp; <span class="{badge}">{label}</span>', unsafe_allow_html=True)

    st.divider()

    # ── Historique ─────────────────────────────────────────────────────────
    if not history:
        st.info("Aucun envoi reçu pour l'instant. L'historique s'affichera ici.")
    else:
        st.subheader("Historique des envois")

        # Filtres
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            search = st.text_input("🔍 Rechercher un client", placeholder="Dupont SARL")
        with col_f2:
            types = ["Tous"] + list(set(h["type"] for h in history))
            filtre_type = st.selectbox("Filtrer par type", types)

        filtered = history
        if search:
            filtered = [h for h in filtered if search.lower() in h["client"].lower()]
        if filtre_type != "Tous":
            filtered = [h for h in filtered if h["type"] == filtre_type]

        # Table
        rows = []
        for h in reversed(filtered):
            drive_col = "✅" if h.get("drive_links") else "—"
            ocr_col   = "✅" if any(h.get("ocr_fields", [])) else "—"
            rows.append({
                "Date":       h["date"],
                "Client":     h["client"],
                "Email":      h["email"],
                "Type":       h["type"],
                "Période":    h["periode"],
                "Fichiers":   ", ".join(h["fichiers"]),
                "Drive":      drive_col,
                "OCR":        ocr_col,
                "Statut":     h["statut"],
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Détail OCR par envoi
        with st.expander("🔍 Détail OCR des envois"):
            for h in reversed(filtered):
                ocr_fields_list = h.get("ocr_fields", [])
                if any(ocr_fields_list):
                    st.markdown(f"**{h['date']} — {h['client']}**")
                    for i, fields in enumerate(ocr_fields_list):
                        if fields:
                            fname = h["fichiers"][i] if i < len(h["fichiers"]) else f"Fichier {i+1}"
                            st.markdown(f"*{fname}*")
                            st.json(fields)

        # Export CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️  Exporter en CSV",
            data=csv,
            file_name=f"facturescan_export_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    st.divider()

    # ── Guide config ──────────────────────────────────────────────────────
    with st.expander("⚙️  Guide de configuration — secrets.toml"):
        st.markdown("""
### Configuration minimale (single cabinet)
```toml
CABINET_NAME    = "Cabinet Dupont & Associés"
COMPTABLE_EMAIL = "comptable@cabinet.fr"
SMTP_HOST       = "smtp.gmail.com"
SMTP_PORT       = 587
SMTP_USER       = "expediteur@gmail.com"
SMTP_PASSWORD   = "xxxx xxxx xxxx xxxx"   # App password Gmail
ADMIN_PASSWORD  = "motdepasse_fort"
DRIVE_ENABLED   = false
OCR_ENABLED     = false
```

### Multi-cabinets
```toml
[cabinets.dupont]
CABINET_NAME    = "Cabinet Dupont"
COMPTABLE_EMAIL = "dupont@cabinet.fr"
SMTP_USER       = "noreply@cabinet.fr"
SMTP_PASSWORD   = "xxxx xxxx xxxx xxxx"
ADMIN_PASSWORD  = "dupont_admin"

[cabinets.martin]
CABINET_NAME    = "Cabinet Martin & Fils"
COMPTABLE_EMAIL = "martin@cabinet.fr"
SMTP_USER       = "noreply@cabinet.fr"
SMTP_PASSWORD   = "xxxx xxxx xxxx xxxx"
ADMIN_PASSWORD  = "martin_admin"
```

### Activer Google Drive
```toml
DRIVE_ENABLED          = true
DRIVE_ROOT_FOLDER_ID   = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
DRIVE_CREDENTIALS_JSON = '''{ "type": "service_account", ... }'''
```

### Activer l'OCR
```toml
OCR_ENABLED = true
```
> ⚠️ Nécessite `pytesseract`, `Pillow`, `pdfminer.six` dans requirements.txt
> et Tesseract installé sur le serveur (voir README).

### Gmail — Mot de passe d'application
1. Activez la vérification en 2 étapes → [myaccount.google.com/security](https://myaccount.google.com/security)
2. Créez un mot de passe d'application → [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Copiez le code 16 caractères dans `SMTP_PASSWORD`
        """)

    if st.button("🚪 Déconnexion"):
        st.session_state.admin_logged = False
        st.rerun()
