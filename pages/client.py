"""
Page client — Scan universel Android/iPhone/Desktop.
Upload natif Streamlit : fonctionne sur tous les appareils.
"""
import streamlit as st
import time
from datetime import datetime

from utils.ocr_utils import run_ocr
from utils.classifier import analyze_invoice, CATEGORIES, FALLBACK_CATEGORY, build_drive_path, get_all_clients
from utils.drive_utils import smart_upload_to_drive
from utils.email_utils import send_to_accountant, send_confirmation_to_client
from utils.history import log_submission


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
CLIENT_CSS = """<style>
/* ── Upload zone ──────────────────────────────────────────────────── */
[data-testid="stFileUploaderDropzone"] {
    background: #1a472a !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 2rem 1rem !important;
    cursor: pointer !important;
}
[data-testid="stFileUploaderDropzone"] > div {
    color: #f5f2eb !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > span {
    color: #f5f2eb !important;
    font-family: 'Syne', sans-serif !important;
    font-size: 1.1rem !important;
    font-weight: 700 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > small {
    color: #a7c4b0 !important;
    font-size: 0.8rem !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background: #f5f2eb !important;
    color: #1a472a !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    padding: 0.5rem 1.5rem !important;
    margin-top: 0.8rem !important;
}
/* ── Résultat carte ───────────────────────────────────────────────── */
.r-card {
    background:#fff; border:1.5px solid #d4cfc6; border-radius:8px;
    padding:1.2rem 1.4rem; margin-bottom:1rem; box-shadow:2px 2px 0 #d4cfc6;
}
.r-header {
    display:flex; align-items:center; gap:10px; margin-bottom:.8rem;
    padding-bottom:.8rem; border-bottom:1px solid #e5e7eb;
}
.r-fname { font-weight:700; font-size:.95rem; color:#0d0d0d; word-break:break-all; flex:1; }
.r-row {
    display:flex; justify-content:space-between; align-items:flex-start;
    padding:6px 0; font-size:.85rem; border-bottom:1px solid #f3f4f6; gap:8px;
    flex-wrap: wrap;
}
.r-row:last-child { border-bottom:none; }
.r-key {
    color:#6b6560; flex-shrink:0; font-size:.72rem;
    text-transform:uppercase; letter-spacing:.07em; padding-top:3px;
    min-width: 100px;
}
.r-val { font-weight:500; font-size:.85rem; color:#0d0d0d; text-align:right; flex:1; }
.r-path {
    background:#f0f7ff; border:1px solid #bfdbfe; border-radius:4px;
    padding:6px 10px; font-family:monospace; font-size:.72rem;
    color:#1e40af; line-height:1.8; word-break:break-all; margin-top:4px;
}
/* ── Badges ──────────────────────────────────────────────────────── */
.bk-new  { background:#dbeafe;color:#1e40af;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700; }
.bk-ok   { background:#dcfce7;color:#166534;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700; }
.bk-warn { background:#fef9c3;color:#854d0e;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700; }
.bk-err  { background:#fee2e2;color:#991b1b;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700; }
/* ── OCR grid ────────────────────────────────────────────────────── */
.ocr-grid {
    display:grid; grid-template-columns:auto 1fr; gap:4px 12px;
    background:#f9fafb; border:1px solid #e5e7eb;
    border-radius:4px; padding:10px 12px; margin-top:6px; font-size:.78rem;
}
.ocr-k { color:#6b7280; }
.ocr-v { font-weight:500; color:#111827; word-break:break-all; }
/* ── Succès ─────────────────────────────────────────────────────── */
.success-box {
    background:#edf7ef; border:2px solid #1a472a; border-radius:8px;
    padding:2rem; text-align:center; margin:1rem 0;
}
.success-box h3 { font-family:'Syne',sans-serif; color:#1a472a; font-size:1.4rem; margin:.5rem 0; }
.success-box p  { color:#6b6560; font-size:.9rem; }
/* ── Alertes ─────────────────────────────────────────────────────── */
.warn-box {
    background:#fffbeb; border:1.5px solid #f59e0b; border-radius:6px;
    padding:.8rem 1rem; font-size:.85rem; color:#92400e; margin-top:.5rem;
}
.info-box {
    background:#eff6ff; border:1.5px solid #93c5fd; border-radius:6px;
    padding:.8rem 1rem; font-size:.85rem; color:#1e40af; margin-top:.5rem;
}
/* ── Mobile ─────────────────────────────────────────────────────── */
@media (max-width: 600px) {
    .r-key { min-width: 80px; font-size:.68rem; }
    .r-val { font-size:.8rem; }
    .ocr-grid { grid-template-columns: 1fr; }
    .r-path { font-size:.65rem; }
}
</style>"""

# JS injecté UNE SEULE FOIS pour activer capture=environment sur mobile
CAPTURE_JS = """<script>
(function(){
    function patch(){
        var els = window.parent.document.querySelectorAll(
            '[data-testid="stFileUploaderDropzone"] input[type="file"]'
        );
        els.forEach(function(el){
            el.setAttribute("capture","environment");
            el.setAttribute("accept","image/*,application/pdf");
        });
    }
    patch();
    setTimeout(patch, 400);
    setTimeout(patch, 1200);
    // Observer pour reruns Streamlit
    var obs = new MutationObserver(patch);
    obs.observe(window.parent.document.body, {childList:true, subtree:true});
})();
</script>"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers affichage
# ─────────────────────────────────────────────────────────────────────────────

def _badge(method, confidence, name, is_new):
    if not name or name == "Inconnu" or method == "none":
        return '<span class="bk-err">⚠ Non identifié</span>'
    if is_new:
        return f'<span class="bk-new">✦ Nouveau · {name}</span>'
    if method in ("siret_db", "siret", "name_db", "ocr_new"):
        return f'<span class="bk-ok">✓ {name}</span>'
    pct = int(confidence * 100)
    return f'<span class="{"bk-ok" if pct>=80 else "bk-warn"}">{name}</span>'

def _cat_icon(folder):
    for p, i in [("1_","🛒"),("2_","💰"),("3_","🧾"),("4_","👥"),("5_","🏗"),("6_","🏦"),("0_","📥")]:
        if folder.startswith(p): return i
    return "📄"

def _ocr_grid(fields):
    if not fields: return ""
    rows = "".join(
        f'<div class="ocr-k">{k}</div><div class="ocr-v">{v}</div>'
        for k, v in fields.items()
        if k not in ("Sociétés détectées","company_names")
    )
    return f'<div class="ocr-grid">{rows}</div>' if rows else ""

def _result_card(fname, client, analysis, ocr, drive_result):
    cat    = analysis["category"]
    path   = analysis["drive_path"]
    dt     = analysis["invoice_date"]
    fields = ocr.get("fields", {})

    badge     = _badge(analysis.get("match_method","none"), analysis.get("confidence",0),
                       client.get("name","?"), analysis.get("is_new_client",False))
    icon      = _cat_icon(cat.get("folder",""))
    date_str  = f"{dt[0]:02d}/{dt[1]:02d}/{dt[2]}" if dt else datetime.now().strftime("%d/%m/%Y")
    path_disp = " › ".join([path["client_folder"], path["exercice_folder"],
                              path["category_folder"], path["month_folder"]])

    if drive_result.get("success"):
        st_icon   = "✅"
        drive_row = f'<a href="{drive_result["web_link"]}" target="_blank" style="color:#1e40af;font-size:12px;">☁️ Voir sur Drive</a>'
    else:
        st_icon   = "📧"
        drive_row = '<span style="color:#9ca3af;font-size:11px;">Drive non configuré</span>'

    siret_str = client.get("siret") or client.get("siren","")
    email_str = ocr.get("client_email","")
    email_row = (f'<span class="bk-ok">✉ {email_str}</span>' if email_str
                 else '<span style="color:#9ca3af;font-size:11px;">—</span>')

    ocr_section = _ocr_grid(fields)
    ocr_html = (f'<div class="r-row"><span class="r-key">OCR</span>'
                f'<span class="r-val" style="text-align:left;">{ocr_section}</span></div>'
                if ocr_section else "")

    return f"""
<div class="r-card">
  <div class="r-header">
    <span style="font-size:1.4rem">{st_icon}</span>
    <span class="r-fname">{fname}</span>
  </div>
  <div class="r-row"><span class="r-key">Client</span><span class="r-val">{badge}</span></div>
  {"<div class='r-row'><span class='r-key'>SIRET</span><span class='r-val'>" + siret_str + "</span></div>" if siret_str else ""}
  <div class="r-row"><span class="r-key">Email</span><span class="r-val">{email_row}</span></div>
  <div class="r-row"><span class="r-key">Catégorie</span><span class="r-val">{icon} {cat.get("label","—")}</span></div>
  <div class="r-row"><span class="r-key">Date</span><span class="r-val">{date_str}</span></div>
  <div class="r-row">
    <span class="r-key">Drive</span>
    <span class="r-val">
      <div class="r-path">{path_disp}</div>
      <div style="margin-top:4px">{drive_row}</div>
    </span>
  </div>
  {ocr_html}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Page principale
# ─────────────────────────────────────────────────────────────────────────────

def render_client_page(config: dict):
    st.markdown(CLIENT_CSS, unsafe_allow_html=True)

    # ── Succès ────────────────────────────────────────────────────────────────
    if st.session_state.get("scan_done"):
        nb_ok        = st.session_state.get("scan_nb_ok", 0)
        nb_total     = st.session_state.get("scan_nb_total", 0)
        results_html = st.session_state.get("scan_results_html", "")
        any_fallback = st.session_state.get("scan_any_fallback", False)
        new_clients  = st.session_state.get("scan_new_clients", [])
        email_error  = st.session_state.get("email_error")

        st.markdown(f"""
        <div class="success-box">
            <div style="font-size:3rem">✅</div>
            <h3>{nb_ok}/{nb_total} facture(s) envoyée(s)</h3>
            <p>Votre comptable a été notifié automatiquement.</p>
        </div>""", unsafe_allow_html=True)

        if new_clients:
            st.markdown(f'<div class="info-box">✦ <strong>Nouveau(x) client(s) :</strong> {", ".join(new_clients)}</div>',
                        unsafe_allow_html=True)
        if any_fallback:
            st.markdown('<div class="warn-box">⚠️ Certaines factures n\'ont pas pu être identifiées → placées dans <code>0_A_Classer</code></div>',
                        unsafe_allow_html=True)

        st.markdown(results_html, unsafe_allow_html=True)

        if email_error is None:
            st.success("📧 Email envoyé au comptable.")
        elif email_error:
            st.error(f"📧 Erreur email : {email_error}")
            st.caption("💡 Vérifiez SMTP_PASSWORD → myaccount.google.com/apppasswords")

        if st.button("📷 Scanner d'autres factures", use_container_width=True):
            st.session_state.scan_done = False
            st.rerun()
        return

    # ── Interface upload ──────────────────────────────────────────────────────
    cabinet = config.get("cabinet_name", "votre comptable")
    st.markdown(f"""
    <div style="text-align:center;padding:.6rem 0 .8rem;">
        <p style="color:#6b6560;font-size:.9rem;margin:0;">
            📄 Transmettez vos factures à <strong>{cabinet}</strong>
        </p>
        <p style="color:#9ca3af;font-size:.75rem;margin:4px 0 0;">
            Photo, galerie ou PDF · Classement automatique
        </p>
    </div>""", unsafe_allow_html=True)

    # Uploader natif — fonctionne Android, iPhone, Desktop
    files = st.file_uploader(
        "📷 Prendre une photo ou choisir un fichier",
        type=["pdf", "jpg", "jpeg", "png", "heic", "webp"],
        accept_multiple_files=True,
        help="Android/iPhone : appuyez pour ouvrir la caméra ou la galerie",
    )

    # JS : active capture=environment sur mobile (ouvre caméra arrière)
    st.markdown(CAPTURE_JS, unsafe_allow_html=True)

    if not files:
        st.markdown("""
        <div style="text-align:center;padding:1rem 0;color:#9ca3af;font-size:.8rem;">
            Sur mobile : appuyez sur <strong>Browse files</strong> pour scanner
        </div>""", unsafe_allow_html=True)
        return

    # ── Traitement ────────────────────────────────────────────────────────────
    nb_total     = len(files)
    nb_ok        = 0
    any_fallback = False
    new_clients  = []
    results_html = ""
    all_analyses = []
    fallback_files = []
    api_key = config.get("google_vision_key", "")

    progress = st.progress(0, text="Analyse en cours…")

    for i, f in enumerate(files):
        progress.progress(int(i / nb_total * 100), text=f"📄 {f.name} ({i+1}/{nb_total})…")

        # OCR
        ocr = run_ocr(f, api_key=api_key)

        # Classification
        analysis = analyze_invoice(ocr)
        client   = analysis["client"]
        is_fb    = analysis["is_fallback"]

        if is_fb:
            any_fallback = True
            fallback_files.append(f.name)
        if analysis.get("is_new_client") and client.get("name") != "Inconnu":
            if client["name"] not in new_clients:
                new_clients.append(client["name"])

        # Drive
        drive_result = {}
        if config.get("drive_enabled"):
            drive_result = smart_upload_to_drive(config, f, analysis["drive_path"], analysis["invoice_date"])

        if not is_fb:
            nb_ok += 1

        results_html += _result_card(f.name, client, analysis, ocr, drive_result)
        all_analyses.append({"file": f, "ocr": ocr, "analysis": analysis, "drive": drive_result})

    progress.progress(100, text="✅ Analyse terminée")
    time.sleep(0.3)
    progress.empty()

    # ── Emails ────────────────────────────────────────────────────────────────
    email_error = None
    try:
        if not config.get("smtp_user") or not config.get("smtp_password"):
            email_error = "SMTP non configuré dans secrets.toml"
        else:
            for r in all_analyses:
                ocr      = r["ocr"]
                analysis = r["analysis"]
                client   = analysis["client"]
                fields   = ocr.get("fields", {})

                client_info = {
                    "nom":       client.get("name", fields.get("Emetteur", fields.get("Émetteur", "Inconnu"))),
                    "email":     ocr.get("client_email", ""),
                    "telephone": fields.get("Telephone", fields.get("Téléphone", "")),
                    "type_doc":  analysis["category"].get("label", "Facture"),
                    "periode":   fields.get("Date emission", fields.get("Date", datetime.now().strftime("%d/%m/%Y"))),
                    "note":      " | ".join(filter(None, [
                        f"N° {fields.get('N° Facture','')}" if fields.get("N° Facture") else "",
                        f"TTC : {fields.get('Montant TTC','')}" if fields.get("Montant TTC") else "",
                        f"SIRET : {ocr.get('siret','')}" if ocr.get("siret") else "",
                    ])),
                }

                drive_links = []
                if r["drive"].get("success"):
                    drive_links = [{"name": r["file"].name, "url": r["drive"].get("web_link","")}]

                # Email au comptable
                send_to_accountant(config, client_info, [r["file"]], [ocr], drive_links)

                # Confirmation client si email détecté
                if ocr.get("client_email"):
                    try:
                        send_confirmation_to_client(config, client_info, [r["file"]], [ocr], ocr["client_email"])
                    except Exception:
                        pass

            if fallback_files:
                _alert_fallback(config, fallback_files)
    except Exception as e:
        email_error = str(e)

    # ── Log ───────────────────────────────────────────────────────────────────
    for r in all_analyses:
        ocr      = r["ocr"]
        analysis = r["analysis"]
        client   = analysis["client"]
        fields   = ocr.get("fields", {})
        log_submission(
            {
                "nom":       client.get("name", "Inconnu"),
                "email":     ocr.get("client_email", ""),
                "telephone": fields.get("Telephone", fields.get("Téléphone", "")),
                "type_doc":  analysis["category"].get("label", "Facture"),
                "periode":   fields.get("Date emission", fields.get("Date", "")),
                "note":      fields.get("N° Facture", ""),
            },
            [r["file"].name],
            [{"name": r["file"].name, "url": r["drive"].get("web_link","")}] if r["drive"].get("success") else [],
            [ocr],
        )

    st.session_state.scan_done         = True
    st.session_state.scan_results_html = results_html
    st.session_state.scan_nb_ok        = nb_ok
    st.session_state.scan_nb_total     = nb_total
    st.session_state.scan_any_fallback = any_fallback
    st.session_state.scan_new_clients  = new_clients
    st.session_state.email_error       = email_error
    st.rerun()


def _alert_fallback(config, filenames):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    msg = MIMEMultipart()
    msg["From"]    = config["smtp_user"]
    msg["To"]      = config["comptable_email"]
    msg["Subject"] = f"[FactureScan] ⚠️ {len(filenames)} facture(s) à classer"
    body = (f"Ces factures n'ont pas pu être identifiées :\n\n"
            + "\n".join(f"  • {f}" for f in filenames)
            + f"\n\nElles sont dans '0_A_Classer'.\n— {config.get('cabinet_name','')}")
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as s:
        s.starttls()
        s.login(config["smtp_user"], config["smtp_password"])
        s.send_message(msg)