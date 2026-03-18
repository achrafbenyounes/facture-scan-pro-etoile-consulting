"""
Envoi d'emails via SMTP.
- Email principal au comptable (avec PJ + résumé OCR)
- Email de confirmation au client
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from typing import IO


def _build_smtp(config: dict):
    server = smtplib.SMTP(config["smtp_host"], config["smtp_port"])
    server.ehlo()
    server.starttls()
    server.login(config["smtp_user"], config["smtp_password"])
    return server


def send_to_accountant(config: dict, client_info: dict, files: list, ocr_results: list, drive_links: list):
    """Envoie les factures au comptable avec résumé OCR et liens Drive."""
    msg = MIMEMultipart()
    msg["From"]    = config["smtp_user"]
    msg["To"]      = config["comptable_email"]
    msg["Subject"] = (
        f"[FactureScan] {len(files)} document(s) — {client_info['nom']} "
        f"({datetime.now().strftime('%d/%m/%Y %H:%M')})"
    )

    # ── Corps du mail ────────────────────────────────────────────────────────
    ocr_section = ""
    if ocr_results:
        ocr_section = "\n─── EXTRACTION OCR ────────────────────────────────\n"
        for r in ocr_results:
            ocr_section += f"\n📄 {r['filename']}\n"
            for k, v in r["fields"].items():
                ocr_section += f"   {k:<20}: {v}\n"

    drive_section = ""
    if drive_links:
        drive_section = "\n─── LIENS GOOGLE DRIVE ────────────────────────────\n"
        for lnk in drive_links:
            drive_section += f"  • {lnk['name']} → {lnk['url']}\n"

    body = f"""Bonjour,

Votre client a transmis {len(files)} document(s) via FactureScan Pro.

─── INFORMATIONS CLIENT ───────────────────────────
Nom / Société    : {client_info['nom']}
Email            : {client_info['email']}
Téléphone        : {client_info.get('telephone', 'Non renseigné')}
Type de document : {client_info['type_doc']}
Période          : {client_info.get('periode', 'Non renseignée')}
Note             : {client_info.get('note', 'Aucune')}
───────────────────────────────────────────────────
{ocr_section}{drive_section}
Fichiers joints  : {', '.join([f.name for f in files])}

─────────────────────────────────────────────────────
Envoyé automatiquement via FactureScan Pro
{config['cabinet_name']}
"""
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for f in files:
        f.seek(0)
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{f.name}"')
        msg.attach(part)

    with _build_smtp(config) as server:
        server.send_message(msg)


def send_confirmation_to_client(config: dict, client_info: dict, files: list, ocr_results: list, client_email: str = ""):
    """Envoie un accusé de réception stylisé au client."""
    if not client_info.get("email"):
        return

    msg = MIMEMultipart("alternative")
    msg["From"]    = config["smtp_user"]
    # Utiliser l'email détecté sur la facture, ou celui fourni manuellement
    recipient = client_email or client_info.get("email", "")
    if not recipient:
        return  # Pas d'email disponible → on n'envoie pas
    msg["To"]      = recipient
    msg["Subject"] = f"✅ Vos documents ont bien été reçus — {config['cabinet_name']}"

    file_list_html = "".join(
        f'<li style="padding:4px 0; color:#374151;">📄 {f.name}</li>'
        for f in files
    )

    ocr_html = ""
    if ocr_results:
        rows = ""
        for r in ocr_results:
            for k, v in r["fields"].items():
                rows += f"""
                <tr>
                  <td style="padding:6px 12px;color:#6b7280;font-size:13px;border-bottom:1px solid #f3f4f6;">{k}</td>
                  <td style="padding:6px 12px;font-weight:500;font-size:13px;border-bottom:1px solid #f3f4f6;">{v}</td>
                </tr>"""
        ocr_html = f"""
        <div style="margin:24px 0;">
          <p style="font-weight:600;margin-bottom:8px;color:#1a472a;">📊 Informations extraites automatiquement :</p>
          <table style="width:100%;border-collapse:collapse;background:#f9fafb;border-radius:6px;">
            {rows}
          </table>
        </div>"""

    html = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
    <tr><td align="center">
      <table width="560" style="background:#ffffff;border:1.5px solid #d4cfc6;border-radius:6px;overflow:hidden;box-shadow:3px 3px 0 #d4cfc6;">

        <!-- Header -->
        <tr><td style="background:#0d0d0d;padding:28px 36px;">
          <p style="margin:0;font-size:22px;font-weight:800;color:#f5f2eb;letter-spacing:-0.02em;">
            Facture<span style="color:#4ade80;">Scan</span> Pro
          </p>
          <p style="margin:4px 0 0;font-size:11px;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase;">
            {config['cabinet_name']}
          </p>
        </td></tr>

        <!-- Body -->
        <tr><td style="padding:32px 36px;">
          <h2 style="margin:0 0 8px;font-size:20px;color:#1a472a;">✅ Documents reçus avec succès</h2>
          <p style="color:#6b7280;margin-top:4px;">
            Bonjour <strong>{client_info['nom']}</strong>,
          </p>
          <p style="color:#374151;line-height:1.6;">
            Votre cabinet comptable <strong>{config['cabinet_name']}</strong> a bien reçu
            vos <strong>{len(files)} document(s)</strong> pour la période
            <strong>{client_info.get('periode','—')}</strong>.
          </p>

          <!-- Files -->
          <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:4px;padding:16px 20px;margin:20px 0;">
            <p style="margin:0 0 10px;font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;">
              Fichiers transmis
            </p>
            <ul style="margin:0;padding-left:18px;">{file_list_html}</ul>
          </div>

          {ocr_html}

          <p style="color:#6b7280;font-size:13px;line-height:1.6;margin-top:24px;">
            Votre comptable traitera ces documents prochainement.
            En cas de question, répondez directement à cet email.
          </p>
        </td></tr>

        <!-- Footer -->
        <tr><td style="padding:20px 36px;background:#f9fafb;border-top:1px solid #e5e7eb;">
          <p style="margin:0;font-size:11px;color:#9ca3af;text-align:center;">
            Envoyé via FactureScan Pro · {config['cabinet_name']}
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body></html>"""

    msg.attach(MIMEText(html, "html", "utf-8"))

    with _build_smtp(config) as server:
        server.send_message(msg)
