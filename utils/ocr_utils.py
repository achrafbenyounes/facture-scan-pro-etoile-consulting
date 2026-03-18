"""
OCR des factures — v7 extraction universelle.

Strategie :
  1. Google Vision / pdfminer / Tesseract → texte brut
  2. Extraction intelligente ligne par ligne
  3. Logique contextuelle : emetteur = bloc en haut a gauche,
     client = bloc apres "Client :" ou "Informations Client"
  4. Montants : recherche du plus grand TTC avec label,
     fallback sur le plus grand montant du document
  5. N° facture : validation stricte (doit contenir chiffres)
  6. Date : priorite a "date d'emission", ignore "echeance"
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


# ─────────────────────────────────────────────────────────────────────────────
# Extraction du texte brut
# ─────────────────────────────────────────────────────────────────────────────

def _google_vision_ocr(raw: bytes, api_key: str) -> str:
    b64 = base64.standard_b64encode(raw).decode("utf-8")
    payload = {
        "requests": [{
            "image": {"content": b64},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["fr", "en"]}
        }]
    }
    try:
        resp = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
            json=payload, timeout=25
        )
        if resp.status_code == 200:
            ann = resp.json()["responses"][0].get("fullTextAnnotation", {})
            return ann.get("text", "")
    except Exception:
        pass
    return ""

def _pdf_to_image(raw: bytes) -> bytes:
    try:
        import fitz
        pix = fitz.open(stream=raw, filetype="pdf")[0].get_pixmap(matrix=fitz.Matrix(2, 2))
        return pix.tobytes("png")
    except Exception:
        pass
    if PIL_OK:
        try:
            buf = io.BytesIO()
            Image.open(io.BytesIO(raw)).save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            pass
    return raw

def extract_text(filename: str, raw: bytes, api_key: str = "") -> tuple:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf" and PDFMINER_OK:
        try:
            t = pdf_extract_text(io.BytesIO(raw)) or ""
            if len(t.strip()) > 50:
                return t, "pdfminer"
        except Exception:
            pass
    if api_key:
        img = _pdf_to_image(raw) if ext == "pdf" else raw
        t   = _google_vision_ocr(img, api_key)
        if t.strip():
            return t, "google_vision"
    if PIL_OK and TESS_OK:
        try:
            img = Image.open(io.BytesIO(raw))
            w, h = img.size
            if w < 1200:
                img = img.resize((int(1200), int(h * 1200 / w)), Image.LANCZOS)
            try:
                t = pytesseract.image_to_string(img, lang="fra+eng") or ""
            except Exception:
                t = pytesseract.image_to_string(img) or ""
            if t.strip():
                return t, "tesseract"
        except Exception:
            pass
    return "", "none"


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ─────────────────────────────────────────────────────────────────────────────

def _clean_digits(s: str) -> str:
    return re.sub(r'[\s\.\-]', '', s) if s else ""

def _norm_amount(s: str) -> str:
    s = re.sub(r'\s', '', s)
    # "1 830,00" → "1830.00"
    s = s.replace(',', '.')
    # "1.830.00" → "1830.00"  (enlever les séparateurs de milliers)
    parts = s.split('.')
    if len(parts) > 2:
        s = ''.join(parts[:-1]) + '.' + parts[-1]
    return s

def _parse_amount(s: str) -> float:
    try:
        return float(_norm_amount(s))
    except Exception:
        return 0.0

def _lines(text: str) -> list:
    return [l.strip() for l in text.splitlines() if l.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Extraction SIRET / SIREN
# ─────────────────────────────────────────────────────────────────────────────

SIRET_RE = re.compile(
    r'(?:siret|siren|n[°o]?\s*siret|n[°o]?\s*siren)\s*[:\s]+(\d[\d\s\.]{12,17})',
    re.IGNORECASE
)
SIRET_RAW_RE = re.compile(r'\b(\d{3}[\s]?\d{3}[\s]?\d{3}[\s]?\d{5})\b')

def _extract_all_sirets(text: str) -> list:
    """Retourne tous les SIRET/SIREN trouvés dans le document."""
    results = []
    for m in SIRET_RE.finditer(text):
        clean = _clean_digits(m.group(1))
        if len(clean) >= 9 and clean not in results:
            results.append(clean[:14])
    if not results:
        for m in SIRET_RAW_RE.finditer(text):
            clean = _clean_digits(m.group(1))
            if clean not in results:
                results.append(clean)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Extraction des blocs Emetteur / Client
# ─────────────────────────────────────────────────────────────────────────────

# Mots qui déclenchent un bloc "client destinataire"
CLIENT_BLOCK_TRIGGERS = re.compile(
    r'^(?:informations?\s*client|adresse\s*(?:de\s*)?(?:facturation|livraison)|'
    r'factur[eé]\s*[àa]|bill\s*to|destinataire|client\s*[:\-]|'
    r'nom\s*[:\-]|acheteur|titulaire\s*du\s*contrat|titulaire\s*[:\-]|'
    r'votre\s*contrat|contract\s*holder)',
    re.IGNORECASE
)

# Mots à ignorer comme nom de société
IGNORE_NAMES = {
    'FACTURE', 'INVOICE', 'DEVIS', 'BON DE COMMANDE', 'AVOIR',
    'DATE', 'TOTAL', 'MONTANT', 'ADRESSE', 'CLIENT', 'FOURNISSEUR',
    'SIRET', 'SIREN', 'TVA', 'IBAN', 'BIC', 'TELEPHONE', 'EMAIL',
    'DESCRIPTION', 'QUANTITE', 'PRIX', 'REFERENCE', 'NOTE', 'PAGE',
}

def _is_company_name(line: str) -> bool:
    """Heuristique : cette ligne ressemble-t-elle à un nom de société ?"""
    line = line.strip()
    if len(line) < 3 or len(line) > 80:
        return False
    # Exclure les lignes qui commencent par un chiffre
    if line[0].isdigit():
        return False
    # Exclure les lignes avec des caractères URL/email
    if '@' in line or '/' in line or 'http' in line.lower():
        return False
    # Exclure si c'est un mot-clé connu
    if line.upper().strip('.,:-') in IGNORE_NAMES:
        return False
    # Doit contenir au moins une lettre
    if not re.search(r'[A-Za-zÀ-ÿ]', line):
        return False
    # Bonus si tout en majuscules ou contient un mot société
    has_caps   = line == line.upper() and len(line) > 3
    has_suffix = bool(re.search(
        r'\b(SARL|SAS|SA|EURL|SCI|SNC|SASU|CONSULTING|SERVICES|'
        r'GROUP|HOLDING|ENTREPRISE|SOCIETE|COMPANY|LTD|GMBH|INC)\b',
        line, re.IGNORECASE
    ))
    has_upper_start = line[0].isupper()
    return has_caps or has_suffix or has_upper_start

def _clean_company_name(name: str) -> str:
    """Nettoie un nom de société : retire adresse, N° TVA, etc. après le nom."""
    # Couper au premier tiret/virgule suivi d'adresse ou chiffre postal
    name = re.split(r'\s*[–\-,]\s*(?:\d{2,}|rue|av|all[eé]e|str|stra|blvd|road)',
                    name, flags=re.IGNORECASE)[0]
    # Retirer les mentions légales courantes
    name = re.split(r'\s*–\s*', name)[0]
    name = re.split(r'\s*-\s+(?=[A-Z][a-z])', name)[0]  # "GmbH - Rue..."
    return name.strip().rstrip('.,;-–')

def _extract_emetteur_and_client(text: str) -> tuple:
    """
    Retourne (emetteur: str, client: str).
    Gère : factures FR, DE, EN, e-commerce, B2B.
    """
    lines = _lines(text)
    emetteur = ""
    client   = ""

    # ── Chercher le bloc client ───────────────────────────────────────────────
    client_block_start = -1
    for i, line in enumerate(lines):
        if CLIENT_BLOCK_TRIGGERS.match(line):
            client_block_start = i
            break

    if client_block_start >= 0:
        # Émetteur = première ligne significative AVANT le bloc client
        for line in lines[:client_block_start]:
            if _is_company_name(line):
                emetteur = _clean_company_name(line)
                break

        # Client = lignes APRÈS le trigger
        # Cas 1 : "Nom : Société ABC" explicite
        # Cas 2 : Prénom + Nom sur 2 lignes (factures e-commerce)
        client_lines = lines[client_block_start + 1: client_block_start + 10]
        for i, line in enumerate(client_lines):
            nom_match = re.match(r'^nom\s*[:\-]\s*(.+)', line, re.IGNORECASE)
            if nom_match:
                candidate = nom_match.group(1).strip()
                if _is_company_name(candidate):
                    client = candidate
                    break
            elif _is_company_name(line):
                # Cas e-commerce : prénom seul sur une ligne, nom sur la suivante
                next_line = client_lines[i+1] if i+1 < len(client_lines) else ""
                if (next_line and re.match(r'^[A-ZÀ-Ÿ][A-ZÀ-Ÿ\s]{1,30}$', next_line)
                        and not _is_address_line(next_line)):
                    client = line + " " + next_line
                else:
                    client = line
                break
    else:
        # Pas de section client explicite
        for line in lines[:15]:
            if _is_company_name(line):
                if not emetteur:
                    emetteur = _clean_company_name(line)
                elif not client and line != emetteur:
                    client = line
                    break

    if not emetteur and lines:
        emetteur = _clean_company_name(lines[0])

    return emetteur.strip(), client.strip()

def _is_address_line(line: str) -> bool:
    """Détecte si une ligne est une adresse, service ou mention légale."""
    return bool(re.search(
        r'\b(rue|avenue|all[eé]e|boulevard|impasse|chemin|route|place|'
        r'cit[eé]|r[eé]sidence|france|paris|lyon|marseille|toulouse|'
        r'\d{5}|cedex|bp\s*\d|tour\s+[a-z]|service\s+client|'
        r'cs\s*\d|tsa\s*\d|la\s+d[eé]fense|cedex)',
        line, re.IGNORECASE
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Extraction date (emission uniquement, pas echeance)
# ─────────────────────────────────────────────────────────────────────────────

DATE_PATTERN = re.compile(r'\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\b')
ECHEANCE_RE  = re.compile(r'[eé]ch[eé]ance|due\s*date|deadline|expir', re.IGNORECASE)
EMISSION_RE  = re.compile(
    r'[eé]mission|[eé]mit|date\s*(?:de\s*)?(?:la\s*)?facture|'
    r'date\s*du\s*document|invoice\s*date|issued',
    re.IGNORECASE
)

def _extract_invoice_date(text: str) -> str:
    """
    Retourne la date d'émission au format JJ/MM/AAAA.
    Ignore les dates d'échéance.
    """
    lines = _lines(text)

    # Passe 1 : ligne contenant un label "émission" + une date
    for line in lines:
        if EMISSION_RE.search(line) and not ECHEANCE_RE.search(line):
            m = DATE_PATTERN.search(line)
            if m:
                return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"

    # Passe 2 : ligne contenant "date" mais PAS "échéance"
    for line in lines:
        if re.search(r'\bdate\b', line, re.IGNORECASE) and not ECHEANCE_RE.search(line):
            m = DATE_PATTERN.search(line)
            if m:
                return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"

    # Passe 3 : première date trouvée dans le document
    m = DATE_PATTERN.search(text)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Extraction N° de facture
# ─────────────────────────────────────────────────────────────────────────────

INV_NUM_RE = re.compile(
    r'(?:n[°o°ᵒ]?\s*(?:de\s*)?facture|facture\s*n[°o°ᵒ]?|'
    r'invoice\s*(?:no\.?|n[°o°ᵒ]?)?|r[eé]f(?:[eé]rence)?\.?\s*(?:facture)?|'
    r'num[eé]ro\s*(?:de\s*)?(?:facture)?)'
    r'\s*[:\s#–\-]*([A-Z0-9][A-Z0-9\-\/\.\_]{2,25})',
    re.IGNORECASE
)

INVALID_NUM = re.compile(
    r'^(date|facture|client|total|montant|adresse|'
    r'tel|email|siret|siren|tva|iban|bic|page|ref)$',
    re.IGNORECASE
)

def _extract_invoice_number(text: str) -> str:
    for m in INV_NUM_RE.finditer(text):
        candidate = m.group(1).strip().rstrip('.,;:')
        # Doit contenir au moins un chiffre
        if not re.search(r'\d', candidate):
            continue
        # Longueur raisonnable
        if len(candidate) < 3 or len(candidate) > 30:
            continue
        # Pas un mot-clé
        if INVALID_NUM.match(candidate):
            continue
        return candidate
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Extraction montants
# ─────────────────────────────────────────────────────────────────────────────

AMOUNT_RE = re.compile(r'(\d[\d\s]*[.,]\d{2})')

TTC_LABELS = re.compile(
    r'total\s*ttc|net\s*[àa]\s*payer|total\s*[àa]\s*payer|'
    r'montant\s*total|total\s*(?:toutes\s*taxes|TTC)',
    re.IGNORECASE
)
HT_LABELS = re.compile(
    r'total\s*ht|sous[\s\-]?total\s*ht|total\s*hors\s*taxe|'
    r'montant\s*ht|base\s*ht',
    re.IGNORECASE
)
TVA_LABELS = re.compile(
    r'(?:total\s*)?tva\s*(?:\(\s*\d+\s*%\s*\))?|'
    r'montant\s*(?:de\s*la\s*)?tva',
    re.IGNORECASE
)

def _extract_amounts(text: str) -> dict:
    result = {}
    lines  = _lines(text)

    ttc_candidates = []
    ht_candidates  = []
    tva_candidates = []

    for line in lines:
        amounts_in_line = AMOUNT_RE.findall(line)
        if not amounts_in_line:
            continue

        if TTC_LABELS.search(line):
            # Prendre le plus grand montant de la ligne
            vals = [(a, _parse_amount(a)) for a in amounts_in_line]
            best = max(vals, key=lambda x: x[1])
            if best[1] > 0:
                ttc_candidates.append(best)

        elif HT_LABELS.search(line):
            vals = [(a, _parse_amount(a)) for a in amounts_in_line]
            best = max(vals, key=lambda x: x[1])
            if best[1] > 0:
                ht_candidates.append(best)

        elif TVA_LABELS.search(line):
            vals = [(a, _parse_amount(a)) for a in amounts_in_line]
            best = max(vals, key=lambda x: x[1])
            if best[1] > 0:
                tva_candidates.append(best)

    # TTC = le plus grand parmi les candidats TTC
    if ttc_candidates:
        best = max(ttc_candidates, key=lambda x: x[1])
        result["montant_ttc"] = _norm_amount(best[0]) + " €"

    # HT = le plus grand parmi les candidats HT
    if ht_candidates:
        best = max(ht_candidates, key=lambda x: x[1])
        result["montant_ht"] = _norm_amount(best[0]) + " €"

    # TVA = le plus grand parmi les candidats TVA (récapitulatif)
    if tva_candidates:
        best = max(tva_candidates, key=lambda x: x[1])
        result["tva"] = _norm_amount(best[0]) + " €"

    # Fallback TTC : plus grand montant € du document entier
    if "montant_ttc" not in result:
        all_amounts = re.findall(r'(\d[\d\s]*[.,]\d{2})\s*(?:€|EUR)', text, re.IGNORECASE)
        if all_amounts:
            try:
                best = max(all_amounts, key=_parse_amount)
                result["montant_ttc"] = _norm_amount(best) + " €"
            except Exception:
                pass

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Extraction email et téléphone
# ─────────────────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b')
PHONE_RE = re.compile(
    r'(?:t[ée]l[ée]?(?:phone)?|tel|mob(?:ile)?|portable|fax)?'
    r'\s*[:\.\-]?\s*((?:\+33|0033|0)\s*[1-9](?:[\s.\-]?\d{2}){4})',
    re.IGNORECASE
)

def _extract_contacts(text: str) -> dict:
    result = {}
    emails = [e for e in EMAIL_RE.findall(text)
              if not any(x in e.lower() for x in ['noreply','no-reply','donotreply'])]
    phones = [m.group(1).strip() for m in PHONE_RE.finditer(text)]

    if emails:
        result["email"] = emails[0]
    if len(emails) > 1:
        result["email_client"] = emails[1]
    if phones:
        result["telephone"] = phones[0]
    if len(phones) > 1:
        result["telephone_client"] = phones[1]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Extraction IBAN / BIC
# ─────────────────────────────────────────────────────────────────────────────

IBAN_RE = re.compile(r'\b([A-Z]{2}\d{2}[A-Z0-9\s]{11,30})\b')
BIC_RE  = re.compile(r'\bBIC\s*[:\s]*([A-Z]{6}[A-Z0-9]{2,11})\b', re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# Assemblage final
# ─────────────────────────────────────────────────────────────────────────────

def parse_fields(text: str) -> dict:
    if not text.strip():
        return {}

    fields = {}

    # Emetteur et client
    emetteur, client = _extract_emetteur_and_client(text)
    if emetteur:
        fields["company_names"] = [emetteur]
    if client:
        fields.setdefault("company_names", [])
        if client not in fields["company_names"]:
            fields["company_names"].append(client)

    # SIRET
    sirets = _extract_all_sirets(text)
    if sirets:
        fields["siret"] = sirets[0]
        fields["siren"] = sirets[0][:9]
    if len(sirets) > 1:
        fields["siret_client"] = sirets[1]

    # Contacts
    contacts = _extract_contacts(text)
    fields.update(contacts)

    # Date
    date = _extract_invoice_date(text)
    if date:
        fields["date_facture"] = date

    # N° facture
    num = _extract_invoice_number(text)
    if num:
        fields["numero_facture"] = num

    # Montants
    amounts = _extract_amounts(text)
    fields.update(amounts)

    # IBAN / BIC
    m = IBAN_RE.search(text)
    if m:
        fields["iban"] = m.group(1).strip()
    m = BIC_RE.search(text)
    if m:
        fields["bic"] = m.group(1).strip()

    return fields


# ─────────────────────────────────────────────────────────────────────────────
# Conversion date en tuple
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entree principal
# ─────────────────────────────────────────────────────────────────────────────

def run_ocr(uploaded_file, api_key: str = "") -> dict:
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

    text, method = extract_text(uploaded_file.name, raw, api_key)

    if not text.strip():
        return {
            "filename": uploaded_file.name, "text": "", "fields": {},
            "available": False,
            "message": "Aucun texte extrait. Vérifiez GOOGLE_VISION_API_KEY.",
            "invoice_date": None, "company_names": [], "siret": "", "siren": "",
            "client_email": "", "client_phone": "", "ocr_method": method,
        }

    parsed        = parse_fields(text)
    company_names = parsed.get("company_names", [])
    siret         = parsed.get("siret", "")
    siren         = parsed.get("siren", "")
    client_email  = parsed.get("email", "")
    client_phone  = parsed.get("telephone", "")
    date_str      = parsed.get("date_facture", "")
    invoice_date  = _date_tuple(date_str)

    # Champs affiches dans l'UI
    display = {}
    if company_names:
        display["Emetteur"]      = company_names[0]
    if len(company_names) > 1:
        display["Client"]        = company_names[1]
    if siret:
        display["SIRET emetteur"]= siret
    if parsed.get("siret_client"):
        display["SIRET client"]  = parsed["siret_client"]
    if parsed.get("numero_facture"):
        display["N° Facture"]    = parsed["numero_facture"]
    if date_str:
        display["Date emission"] = date_str
    if parsed.get("montant_ht"):
        display["Montant HT"]    = parsed["montant_ht"]
    if parsed.get("tva"):
        display["TVA"]           = parsed["tva"]
    if parsed.get("montant_ttc"):
        display["Montant TTC"]   = parsed["montant_ttc"]
    if parsed.get("iban"):
        display["IBAN"]          = parsed["iban"]
    if parsed.get("bic"):
        display["BIC"]           = parsed["bic"]
    if client_email:
        display["Email"]         = client_email
    if parsed.get("email_client"):
        display["Email client"]  = parsed["email_client"]
    if client_phone:
        display["Telephone"]     = client_phone
    if parsed.get("telephone_client"):
        display["Tel. client"]   = parsed["telephone_client"]

    return {
        "filename":      uploaded_file.name,
        "text":          text,
        "available":     True,
        "message":       f"OK ({method}) — {len(display)} champs",
        "fields":        display,
        "invoice_date":  invoice_date,
        "company_names": company_names,
        "siret":         siret,
        "siren":         siren,
        "client_email":  client_email,
        "client_phone":  client_phone,
        "ocr_method":    method,
    }