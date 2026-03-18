"""
Page client — Scan mobile ultra-simplifié v3.
Zéro saisie, zéro liste clients dans secrets.toml.
L'IA lit tout depuis la facture.
"""
import streamlit as st
import time
from datetime import datetime

from utils.ocr_utils import run_ocr
from utils.classifier import analyze_invoice, CATEGORIES, FALLBACK_CATEGORY, build_drive_path, get_all_clients
from utils.drive_utils import smart_upload_to_drive
from utils.email_utils import send_to_accountant, send_confirmation_to_client
from utils.history import log_submission


# ────────────────────────────────────────────────────────────────────────────
# CSS mobile-first
# ────────────────────────────────────────────────────────────────────────────
MOBILE_CSS = """<style>
/* Styles interface mobile */

.result-card {
    background:#fff; border:1.5px solid #d4cfc6; border-radius:6px;
    padding:1.2rem 1.4rem; margin-bottom:1rem; box-shadow:3px 3px 0 #d4cfc6;
}
.result-header {
    display:flex; align-items:center; gap:10px; margin-bottom:.8rem;
    padding-bottom:.8rem; border-bottom:1px solid #e5e7eb;
}
.result-filename { font-weight:600; font-size:.9rem; color:#0d0d0d; word-break:break-all; }
.result-row {
    display:flex; justify-content:space-between; align-items:flex-start;
    padding:5px 0; font-size:.85rem; border-bottom:1px solid #f3f4f6; gap:8px;
}
.result-row:last-child { border-bottom:none; }
.result-key { color:#6b6560; flex-shrink:0; font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; padding-top:2px; }
.result-val { font-weight:500; text-align:right; font-size:.85rem; color:#0d0d0d; }

.badge-new  { background:#dbeafe;color:#1e40af;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700; }
.badge-ok   { background:#dcfce7;color:#166534;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700; }
.badge-warn { background:#fef9c3;color:#854d0e;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700; }
.badge-err  { background:#fee2e2;color:#991b1b;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700; }

.drive-path {
    background:#f8faff; border:1px solid #dbeafe; border-radius:4px;
    padding:8px 12px; font-family:monospace; font-size:.75rem;
    color:#1e40af; line-height:1.8; word-break:break-all;
}
.ocr-grid {
    display:grid; grid-template-columns:1fr 1fr; gap:6px;
    background:#f9fafb; border:1px solid #e5e7eb;
    border-radius:4px; padding:10px 12px; margin-top:6px; font-size:.78rem;
}
.ocr-k { color:#6b7280; }
.ocr-v { font-weight:500; color:#111827; word-break:break-all; }

.success-global {
    background:#edf7ef; border:2px solid #1a472a; border-radius:6px;
    padding:2rem; text-align:center; margin:1rem 0;
}
.success-global .big-check { font-size:3rem; }
.success-global h3 { font-family:'Syne',sans-serif; color:#1a472a; font-size:1.3rem; margin:.5rem 0; }
.success-global p { color:#6b6560; font-size:.9rem; }

.fallback-warn {
    background:#fffbeb; border:1.5px solid #f59e0b; border-radius:4px;
    padding:.8rem 1rem; font-size:.85rem; color:#92400e; margin-top:.5rem;
}
.new-client-info {
    background:#eff6ff; border:1.5px solid #93c5fd; border-radius:4px;
    padding:.8rem 1rem; font-size:.85rem; color:#1e40af; margin-top:.5rem;
}

@media (max-width:480px) {
    .cam-btn { width:140px; height:140px; }
    .cam-btn .cam-icon { font-size:2.5rem; }
    .ocr-grid { grid-template-columns:1fr; }
}
</style>"""



# ────────────────────────────────────────────────────────────────────────────
# Helpers d'affichage
# ────────────────────────────────────────────────────────────────────────────

def _client_badge(method: str, confidence: float, name: str, is_new: bool) -> str:
    if name == "Inconnu" or method == "none":
        return '<span class="badge-err">⚠ Non identifié → À classer</span>'
    if is_new:
        return f'<span class="badge-new">✦ Nouveau client · {name}</span>'
    if method in ("siret_db", "siret"):
        return f'<span class="badge-ok">✓ {name}</span>'
    if method == "name_db":
        return f'<span class="badge-ok">✓ {name}</span>'
    pct = int(confidence * 100)
    cls = "badge-ok" if pct >= 80 else "badge-warn"
    return f'<span class="{cls}">{name}</span>'

def _cat_icon(folder: str) -> str:
    for prefix, icon in [("1_","🛒"),("2_","💰"),("3_","🧾"),("4_","👥"),("5_","🏗"),("6_","🏦"),("0_","📥")]:
        if folder.startswith(prefix): return icon
    return "📄"

def _ocr_fields_html(fields: dict) -> str:
    if not fields:
        return ""
    rows = ""
    for k, v in fields.items():
        if k == "Sociétés détectées":
            continue
        rows += f'<div class="ocr-k">{k}</div><div class="ocr-v">{v}</div>'
    if not rows:
        return ""
    return f'<div class="ocr-grid">{rows}</div>'

def _result_card_html(fname: str, client: dict, analysis: dict, ocr: dict, drive_result: dict) -> str:
    cat      = analysis["category"]
    path     = analysis["drive_path"]
    dt       = analysis["invoice_date"]
    method   = analysis.get("match_method","none")
    conf     = analysis.get("confidence",0.0)
    is_new   = analysis.get("is_new_client", False)

    client_html = _client_badge(method, conf, client.get("name","?"), is_new)
    cat_icon    = _cat_icon(cat.get("folder",""))
    date_str    = (f"{dt[0]:02d}/{dt[1]:02d}/{dt[2]}" if dt else
                   datetime.now().strftime("%d/%m/%Y") + " (auj.)")

    if drive_result.get("success"):
        drive_html  = f'<a href="{drive_result["web_link"]}" target="_blank" style="color:#1e40af;font-size:12px;">Voir sur Drive ↗</a>'
        status_icon = "✅"
    elif drive_result.get("error"):
        drive_html  = f'<span style="color:#991b1b;font-size:12px;">{drive_result["error"][:60]}</span>'
        status_icon = "⚠️"
    else:
        drive_html  = '<span style="color:#9ca3af;font-size:12px;">Drive non configuré</span>'
        status_icon = "📧"

    path_display = " › ".join([path["client_folder"], path["exercice_folder"],
                                path["category_folder"], path["month_folder"]])
    ocr_html = _ocr_fields_html(ocr.get("fields", {}))

    siret_line = ""
    if client.get("siret") or client.get("siren"):
        siret_line += f'''
  <div class="result-row">
    <span class="result-key">SIRET/SIREN</span>
    <span class="result-val">{client.get("siret") or client.get("siren","")}</span>
  </div>'''

    # Email détecté sur la facture
    detected_email = ocr.get("client_email","")
    if detected_email:
        email_badge = f'<span class="badge-ok">✉ {detected_email} — confirmation envoyée</span>'
    else:
        email_badge = '<span style="color:#9ca3af;font-size:11px;">Email non détecté sur la facture</span>'
    siret_line += f'''
  <div class="result-row">
    <span class="result-key">Email client</span>
    <span class="result-val">{email_badge}</span>
  </div>'''

    return f"""
<div class="result-card">
  <div class="result-header">
    <span style="font-size:1.3rem;">{status_icon}</span>
    <span class="result-filename">{fname}</span>
  </div>
  <div class="result-row">
    <span class="result-key">Client</span>
    <span class="result-val">{client_html}</span>
  </div>{siret_line}
  <div class="result-row">
    <span class="result-key">Catégorie</span>
    <span class="result-val">{cat_icon} {cat.get("label","—")}</span>
  </div>
  <div class="result-row">
    <span class="result-key">Date facture</span>
    <span class="result-val">{date_str}</span>
  </div>
  <div class="result-row">
    <span class="result-key">Classement Drive</span>
    <span class="result-val">
      <div class="drive-path">{path_display}</div>
      <div style="margin-top:4px;">{drive_html}</div>
    </span>
  </div>
  {"<div class='result-row'><span class='result-key'>Données OCR</span><span class='result-val' style='width:100%;'>" + ocr_html + "</span></div>" if ocr_html else ""}
</div>"""


# ────────────────────────────────────────────────────────────────────────────
# Page principale
# ────────────────────────────────────────────────────────────────────────────

def render_client_page(config: dict):
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)

    # ── Résultat après traitement ─────────────────────────────────────────
    if st.session_state.get("scan_done"):
        nb_ok        = st.session_state.get("scan_nb_ok", 0)
        nb_total     = st.session_state.get("scan_nb_total", 0)
        results_html = st.session_state.get("scan_results_html", "")
        any_fallback = st.session_state.get("scan_any_fallback", False)
        new_clients  = st.session_state.get("scan_new_clients", [])
        email_error  = st.session_state.get("email_error")

        st.markdown(f"""
        <div class="success-global">
            <div class="big-check">✅</div>
            <h3>{nb_ok}/{nb_total} facture(s) classée(s)</h3>
            <p>Votre comptable a été notifié automatiquement.</p>
        </div>""", unsafe_allow_html=True)

        if new_clients:
            names = ", ".join(new_clients)
            st.markdown(f"""
            <div class="new-client-info">
                ✦ <strong>Nouveau(x) client(s) détecté(s) :</strong> {names}<br>
                <span style="font-size:12px;">Enregistrés automatiquement dans la base locale.</span>
            </div>""", unsafe_allow_html=True)

        if any_fallback:
            st.markdown("""
            <div class="fallback-warn">
                ⚠️ <strong>Certaines factures n'ont pas pu être identifiées</strong>
                et sont placées dans <code>0_A_Classer</code>.
                Votre comptable recevra une alerte email.
            </div>""", unsafe_allow_html=True)

        st.markdown(results_html, unsafe_allow_html=True)

        if email_error is None:
            st.success("📧 Email envoyé au comptable.")
        elif email_error:
            st.error(f"📧 Erreur email : {email_error}")
            st.info("💡 Vérifiez SMTP_PASSWORD dans secrets.toml → https://myaccount.google.com/apppasswords")

        if st.button("📷 Scanner d'autres factures"):
            st.session_state.scan_done = False
            st.rerun()
        return

    # ── Interface scan ─────────────────────────────────────────────────────
    cabinet_name = config.get("cabinet_name", "votre comptable")

    # CSS pour transformer le file_uploader en gros bouton caméra sur mobile
    st.markdown("""
    <style>
    /* Cache le drag&drop desktop, garde seulement le bouton sur mobile */
    @media (max-width: 768px) {
        [data-testid="stFileUploaderDropzone"] > div:first-child {
            display: none !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            border: none !important;
            background: transparent !important;
            padding: 0 !important;
        }
    }
    /* Bouton Browse Files → style caméra */
    [data-testid="stFileUploaderDropzone"] button {
        width: 100% !important;
        background: #1a472a !important;
        color: #f5f2eb !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 1.2rem 2rem !important;
        font-family: 'Syne', sans-serif !important;
        font-weight: 700 !important;
        font-size: 1.1rem !important;
        letter-spacing: 0.05em !important;
        cursor: pointer !important;
        margin-top: 0.5rem !important;
    }
    [data-testid="stFileUploaderDropzone"] button:hover {
        background: #2d6a4f !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="text-align:center;padding:.8rem 0 .4rem;">
        <p style="color:#6b6560;font-size:.85rem;margin:0;">
            📷 Scannez une facture · Classement automatique chez
            <strong>{cabinet_name}</strong>
        </p>
    </div>""", unsafe_allow_html=True)

    files = st.file_uploader(
        "📷  Prendre une photo ou choisir un fichier",
        type=["pdf", "jpg", "jpeg", "png", "heic", "webp"],
        accept_multiple_files=True,
    )

    # Sur mobile : ouvre directement la caméra arrière
    st.markdown("""
    <script>
    (function() {
        function patchInput() {
            var inputs = window.parent.document.querySelectorAll(
                '[data-testid="stFileUploaderDropzone"] input[type="file"]'
            );
            inputs.forEach(function(inp) {
                if (!inp.hasAttribute("capture")) {
                    inp.setAttribute("capture", "environment");
                }
            });
        }
        // Patch immédiat + retry pour les reruns Streamlit
        patchInput();
        setTimeout(patchInput, 500);
        setTimeout(patchInput, 1500);
    })();
    </script>
    """, unsafe_allow_html=True)

    if not files:
        return

    # ── Traitement automatique ─────────────────────────────────────────────
    nb_total     = len(files)
    nb_ok        = 0
    any_fallback = False
    new_clients  = []
    results_html = ""
    all_analyses = []
    fallback_files = []

    progress_bar = st.progress(0, text="Analyse en cours…")

    for i, f in enumerate(files):
        progress_bar.progress(int(i/nb_total*100), text=f"Analyse {f.name} ({i+1}/{nb_total})…")

        # OCR complet (Google Vision si clé configurée)
        api_key = config.get("google_vision_key", "")
        ocr = run_ocr(f, api_key=api_key)

        # Classification autonome (no client list)
        analysis = analyze_invoice(ocr)
        client   = analysis["client"]
        is_fb    = analysis["is_fallback"]

        if is_fb:
            any_fallback = True
            fallback_files.append(f.name)

        if analysis.get("is_new_client") and client.get("name") != "Inconnu":
            if client["name"] not in new_clients:
                new_clients.append(client["name"])

        # Upload Drive
        drive_result = {}
        if config.get("drive_enabled"):
            drive_result = smart_upload_to_drive(
                config, f, analysis["drive_path"], analysis["invoice_date"]
            )

        if not is_fb:
            nb_ok += 1

        results_html += _result_card_html(f.name, client, analysis, ocr, drive_result)
        all_analyses.append({"file": f, "ocr": ocr, "analysis": analysis, "drive": drive_result})

    progress_bar.progress(100, text="Analyse terminée ✓")
    time.sleep(0.4)
    progress_bar.empty()

    # ── Email comptable ────────────────────────────────────────────────────
    email_error = None
    try:
        if not config.get("smtp_user") or not config.get("smtp_password"):
            email_error = "SMTP_USER ou SMTP_PASSWORD manquant dans secrets.toml"
        else:
            # ── Un email par facture avec les vraies données OCR ──────────────
            for r in all_analyses:
                ocr      = r["ocr"]
                analysis = r["analysis"]
                client   = analysis["client"]
                category = analysis["category"]
                fields   = ocr.get("fields", {})

                # Construire client_info depuis les données OCR réelles
                client_info = {
                    "nom":       client.get("name", fields.get("Émetteur", "Inconnu")),
                    "email":     ocr.get("client_email", ""),
                    "telephone": fields.get("Téléphone", "Non renseigné"),
                    "type_doc":  category.get("label", "Facture"),
                    "periode":   fields.get("Date", datetime.now().strftime("%d/%m/%Y")),
                    "note":      (
                        f"N° Facture : {fields.get('N° Facture','')} | "
                        f"Montant TTC : {fields.get('Montant TTC','')} | "
                        f"SIRET : {ocr.get('siret','')}"
                    ).strip(" |"),
                }

                drive_links = []
                if r["drive"].get("success"):
                    drive_links = [{"name": r["file"].name, "url": r["drive"].get("web_link","")}]

                # Email au comptable
                send_to_accountant(
                    config, client_info,
                    [r["file"]], [ocr], drive_links
                )

                # Confirmation au client si email détecté sur la facture
                detected_email = ocr.get("client_email", "")
                if detected_email:
                    try:
                        send_confirmation_to_client(
                            config, client_info,
                            [r["file"]], [ocr], detected_email
                        )
                    except Exception:
                        pass

            if fallback_files:
                _send_fallback_alert(config, fallback_files)
    except Exception as e:
        email_error = str(e)

    # ── Log — une entrée par facture avec les vraies données OCR ────────────
    for r in all_analyses:
        ocr      = r["ocr"]
        analysis = r["analysis"]
        client   = analysis["client"]
        fields   = ocr.get("fields", {})

        log_submission(
            {
                "nom":       client.get("name", fields.get("Émetteur", "Inconnu")),
                "email":     ocr.get("client_email", ""),
                "telephone": fields.get("Téléphone", ""),
                "type_doc":  analysis["category"].get("label", "Facture"),
                "periode":   fields.get("Date", datetime.now().strftime("%d/%m/%Y")),
                "note":      fields.get("N° Facture", ""),
            },
            [r["file"].name],
            [{"name": r["file"].name, "url": r["drive"].get("web_link", "")}]
            if r["drive"].get("success") else [],
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


# ────────────────────────────────────────────────────────────────────────────
# Email alerte fallback
# ────────────────────────────────────────────────────────────────────────────

def _send_fallback_alert(config: dict, filenames: list):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    msg = MIMEMultipart()
    msg["From"]    = config["smtp_user"]
    msg["To"]      = config["comptable_email"]
    msg["Subject"] = f"[FactureScan] ⚠️ {len(filenames)} facture(s) à classer manuellement"
    body = (f"Bonjour,\n\nCes factures n'ont pas pu être identifiées automatiquement :\n\n"
            + "\n".join(f"  • {f}" for f in filenames)
            + f"\n\nElles sont dans le dossier '0_A_Classer'.\n\n— FactureScan Pro · {config.get('cabinet_name','')}")
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as s:
        s.starttls()
        s.login(config["smtp_user"], config["smtp_password"])
        s.send_message(msg)