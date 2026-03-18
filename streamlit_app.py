"""
FactureScan Pro — Point d'entrée principal
"""
import streamlit as st

st.set_page_config(
    page_title="FactureScan Pro",
    page_icon="📄",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from utils.styles import inject_css
from utils.config import load_config, get_active_cabinet
from utils.pwa import inject_pwa
from pages.client import render_client_page
from pages.admin import render_admin_page
from pages.scan import render_scan_page

inject_css()
cabinet_key = get_active_cabinet()
config = load_config(cabinet_key)
inject_pwa(config.get("cabinet_name", "FactureScan Pro"))

# ── Header ──────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="app-header">
    <div class="app-logo">Facture<span>Scan</span> Pro</div>
    <div class="app-tagline">{config.get('cabinet_name','Cabinet Comptable')} · Transmission sécurisée de documents</div>
</div>
""", unsafe_allow_html=True)

# ── Navigation ───────────────────────────────────────────────────────────────
tab_client, tab_admin = st.tabs(["📷  Scanner une facture", "🔐  Espace comptable"])

with tab_client:
    render_client_page(config)

with tab_admin:
    render_admin_page(config)

# ── Footer ───────────────────────────────────────────────────────────────────
from datetime import datetime
st.markdown(f"""
<div class="footer">
    FactureScan Pro · {config.get('cabinet_name','')} · {datetime.now().year}
</div>
""", unsafe_allow_html=True)
