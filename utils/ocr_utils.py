"""
OCR des factures — v5 Google Vision API.

Fonctionne partout : Windows local + Streamlit Cloud.
100% gratuit jusqu'à 1000 images/mois.
Zéro installation système requise.

Ordre de priorité :
  1. PDF natif    → pdfminer (texte déjà présent, zéro quota)
  2. Google Vision API → images et PDF scannés
  3. Tesseract    → fallback si installé localement
"""

import re
import io
import base64
import json
import requests

try:
    from pdfminer.high_level import extract_text as pdf_extract_text
    PDFMINER_OK = True
except ImportError:
    PDFMINER_OK = False

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import pytesseract
    TESS_OK = True
except ImportError:
    TESS_OK = False


# ────────────────────────────────────────────────────────────────────────────
# Google Vision API
# ────────────────────────────────────────────────────────────────────────────

def _google_vision_ocr(raw: bytes, api_key: str) -> str:
    """
    Envoie l'image à Google Vision API et retourne le texte extrait.
    Gratuit jusqu'à 1000 requêtes/mois.
    """
    b64 = base64.standard_b64encode(raw).decode("utf-8")

    payload = {
        "requests": [{
            "image": {"content": b64},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1}],
            "imageContext": {"languageHints": ["fr", "en"]}
        }]
    }

    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"

    try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            annotation = data["responses"][0].get("fullTextAnnotation", {})
            return annotation.get("text", "")
        else:
            return ""
    except Exception:
        return ""


def _pdf_to_image_bytes(raw: bytes) -> bytes:
    """Convertit la première page d'un PDF en image PNG pour Google Vision."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(stream=raw, filetype="pdf")
        page = doc[0]
        mat = fitz.Matrix(2, 2)  # zoom x2 pour meilleure qualité
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    except ImportError:
        pass

    # Fallback PIL si pymupdf absent
    if PIL_OK:
        try:
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            pass
    return raw


# ────────────────────────────────────────────────────────────────────────────
# Extraction texte depuis fichier
# ────────────────────────────────────────────────────────────────────────────

def extract_text(filename: str, raw: bytes, api_key: str = "") -> tuple[str, str]:
    """
    Retourne (texte_extrait, methode_utilisée).
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Étape 1 : PDF natif (texte déjà présent → zéro quota)
    if ext == "pdf" and PDFMINER_OK:
        text = ""
        try:
            text = pdf_extract_text(io.BytesIO(raw)) or ""
        except Exception:
            pass
        if len(text.strip()) > 50:
            return text, "pdfminer"

    # Étape 2 : Google Vision (image ou PDF scanné)
    if api_key:
        if ext == "pdf":
            img_bytes = _pdf_to_image_bytes(raw)
        else:
            img_bytes = raw
        text = _google_vision_ocr(img_bytes, api_key)
        if text.strip():
            return text, "google_vision"

    # Étape 3 : Tesseract (fallback local)
    if PIL_OK and TESS_OK:
        try:
            img = Image.open(io.BytesIO(raw))
            w, h = img.size
            if w < 1200:
                scale = 1200 / w
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            try:
                text = pytesseract.image_to_string(img, lang="fra+eng") or ""
            except Exception:
                text = pytesseract.image_to_string(img) or ""
            if text.strip():
                return text, "tesseract"
        except Exception:
            pass

    return "", "none"


# ────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ────────────────────────────────────────────────────────────────────────────

SIRET_LABEL_RE = re.compile(
    r'(?:siret|siren)\s*[:\s]+(\d[\d\s\.]{12,17})', re.IGNORECASE)
SIRET_RAW_RE   = re.compile(r'\b(\d{3}[\s\.]?\d{3}[\s\.]?\d{3}[\s\.]?\d{5})\b')
SIREN_RAW_RE   = re.compile(r'\b(\d{3}[\s\.]?\d{3}[\s\.]?\d{3})\b')

EMAIL_RE  = re.compile(r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b')
PHONE_RE  = re.compile(r'\b((?:0[1-9]|\+33\s?[1-9])[\s.\-]?(?:\d[\s.\-]?){8}\d)\b')

DATE_LABEL_RE = re.compile(
    r'(?:date|émission|facture\s*du)\s*[:\s]*(\d{1,2}[/.\-]\d{1,2}[/.\-]20\d{2})',
    re.IGNORECASE)
DATE_RAW_RE   = re.compile(r'\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\b')

TTC_RE = re.compile(
    r'(?:total\s*ttc|net\s*[àa]\s*payer|total\s*[àa]\s*payer)\s*[:\s]*'
    r'([0-9\s]{1,8}[.,][0-9]{2})\s*(?:€|eur)?',
    re.IGNORECASE)
HT_RE  = re.compile(
    r'(?:total\s*ht|sous[\s\-]?total\s*ht)\s*[:\s]*([0-9\s]{1,8}[.,][0-9]{2})\s*(?:€|eur)?',
    re.IGNORECASE)
TVA_RE = re.compile(
    r'tva\s*(?:\(\s*\d+\s*%\s*\))?\s*[:\s]*([0-9\s]{1,7}[.,][0-9]{2})\s*(?:€|eur)?',
    re.IGNORECASE)

INVOICE_NUM_RE = re.compile(
    r'(?:facture\s*n[°o]?|n[°o]\s*(?:de\s*)?facture|n[°o])\s*[:\s#]*'
    r'([A-Z0-9][\w\-\/\.]{2,20})',
    re.IGNORECASE)

IBAN_RE = re.compile(r'\b(FR\d{2}[\d\s]{20,30})\b', re.IGNORECASE)
BIC_RE  = re.compile(r'\bBIC\s*[:\s]*([A-Z]{6}[A-Z0-9]{2,5})\b', re.IGNORECASE)

ALLCAPS_RE   = re.compile(r'^([A-ZÀ-Ÿ][A-ZÀ-Ÿ0-9\s\-&\.]{3,50})$')
COMPANY_RE   = re.compile(
    r'^([A-ZÀ-Ÿ][A-Za-zÀ-ÿ0-9\s\-&\.,]{3,60}'
    r'(?:SARL|SAS|SA|EURL|SCI|SNC|SASU|CONSULTING|SERVICES|GROUP|HOLDING)?)$')


def _clean_num(s: str) -> str:
    return re.sub(r'[\s\.]', '', s) if s else ""

def _normalize_amount(s: str) -> str:
    return re.sub(r'\s', '', s).replace(',', '.') if s else ""


# ────────────────────────────────────────────────────────────────────────────
# Extraction structurée depuis texte brut
# ────────────────────────────────────────────────────────────────────────────

def parse_fields(text: str) -> dict:
    """Extrait tous les champs structurés depuis le texte brut."""
    if not text.strip():
        return {}

    fields = {}
    text_lower = text.lower()

    # SIRET / SIREN
    m = SIRET_LABEL_RE.search(text)
    if m:
        raw = _clean_num(m.group(1))
        if len(raw) >= 14:
            fields["siret"] = raw[:14]
            fields["siren"] = raw[:9]
        elif len(raw) >= 9:
            fields["siren"] = raw[:9]
    else:
        m = SIRET_RAW_RE.search(text)
        if m:
            raw = _clean_num(m.group(1))
            fields["siret"] = raw
            fields["siren"] = raw[:9]

    # Email
    emails = EMAIL_RE.findall(text)
    good = [e for e in emails if not any(x in e.lower()
            for x in ['noreply', 'no-reply', 'donotreply', 'mailer'])]
    if good:
        fields["email"] = good[0]

    # Téléphone
    m = PHONE_RE.search(text)
    if m:
        fields["telephone"] = m.group(1).strip()

    # Date facture
    m = DATE_LABEL_RE.search(text)
    if m:
        fields["date_facture"] = m.group(1)
    else:
        m = DATE_RAW_RE.search(text)
        if m:
            fields["date_facture"] = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"

    # N° facture
    m = INVOICE_NUM_RE.search(text)
    if m:
        fields["numero_facture"] = m.group(1).strip()

    # Montants
    m = TTC_RE.search(text)
    if m:
        fields["montant_ttc"] = _normalize_amount(m.group(1)) + " €"
    else:
        # Plus grand montant € comme fallback
        amounts = re.findall(r'(\d[\d\s]*[.,]\d{2})\s*(?:€|EUR)', text, re.IGNORECASE)
        if amounts:
            try:
                best = max(amounts, key=lambda x: float(_normalize_amount(x)))
                fields["montant_ttc"] = _normalize_amount(best) + " €"
            except Exception:
                pass

    m = HT_RE.search(text)
    if m:
        fields["montant_ht"] = _normalize_amount(m.group(1)) + " €"

    m = TVA_RE.search(text)
    if m:
        fields["tva"] = _normalize_amount(m.group(1)) + " €"

    # IBAN / BIC
    m = IBAN_RE.search(text)
    if m:
        fields["iban"] = m.group(1).strip()

    m = BIC_RE.search(text)
    if m:
        fields["bic"] = m.group(1).strip()

    # Noms de sociétés (20 premières lignes)
    company_names = []
    lines = [l.strip() for l in text.splitlines() if l.strip()][:25]
    for line in lines:
        if ALLCAPS_RE.match(line) and len(line) > 4:
            company_names.append(line)
        elif COMPANY_RE.match(line):
            company_names.append(line)

    # Après "Client :"
    m = re.search(r'(?:client|facturé\s*à)\s*[:\s]+([^\n]{4,60})', text, re.IGNORECASE)
    if m:
        company_names.append(m.group(1).strip())

    seen, unique = set(), []
    for n in company_names:
        key = n.upper()
        if key not in seen:
            seen.add(key)
            unique.append(n)
    fields["company_names"] = unique[:5]

    return fields


# ────────────────────────────────────────────────────────────────────────────
# Conversion date en tuple
# ────────────────────────────────────────────────────────────────────────────

def _date_tuple(date_str: str):
    if not date_str:
        return None
    m = re.match(r'(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})', date_str)
    if m:
        try:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
        except Exception:
            pass
    return None


# ────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ────────────────────────────────────────────────────────────────────────────

def run_ocr(uploaded_file, api_key: str = "") -> dict:
    """
    Analyse complète d'une facture uploadée.

    Args:
        uploaded_file : st.UploadedFile
        api_key       : clé Google Vision API (depuis secrets.toml)

    Retourne un dict complet avec tous les champs extraits.
    """
    try:
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception as e:
        return {
            "filename": uploaded_file.name, "text": "", "fields": {},
            "available": False, "message": str(e),
            "invoice_date": None, "company_names": [], "siret": "", "siren": "",
            "client_email": "", "client_phone": "", "ocr_method": "error",
        }

    # Extraction texte
    text, method = extract_text(uploaded_file.name, raw, api_key)

    if not text.strip():
        return {
            "filename": uploaded_file.name, "text": "", "fields": {},
            "available": False,
            "message": (
                "❌ Aucun texte extrait. " +
                ("Vérifiez votre clé GOOGLE_VISION_API_KEY." if api_key else
                 "Configurez GOOGLE_VISION_API_KEY dans secrets.toml.")
            ),
            "invoice_date": None, "company_names": [], "siret": "", "siren": "",
            "client_email": "", "client_phone": "", "ocr_method": method,
        }

    # Extraction structurée
    parsed       = parse_fields(text)
    company_names = parsed.get("company_names", [])
    siret        = parsed.get("siret", "")
    siren        = parsed.get("siren", "")
    client_email = parsed.get("email", "")
    client_phone = parsed.get("telephone", "")
    date_str     = parsed.get("date_facture", "")
    invoice_date = _date_tuple(date_str)

    # Champs affichés dans l'UI
    display_fields = {}
    if company_names:
        display_fields["Émetteur"]       = company_names[0]
    if len(company_names) > 1:
        display_fields["Destinataire"]   = company_names[1]
    if siret:
        display_fields["SIRET"]          = siret
    if siren and not siret:
        display_fields["SIREN"]          = siren
    if parsed.get("numero_facture"):
        display_fields["N° Facture"]     = parsed["numero_facture"]
    if date_str:
        display_fields["Date"]           = date_str
    if parsed.get("montant_ht"):
        display_fields["Montant HT"]     = parsed["montant_ht"]
    if parsed.get("tva"):
        display_fields["TVA"]            = parsed["tva"]
    if parsed.get("montant_ttc"):
        display_fields["Montant TTC"]    = parsed["montant_ttc"]
    if parsed.get("iban"):
        display_fields["IBAN"]           = parsed["iban"]
    if parsed.get("bic"):
        display_fields["BIC"]            = parsed["bic"]
    if client_email:
        display_fields["Email"]          = client_email
    if client_phone:
        display_fields["Téléphone"]      = client_phone

    return {
        "filename":     uploaded_file.name,
        "text":         text,
        "available":    True,
        "message":      f"✅ {method} — {len(display_fields)} champs extraits",
        "fields":       display_fields,
        "invoice_date": invoice_date,
        "company_names": company_names,
        "siret":        siret,
        "siren":        siren,
        "client_email": client_email,
        "client_phone": client_phone,
        "ocr_method":   method,
    }
