import streamlit as st

def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,400&display=swap');

:root {
    --ink:    #0d0d0d;
    --paper:  #f5f2eb;
    --accent: #1a472a;
    --gold:   #c9a84c;
    --muted:  #6b6560;
    --border: #d4cfc6;
    --card:   #ffffff;
    --danger: #b91c1c;
    --info:   #1e40af;
}

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: var(--paper) !important;
    color: var(--ink);
}

.app-header {
    text-align: center;
    padding: 2.5rem 0 1.5rem;
    border-bottom: 2px solid var(--ink);
    margin-bottom: 2rem;
}
.app-logo {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 2.2rem;
    letter-spacing: -0.03em;
    color: var(--ink);
}
.app-logo span { color: var(--accent); }
.app-tagline {
    font-size: 0.82rem;
    color: var(--muted);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-top: 0.3rem;
}

.card {
    background: var(--card);
    border: 1.5px solid var(--border);
    border-radius: 4px;
    padding: 1.6rem 2rem;
    margin-bottom: 1.2rem;
    box-shadow: 3px 3px 0px var(--border);
}
.card-title {
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 1.2rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--ink);
}
.step-badge {
    background: var(--accent);
    color: white;
    font-size: 0.68rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 2px;
    font-family: 'Syne', sans-serif;
}

.success-box {
    background: #edf7ef;
    border: 1.5px solid var(--accent);
    border-radius: 4px;
    padding: 1.8rem;
    text-align: center;
    margin-bottom: 1rem;
}
.success-box h3 {
    font-family: 'Syne', sans-serif;
    font-size: 1.3rem;
    color: var(--accent);
    margin-bottom: 0.5rem;
}

.ocr-box {
    background: #f0f4ff;
    border: 1.5px solid #93c5fd;
    border-radius: 4px;
    padding: 1.2rem 1.4rem;
    margin-top: 0.8rem;
    font-size: 0.9rem;
}
.ocr-box h4 {
    font-family: 'Syne', sans-serif;
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--info);
    margin-bottom: 0.6rem;
}
.ocr-row {
    display: flex;
    justify-content: space-between;
    padding: 0.25rem 0;
    border-bottom: 1px solid #dbeafe;
}
.ocr-key { color: var(--muted); font-size: 0.82rem; }
.ocr-val { font-weight: 500; font-size: 0.85rem; }

.stat-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.stat-box {
    flex: 1; background: var(--card);
    border: 1.5px solid var(--border); border-radius: 4px;
    padding: 1.2rem; text-align: center;
    box-shadow: 2px 2px 0px var(--border);
}
.stat-num {
    font-family: 'Syne', sans-serif;
    font-size: 2rem; font-weight: 800; color: var(--accent);
}
.stat-label {
    font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--muted);
}

.badge-ok {
    background: #dcfce7; color: #166534;
    padding: 2px 10px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 600;
}
.badge-warn {
    background: #fef9c3; color: #854d0e;
    padding: 2px 10px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 600;
}

.stButton > button {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em !important;
    background-color: var(--ink) !important;
    color: var(--paper) !important;
    border: none !important;
    border-radius: 3px !important;
    padding: 0.65rem 2rem !important;
    width: 100% !important;
    transition: background 0.15s ease;
}
.stButton > button:hover { background-color: var(--accent) !important; }

[data-testid="stFileUploader"] {
    border: 2px dashed var(--border) !important;
    border-radius: 4px !important;
    background: #fafaf7 !important;
}

[data-testid="stSidebar"] { background-color: var(--ink) !important; }
[data-testid="stSidebar"] * { color: var(--paper) !important; }

.footer {
    text-align: center; font-size: 0.75rem; color: var(--muted);
    padding: 2rem 0 1rem;
    border-top: 1px solid var(--border); margin-top: 2.5rem;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* ── MOBILE RESPONSIVE ──────────────────────────────────────────────── */
@media (max-width: 640px) {
    .app-header  { padding: 1.6rem 0 1rem; }
    .app-logo    { font-size: 1.7rem; }
    .app-tagline { font-size: 0.72rem; }
    .card        { padding: 1.2rem 1rem; }

    [data-testid="column"] { min-width: 100% !important; }

    .stat-row  { flex-wrap: wrap; }
    .stat-box  { min-width: calc(50% - 0.5rem); }
    .stat-num  { font-size: 1.6rem; }

    .stButton > button {
        font-size: 1rem !important;
        padding: 0.9rem !important;
    }
    [data-testid="stTabs"] button {
        font-size: 0.78rem !important;
        padding: 8px 8px !important;
    }
    [data-testid="stFileUploader"] { padding: 0.8rem !important; }

    /* Espace pour le banner PWA fixé en bas */
    .main .block-container { padding-bottom: 100px !important; }
}

/* Mode standalone PWA */
@media (display-mode: standalone) {
    .main .block-container { padding-top: 1rem !important; }
    .app-header { padding-top: 1.5rem; }
}

/* Suppression tap highlight iOS */
* { -webkit-tap-highlight-color: transparent; }
button, label { touch-action: manipulation; }
</style>
""", unsafe_allow_html=True)
