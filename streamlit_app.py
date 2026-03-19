"""
FactureScan Pro — Point d'entrée principal.

Gestion des onglets SANS query_params pour éviter les redirections
non voulues vers l'espace comptable.
L'onglet actif est géré uniquement via st.session_state["active_tab"].
"""
import streamlit as st
import streamlit.components.v1 as components

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
config      = load_config(cabinet_key)
inject_pwa(config.get("cabinet_name", "FactureScan Pro"))

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="app-header">
    <div class="app-logo">Facture<span>Scan</span> Pro</div>
    <div class="app-tagline">{config.get('cabinet_name','Cabinet Comptable')} · Transmission sécurisée de documents</div>
</div>
""", unsafe_allow_html=True)

# ── Onglets ───────────────────────────────────────────────────────────────────
# L'onglet actif est contrôlé uniquement par session_state["active_tab"]
# Valeurs : "client" (défaut) ou "admin"
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "client"

tab_client, tab_admin = st.tabs(["📷  Scanner une facture", "🔐  Espace comptable"])

with tab_client:
    render_client_page(config)

with tab_admin:
    render_admin_page(config)

# ── Activation JS de l'onglet admin si demandé ───────────────────────────────
# Injecté APRÈS le rendu des onglets, uniquement quand nécessaire.
# Utilise components.html (iframe) dont le JS accède à window.parent.
if st.session_state.get("active_tab") == "admin":
    components.html("""
    <script>
    (function() {
        var attempts = 0;
        function clickAdmin() {
            attempts++;
            try {
                var doc  = window.parent.document;
                var tabs = doc.querySelectorAll('[data-baseweb="tab"]');
                if (tabs && tabs.length >= 2) {
                    var isActive = tabs[1].getAttribute('aria-selected') === 'true'
                                || tabs[1].getAttribute('tabindex') === '0';
                    if (!isActive) {
                        tabs[1].click();
                    }
                    return;
                }
            } catch(e) {}
            if (attempts < 40) setTimeout(clickAdmin, 80);
        }
        clickAdmin();
        window.addEventListener('load', function() { setTimeout(clickAdmin, 50); });
    })();
    </script>
    """, height=0)

# ── Footer ────────────────────────────────────────────────────────────────────
from datetime import datetime
st.markdown(f"""
<div class="footer">
    FactureScan Pro · {config.get('cabinet_name','')} · {datetime.now().year}
</div>
""", unsafe_allow_html=True)