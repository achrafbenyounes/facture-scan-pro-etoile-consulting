"""
Espace comptable — Dashboard responsive PC et mobile.
"""
import hashlib
import streamlit as st
from datetime import datetime

from utils.history import get_history, delete_file_entry

ADMIN_CSS = """<style>
/* ── Layout responsive ────────────────────────────────────────────── */
.dash-header {
    display:flex; align-items:center; justify-content:space-between;
    flex-wrap:wrap; gap:.5rem; margin-bottom:1.5rem;
}
.dash-title {
    font-family:'Syne',sans-serif; font-weight:800;
    font-size:1.3rem; color:#0d0d0d; margin:0;
}
.dash-sub { font-size:.8rem; color:#6b6560; margin:0; }

/* ── Stats ────────────────────────────────────────────────────────── */
.stats-grid {
    display:grid;
    grid-template-columns: repeat(4, 1fr);
    gap:.8rem; margin-bottom:1.5rem;
}
@media (max-width:600px) {
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
.stat-card {
    background:#fff; border:1.5px solid #d4cfc6; border-radius:8px;
    padding:1rem .8rem; text-align:center; box-shadow:2px 2px 0 #d4cfc6;
}
.stat-n {
    font-family:'Syne',sans-serif; font-size:2rem;
    font-weight:800; color:#1a472a; line-height:1.1;
}
.stat-l {
    font-size:.68rem; text-transform:uppercase;
    letter-spacing:.08em; color:#6b6560; margin-top:3px;
}

/* ── Search ───────────────────────────────────────────────────────── */
.search-hint {
    font-size:.75rem; color:#9ca3af;
    text-align:center; margin-bottom:.8rem;
}

/* ── Client card ─────────────────────────────────────────────────── */
.client-card {
    background:#fff; border:1.5px solid #d4cfc6; border-radius:8px;
    margin-bottom:.8rem; overflow:hidden; box-shadow:2px 2px 0 #d4cfc6;
}
.client-top {
    display:flex; align-items:center; justify-content:space-between;
    padding:.9rem 1.2rem; border-bottom:1px solid #f3f4f6; flex-wrap:wrap; gap:.5rem;
}
.client-name {
    font-family:'Syne',sans-serif; font-weight:700;
    font-size:1rem; color:#0d0d0d; display:flex; align-items:center; gap:8px;
}
.client-meta {
    font-size:.75rem; color:#6b6560;
    display:flex; gap:1rem; flex-wrap:wrap; align-items:center;
}
.client-body { padding:.8rem 1.2rem 1rem; }

/* ── Contact pills ───────────────────────────────────────────────── */
.contact-row {
    display:flex; gap:.6rem; flex-wrap:wrap; margin-bottom:.8rem;
}
.contact-pill {
    background:#f3f4f6; border-radius:20px;
    padding:3px 12px; font-size:.75rem; color:#374151;
    display:flex; align-items:center; gap:5px;
}
.contact-pill a { color:#1e40af; text-decoration:none; }

/* ── Année / Mois ────────────────────────────────────────────────── */
.year-badge {
    display:inline-flex; align-items:center; gap:6px;
    background:#edf7ef; color:#1a472a; border-radius:4px;
    padding:3px 10px; font-family:'Syne',sans-serif;
    font-weight:700; font-size:.75rem; text-transform:uppercase;
    letter-spacing:.06em; margin-bottom:.5rem;
}
.month-label {
    font-size:.72rem; font-weight:600; color:#6b6560;
    text-transform:uppercase; letter-spacing:.06em;
    margin:.4rem 0 .3rem .5rem;
}

/* ── Invoice row ─────────────────────────────────────────────────── */
.inv-row {
    display:grid;
    grid-template-columns: 1.8rem 1fr auto auto auto auto;
    align-items:center; gap:.5rem;
    padding:7px 10px; background:#f9fafb;
    border:1px solid #e5e7eb; border-radius:6px;
    margin-bottom:4px; font-size:.8rem;
}
@media (max-width:600px) {
    .inv-row {
        grid-template-columns: 1.5rem 1fr auto auto;
    }
    .inv-hide-mobile { display:none !important; }
}
.inv-name {
    font-weight:500; color:#0d0d0d;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.inv-cat {
    font-size:.68rem; padding:2px 7px; border-radius:20px;
    background:#f3f4f6; color:#374151; white-space:nowrap;
}
.inv-amt  { font-weight:700; color:#1a472a; white-space:nowrap; font-size:.82rem; }
.inv-date { color:#9ca3af; font-size:.72rem; white-space:nowrap; }

/* ── Intégrations ────────────────────────────────────────────────── */
.integ-row {
    display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:.5rem;
}
.integ-pill {
    display:flex; align-items:center; gap:6px;
    padding:4px 12px; border-radius:20px;
    font-size:.78rem; font-weight:600;
}
.integ-ok   { background:#dcfce7; color:#166534; }
.integ-warn { background:#fef9c3; color:#854d0e; }

/* ── Empty state ─────────────────────────────────────────────────── */
.empty-state {
    text-align:center; padding:3rem 1rem; color:#9ca3af;
}
.empty-state .icon { font-size:2.5rem; margin-bottom:.5rem; }

/* ── Login card ──────────────────────────────────────────────────── */
.login-wrap {
    max-width:380px; margin:2rem auto;
    background:#fff; border:1.5px solid #d4cfc6; border-radius:10px;
    padding:2rem 2rem 1.5rem; box-shadow:4px 4px 0 #d4cfc6;
}
.login-title {
    font-family:'Syne',sans-serif; font-weight:800;
    font-size:1.2rem; color:#0d0d0d; margin-bottom:1.5rem; text-align:center;
}
</style>"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _check_password(pwd, config):
    h   = hashlib.sha256(pwd.encode()).hexdigest()
    ref = hashlib.sha256(config.get("admin_password","admin1234").encode()).hexdigest()
    return h == ref

def _cat_icon(t):
    for k, v in [("Achat","🛒"),("Fournisseur","🛒"),("Vente","💰"),("Client","💰"),
                 ("Frais","🧾"),("Note","🧾"),("Salaire","👥"),("Social","👥"),
                 ("Immobili","🏗"),("Banque","🏦"),("Tréso","🏦")]:
        if k.lower() in t.lower(): return v
    return "📄"

def _build_tree(history):
    tree = {}
    for idx, entry in enumerate(history):
        # Nom client
        client = entry.get("client","")
        if not client or client in ("Scan auto","—",""):
            ocrs = entry.get("ocr_fields",[])
            client = next((f.get("Emetteur", f.get("Émetteur","")) for f in ocrs if f), "") or "À identifier"

        # Email / téléphone : entrée puis ocr_fields
        email = entry.get("email","")
        phone = entry.get("telephone","")
        for ocr in entry.get("ocr_fields",[]):
            if not email: email = ocr.get("Email","")
            if not phone: phone = ocr.get("Telephone", ocr.get("Téléphone",""))

        # Date
        ds = entry.get("date_iso") or entry.get("date","")
        try:
            dt   = datetime.strptime(ds[:16], "%Y-%m-%d %H:%M" if "-" in ds[:4] else "%d/%m/%Y %H:%M")
            year = str(dt.year)
            mth  = dt.strftime("%m — %B")
        except Exception:
            year, mth = "—", "—"

        if client not in tree:
            tree[client] = {"meta": {"email":email,"telephone":phone,"nb":0,"last":entry.get("date","")}, "years":{}}
        else:
            if email and not tree[client]["meta"].get("email"): tree[client]["meta"]["email"] = email
            if phone and not tree[client]["meta"].get("telephone"): tree[client]["meta"]["telephone"] = phone

        node = tree[client]
        node["meta"]["nb"] += len(entry.get("fichiers",[]))
        node["meta"]["last"] = entry.get("date", node["meta"]["last"])

        if year not in node["years"]: node["years"][year] = {}
        if mth not in node["years"][year]: node["years"][year][mth] = []

        fnames  = entry.get("fichiers",[])
        dlinks  = {l["name"]: l["url"] for l in entry.get("drive_links",[]) if l.get("url")}
        ocr_lst = entry.get("ocr_fields",[])

        for fpos, fname in enumerate(fnames):
            ocr = ocr_lst[fpos] if fpos < len(ocr_lst) else {}
            node["years"][year][mth].append({
                "filename":    fname,
                "type":        entry.get("type","—"),
                "date":        entry.get("date",""),
                "drive_url":   dlinks.get(fname,""),
                "montant":     ocr.get("Montant TTC",""),
                "num":         ocr.get("N° Facture",""),
                "entry_index": idx,
                "file_pos":    fpos,
            })
    return tree


# ─────────────────────────────────────────────────────────────────────────────
# Page principale
# ─────────────────────────────────────────────────────────────────────────────

def render_admin_page(config: dict):
    st.markdown(ADMIN_CSS, unsafe_allow_html=True)

    if "admin_logged" not in st.session_state:
        st.session_state.admin_logged = False

    # ── Login ──────────────────────────────────────────────────────────────────
    if not st.session_state.admin_logged:
        st.markdown("""
        <style>
        .login-outer {
            max-width:360px; margin:1.5rem auto 0;
            background:#fff; border:1.5px solid #d4cfc6; border-radius:10px;
            padding:1.8rem 1.5rem 0.5rem; box-shadow:4px 4px 0 #d4cfc6;
        }
        .login-outer h3 {
            font-family:'Syne',sans-serif; font-weight:800; font-size:1.1rem;
            color:#0d0d0d; margin:0 0 1.2rem; text-align:center;
        }
        </style>
        <div class="login-outer"><h3>🔐 Espace comptable</h3></div>
        """, unsafe_allow_html=True)
        pwd = st.text_input("Mot de passe", type="password",
                            placeholder="Entrez votre mot de passe")
        if st.button("Se connecter", use_container_width=True):
            if _check_password(pwd, config):
                st.session_state.admin_logged = True
                st.query_params["tab"] = "admin"
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")
        return

    # ── Toast post-suppression ─────────────────────────────────────────────────
    if st.session_state.get("_del_toast"):
        st.toast(f"🗑️ {st.session_state.pop('_del_toast')} supprimé")

    # ── Header ─────────────────────────────────────────────────────────────────
    cabinet = config.get("cabinet_name","Cabinet")
    now_str = datetime.now().strftime("%d/%m/%Y")
    st.markdown(f"""
    <div class="dash-header">
        <div>
            <p class="dash-title">📁 {cabinet}</p>
            <p class="dash-sub">Tableau de bord · {now_str}</p>
        </div>
    </div>""", unsafe_allow_html=True)

    history = get_history()
    tree    = _build_tree(history)

    # ── Stats ───────────────────────────────────────────────────────────────────
    nb_clients  = len(tree)
    nb_factures = sum(c["meta"]["nb"] for c in tree.values())
    nb_drive    = sum(1 for e in history for l in e.get("drive_links",[]) if l.get("url"))
    nb_envois   = len(history)

    st.markdown(f"""
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-n">{nb_clients}</div><div class="stat-l">Clients</div></div>
        <div class="stat-card"><div class="stat-n">{nb_factures}</div><div class="stat-l">Factures</div></div>
        <div class="stat-card"><div class="stat-n">{nb_drive}</div><div class="stat-l">Sur Drive</div></div>
        <div class="stat-card"><div class="stat-n">{nb_envois}</div><div class="stat-l">Envois</div></div>
    </div>""", unsafe_allow_html=True)

    # ── Recherche ───────────────────────────────────────────────────────────────
    search = st.text_input("🔍", placeholder="Rechercher un client, email, téléphone…",
                           label_visibility="collapsed")

    # ── Liste clients ───────────────────────────────────────────────────────────
    if not tree:
        st.markdown("""
        <div class="empty-state">
            <div class="icon">📭</div>
            <div>Aucune facture reçue pour l'instant.</div>
            <div style="font-size:.8rem;margin-top:4px">
                Les factures scannées apparaîtront ici automatiquement.
            </div>
        </div>""", unsafe_allow_html=True)
    else:
        filtered = {
            n: d for n, d in sorted(tree.items())
            if not search
            or search.lower() in n.lower()
            or search.lower() in d["meta"].get("email","").lower()
            or search.lower() in d["meta"].get("telephone","").lower()
        }

        if not filtered:
            st.info(f"Aucun résultat pour « {search} »")

        for cname, cdata in filtered.items():
            meta  = cdata["meta"]
            email = meta.get("email","")
            phone = meta.get("telephone","")
            nb    = meta["nb"]
            last  = meta.get("last","")[:10]

            with st.expander(f"🏢 {cname} — {nb} fichier(s) · {last}", expanded=False):

                # Contact pills
                pills = ""
                if email: pills += f'<span class="contact-pill">✉ <a href="mailto:{email}">{email}</a></span>'
                if phone: pills += f'<span class="contact-pill">📞 {phone}</span>'
                pills += f'<span class="contact-pill">📂 {nb} fichier(s)</span>'
                st.markdown(f'<div class="contact-row">{pills}</div>', unsafe_allow_html=True)

                # Arborescence
                for year in sorted(cdata["years"], reverse=True):
                    st.markdown(f'<div class="year-badge">📅 {year}</div>', unsafe_allow_html=True)

                    for mth in sorted(cdata["years"][year], reverse=True):
                        invs = cdata["years"][year][mth]
                        st.markdown(
                            f'<div class="month-label">└─ {mth} &nbsp;({len(invs)} fichier(s))</div>',
                            unsafe_allow_html=True
                        )

                        for inv in invs:
                            icon = _cat_icon(inv["type"])
                            c1, c2, c3, c4, c5, c6 = st.columns([.5, 3.5, 2, 1.5, 1.2, .6])

                            with c1: st.markdown(f"<div style='font-size:1.1rem;padding-top:4px'>{icon}</div>", unsafe_allow_html=True)
                            with c2:
                                name = inv["filename"][:35] + "…" if len(inv["filename"]) > 35 else inv["filename"]
                                st.markdown(f"**{name}**")
                                if inv.get("drive_url"):
                                    st.markdown(f"[☁️ Drive]({inv['drive_url']})")
                            with c3: st.caption(inv["type"])
                            with c4: st.markdown(f"**{inv['montant']}**" if inv["montant"] else "—")
                            with c5: st.caption(inv["date"][:10] if inv["date"] else "")
                            with c6:
                                if st.button("🗑️", key=f"d_{inv['entry_index']}_{inv['file_pos']}",
                                             help="Supprimer"):
                                    delete_file_entry(inv["entry_index"], inv["filename"])
                                    st.session_state["_del_toast"] = inv["filename"]
                                    st.query_params["tab"] = "admin"
                                    st.rerun()

    st.divider()

    # ── Statut intégrations ─────────────────────────────────────────────────────
    with st.expander("⚙️ Intégrations & Configuration"):
        smtp_ok  = bool(config.get("smtp_user"))
        drive_ok = config.get("drive_enabled", False)
        ocr_ok   = bool(config.get("google_vision_key"))

        st.markdown(f"""
        <div class="integ-row">
            <span class="integ-pill {'integ-ok' if smtp_ok else 'integ-warn'}">
                📧 SMTP {'Actif' if smtp_ok else 'Non configuré'}
            </span>
            <span class="integ-pill {'integ-ok' if drive_ok else 'integ-warn'}">
                ☁️ Drive {'Actif' if drive_ok else 'Désactivé'}
            </span>
            <span class="integ-pill {'integ-ok' if ocr_ok else 'integ-warn'}">
                🔍 OCR {'Google Vision' if ocr_ok else 'Non configuré'}
            </span>
        </div>""", unsafe_allow_html=True)

        if not drive_ok:
            st.warning("Google Drive désactivé — activez-le dans secrets.toml pour un stockage permanent.")
        if not ocr_ok:
            st.warning("Clé Google Vision manquante — l'extraction OCR sera limitée.")

    col_logout, _ = st.columns([1, 3])
    with col_logout:
        if st.button("🚪 Déconnexion", use_container_width=True):
            st.session_state.admin_logged = False
            st.query_params.clear()
            st.rerun()