"""
FactureScan Pro — Moteur IDP v8 (Intelligent Document Processing)

Architecture multicouche :
  Couche 1 — PDF natif : PyMuPDF (fitz) > pdfplumber > pdfminer
  Couche 2 — Image/scan : Google Vision API
  Couche 3 — Fallback   : Tesseract local

Classification automatique des 10 types de documents comptables FR :
  facture_achat | facture_vente | avis_echeance | releve_bancaire |
  note_frais | bulletin_salaire | bon_commande | avoir | devis | contrat

Extraction universelle :
  - Emetteur / Client / Titulaire
  - Tous SIRET/SIREN présents
  - Tous emails et téléphones
  - Date emission (pas echéance)
  - N° document (facture, commande, contrat...)
  - Montants : HT, TVA, TTC, Remise
  - IBAN/BIC (FR, DE, GB, ES, IT, BE, NL...)
  - Référence client / commande
  - Conditions de paiement
  - Mode de paiement
"""

import re
import io
import base64
import json
import requests
from datetime import datetime

# ── PDF engines (ordre de priorité) ─────────────────────────────────────────
try:
    import fitz  # PyMuPDF — le plus précis pour les financiers
    PYMUPDF_OK = True
except ImportError:
    PYMUPDF_OK = False

try:
    import pdfplumber  # Excellent pour les tableaux
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    PDFMINER_OK = True
except ImportError:
    PDFMINER_OK = False

# ── Image engines ────────────────────────────────────────────────────────────
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
# EXTRACTION DE TEXTE BRUT
# ─────────────────────────────────────────────────────────────────────────────

def _extract_pdf_pymupdf(raw: bytes) -> str:
    """PyMuPDF — meilleur pour les PDF financiers structurés."""
    if not PYMUPDF_OK:
        return ""
    try:
        doc  = fitz.open(stream=raw, filetype="pdf")
        text = ""
        for page in doc:
            # Extraction avec préservation du layout (colonnes, tableaux)
            text += page.get_text("text") + "\n"
        doc.close()
        return text
    except Exception:
        return ""

def _extract_pdf_pdfplumber(raw: bytes) -> str:
    """pdfplumber — excellent pour les PDF avec tableaux (relevés bancaires)."""
    if not PDFPLUMBER_OK:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            parts = []
            for page in pdf.pages:
                # Texte normal
                t = page.extract_text() or ""
                parts.append(t)
                # Tables extraites et converties en texte
                for table in page.extract_tables():
                    for row in table:
                        if row:
                            row_str = " | ".join(str(c) if c else "" for c in row)
                            parts.append(row_str)
            return "\n".join(parts)
    except Exception:
        return ""

def _extract_pdf_pdfminer(raw: bytes) -> str:
    """pdfminer — fallback fiable."""
    if not PDFMINER_OK:
        return ""
    try:
        return pdfminer_extract(io.BytesIO(raw)) or ""
    except Exception:
        return ""

def _extract_pdf_image_stream(raw: bytes, page_num: int = 0) -> bytes:
    """
    Extrait l'image embarquée depuis le stream PDF et l'upscale a 300 DPI.
    Fonctionne sans ghostscript ni wand — pdfplumber + Pillow uniquement.
    L'upscale x2 est critique : les PDF images sont souvent a 150 DPI,
    trop faible pour Google Vision (recommande 300+ DPI).
    """
    if not PDFPLUMBER_OK or not PIL_OK:
        return b""
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            if page_num >= len(pdf.pages):
                return b""
            imgs = pdf.pages[page_num].images
            if not imgs:
                return b""
            img_info = imgs[0]
            stream   = img_info.get("stream")
            if stream is None:
                return b""
            raw_data = stream.get_data()
            w, h     = img_info["srcsize"]
            cs       = str(img_info.get("colorspace", ""))
            if "Gray" in cs or img_info.get("imagemask"):
                mode, bpp = "L", 1
            elif "CMYK" in cs:
                mode, bpp = "CMYK", 4
            else:
                mode, bpp = "RGB", 3
            expected = w * h * bpp
            if len(raw_data) < int(expected * 0.8):
                return b""
            img = Image.frombytes(mode, (w, h), raw_data[:expected])
            if mode == "CMYK":
                img = img.convert("RGB")

            # Upscale a 300 DPI si image trop petite (< 2000px de large)
            # Google Vision recommande 300 DPI minimum pour un bon OCR
            if w < 2000:
                scale = max(2.0, 2480 / w)  # Cible 2480px (300 DPI pour A4)
                new_w = int(w * scale)
                new_h = int(h * scale)
                img = img.resize((new_w, new_h), Image.LANCZOS)
                # Ameliorer le contraste pour l'OCR
                try:
                    from PIL import ImageEnhance
                    img = ImageEnhance.Contrast(img).enhance(1.3)
                    img = ImageEnhance.Sharpness(img).enhance(1.5)
                except Exception:
                    pass

            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            buf.seek(0)
            return buf.read()
    except Exception:
        return b""


def _pdf_to_png(raw: bytes) -> bytes:
    """
    Convertit la 1ere page PDF en PNG.
    Ordre : PyMuPDF → stream direct → pdfplumber.to_image → bytes bruts.
    """
    # 1. PyMuPDF — qualite maximale
    if PYMUPDF_OK:
        try:
            doc = fitz.open(stream=raw, filetype="pdf")
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
            png = pix.tobytes("png")
            doc.close()
            if png: return png
        except Exception:
            pass

    # 2. Extraction directe du stream image — sans dependances systeme
    png = _extract_pdf_image_stream(raw, 0)
    if png: return png

    # 3. pdfplumber.to_image — necessite ghostscript (peut echouer)
    if PDFPLUMBER_OK:
        try:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                buf = io.BytesIO()
                pdf.pages[0].to_image(resolution=200).save(buf, format="PNG")
                buf.seek(0)
                png = buf.read()
                if png: return png
        except Exception:
            pass

    # 4. Fallback : PDF brut (Google Vision l'accepte parfois)
    return raw

def _google_vision(raw: bytes, api_key: str, is_pdf: bool = False) -> str:
    """Google Vision API — OCR haute précision (images ET PDFs scannés)."""
    b64 = base64.standard_b64encode(raw).decode()
    try:
        if is_pdf:
            # Google Vision Cloud Vision async n'est pas dispo ici
            # → on utilise le mode image standard en envoyant le PDF tel quel
            # (Google Vision accepte les PDF mono-page en base64)
            payload = {"requests": [{
                "image": {"content": b64},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                "imageContext": {
                    "languageHints": ["fr", "en", "de", "es", "it"],
                }
            }]}
        else:
            payload = {"requests": [{
                "image": {"content": b64},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                "imageContext": {"languageHints": ["fr", "en", "de", "es", "it"]}
            }]}

        r = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
            json=payload,
            timeout=30
        )
        if r.status_code == 200:
            resp = r.json()["responses"][0]
            ann  = resp.get("fullTextAnnotation", {})
            return ann.get("text", "")
        else:
            return ""
    except Exception:
        pass
    return ""


def _pdf_page_to_png(raw: bytes, page_num: int = 0) -> bytes:
    """
    Convertit une page PDF en PNG pour l'OCR.
    Utilise PyMuPDF si disponible, sinon retourne les bytes bruts du PDF.
    """
    if PYMUPDF_OK:
        try:
            doc = fitz.open(stream=raw, filetype="pdf")
            if page_num < len(doc):
                pix = doc[page_num].get_pixmap(matrix=fitz.Matrix(3.0, 3.0))
                png = pix.tobytes("png")
                doc.close()
                return png
            doc.close()
        except Exception:
            pass
    # Fallback : retourner le PDF tel quel (Google Vision l'accepte)
    return raw

def _tesseract(raw: bytes) -> str:
    """Tesseract — fallback local."""
    if not PIL_OK or not TESS_OK:
        return ""
    try:
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if w < 1500:
            img = img.resize((int(1500), int(h * 1500 / w)), Image.LANCZOS)
        try:
            return pytesseract.image_to_string(img, lang="fra+eng") or ""
        except Exception:
            return pytesseract.image_to_string(img) or ""
    except Exception:
        return ""

def extract_text(filename: str, raw: bytes, api_key: str = "") -> tuple:
    """
    Extrait le texte brut avec la meilleure méthode disponible.
    Retourne (texte, méthode_utilisée).
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        # Essai 1 : PyMuPDF (plus précis)
        t = _extract_pdf_pymupdf(raw)
        if len(t.strip()) > 80:
            return t, "pymupdf"
        # Essai 2 : pdfplumber (meilleur pour tableaux)
        t = _extract_pdf_pdfplumber(raw)
        if len(t.strip()) > 80:
            return t, "pdfplumber"
        # Essai 3 : pdfminer
        t = _extract_pdf_pdfminer(raw)
        if len(t.strip()) > 80:
            return t, "pdfminer"
        # PDF image (scanné ou vectoriel image) → convertir chaque page en PNG
        if api_key:
            all_text = []

            # Méthode A : PyMuPDF page par page (si dispo)
            if PYMUPDF_OK:
                try:
                    doc = fitz.open(stream=raw, filetype="pdf")
                    for pg in range(min(len(doc), 5)):
                        pix  = doc[pg].get_pixmap(matrix=fitz.Matrix(3.0, 3.0))
                        png  = pix.tobytes("png")
                        page_text = _google_vision(png, api_key)
                        if page_text.strip():
                            all_text.append(page_text)
                    doc.close()
                except Exception:
                    pass

            # Méthode B : extraction directe du stream (sans deps système)
            if not all_text and PDFPLUMBER_OK and PIL_OK:
                try:
                    with pdfplumber.open(io.BytesIO(raw)) as pdf:
                        for pg_idx in range(min(len(pdf.pages), 5)):
                            png = _extract_pdf_image_stream(raw, pg_idx)
                            if png:
                                page_text = _google_vision(png, api_key)
                                if page_text.strip():
                                    all_text.append(page_text)
                except Exception:
                    pass

            # Méthode C : pdfplumber.to_image (ghostscript requis)
            if not all_text and PDFPLUMBER_OK:
                try:
                    with pdfplumber.open(io.BytesIO(raw)) as pdf:
                        for pg_idx, page in enumerate(pdf.pages[:5]):
                            buf = io.BytesIO()
                            page.to_image(resolution=250).save(buf, format="PNG")
                            buf.seek(0)
                            png = buf.read()
                            if png:
                                page_text = _google_vision(png, api_key)
                                if page_text.strip():
                                    all_text.append(page_text)
                except Exception:
                    pass

            if all_text:
                return "\n\n--- PAGE ---\n\n".join(all_text), "google_vision_pdf"

        # Fallback tesseract
        t = _tesseract(_pdf_to_png(raw))
        if t.strip(): return t, "tesseract"

    else:  # image
        if api_key:
            t = _google_vision(raw, api_key)
            if t.strip(): return t, "google_vision"
        t = _tesseract(raw)
        if t.strip(): return t, "tesseract"

    return "", "none"


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION DU TYPE DE DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────

DOC_SIGNATURES = {
    "avis_echeance": [
        r"avis\s+d[''']?\s*[eé]ch[eé]ance", r"pr[eé]l[eè]vement\s+automatique",
        r"montant\s+(?:total\s+)?[àa]\s+r[eé]gler", r"date\s+limite\s+de\s+paiement",
        r"r[eé]f[eé]rence\s+(?:de\s+)?paiement", r"avis\s+de\s+paiement",
        r"[eé]ch[eé]ance\s+du", r"quittance",
        r"facture\s+ttc", r"a\s+payer\s+avant",
        r"titulaire\s+du\s+contrat", r"loyer",
    ],
    "releve_bancaire": [
        r"relev[eé]\s+de\s+compte", r"relev[eé]\s+bancaire", r"extrait\s+de\s+compte",
        r"solde\s+(?:au|cr[eé]diteur|d[eé]biteur)", r"op[eé]rations\s+du\s+(?:\d|mois)",
        r"virement\s+re[cç]u", r"pr[eé]l[eè]vement\s+efectu[eé]",
        r"lib[eé]ll[eé]\s+.*?\s+d[eé]bit\s+cr[eé]dit",
    ],
    "bulletin_salaire": [
        r"bulletin\s+(?:de\s+)?(?:salaire|paie|paye)", r"fiche\s+de\s+paie",
        r"net\s+[àa]\s+payer\s+(?:au\s+salari[eé])?",
        r"cotisations?\s+(?:sociales?|patronales?|salariales?)",
        r"salaire\s+brut", r"urssaf", r"csg\b", r"crds\b",
        r"conges?\s+pay[eé]s", r"p[eé]riode\s+(?:de\s+)?paie",
    ],
    "note_frais": [
        r"note\s+de\s+frais", r"frais\s+(?:de\s+)?d[eé]placement",
        r"frais\s+professionnel", r"remboursement\s+(?:de\s+)?frais",
        r"ticket\s+de\s+caisse", r"re[cç]u\b", r"justificatif",
    ],
    "avoir": [
        r"\bavoir\b", r"note\s+de\s+cr[eé]dit", r"credit\s+note",
        r"remboursement\s+(?:suite|suite\s+[àa])",
        r"annulation\s+(?:de\s+)?(?:facture|commande)",
    ],
    "bon_commande": [
        r"bon\s+de\s+commande", r"purchase\s+order", r"\bP\.?O\.?\b",
        r"r[eé]f[eé]rence\s+commande", r"bon\s+d[''']?achat",
    ],
    "devis": [
        r"\bdevis\b", r"offre\s+(?:de\s+)?prix", r"proposition\s+commerciale",
        r"quotation", r"estimate\b", r"valable\s+(?:jusqu[''']?au|\d+\s+jours)",
    ],
    "contrat": [
        r"\bcontrat\b", r"convention\b", r"accord\b.*\bentre\b.*\bet\b",
        r"clause\b", r"r[eé]siliation", r"d[''']?une\s+dur[eé]e\s+de",
    ],
    "facture_achat": [
        r"facture\s+fournisseur", r"facture\s+d[''']?achat",
        r"r[eé]gl[eé]\s+[àa]\s+", r"fournisseur\s+:",
    ],
    "facture_vente": [
        r"facture\s+(?:client|de\s+vente)", r"facture\s+n[°o]",
        r"client\s+:", r"destinataire\s+:", r"\bfacture\b",
    ],
}

DOC_LABELS = {
    "facture_vente":   "Facture de vente",
    "facture_achat":   "Facture fournisseur",
    "avis_echeance":   "Avis d'échéance",
    "releve_bancaire": "Relevé bancaire",
    "bulletin_salaire":"Bulletin de salaire",
    "note_frais":      "Note de frais",
    "bon_commande":    "Bon de commande",
    "avoir":           "Avoir",
    "devis":           "Devis",
    "contrat":         "Contrat",
}

def classify_document(text: str) -> str:
    """
    Identifie le type de document avec un score de confiance.
    Retourne la clé du type ('facture_vente', 'avis_echeance', etc.)
    """
    text_l = text.lower()
    scores = {}
    for doc_type, patterns in DOC_SIGNATURES.items():
        scores[doc_type] = sum(
            1 for p in patterns if re.search(p, text_l)
        )
    best = max(scores, key=scores.get)
    # Seuil minimum : au moins 1 match
    return best if scores[best] > 0 else "facture_vente"


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION INTELLIGENTE DES ENTITÉS
# ─────────────────────────────────────────────────────────────────────────────

# ── Utilitaires ───────────────────────────────────────────────────────────────

def _clean(s):
    return re.sub(r'[\s\.\-]', '', s) if s else ""

def _norm_amount(s):
    """Normalise '1 440,00' → '1440.00'"""
    s = re.sub(r'\s', '', s or "").replace(',', '.')
    parts = s.split('.')
    if len(parts) > 2:
        s = ''.join(parts[:-1]) + '.' + parts[-1]
    try:
        float(s)
        return s
    except Exception:
        return ""

def _parse_amount(s):
    try: return float(_norm_amount(s))
    except: return 0.0

def _lines(text):
    return [l.strip() for l in text.splitlines() if l.strip()]

# ── SIRET / SIREN / TVA intracommunautaire ────────────────────────────────────

SIRET_LABELED = re.compile(
    r'(?:siret|siren|n[°o]?\s*(?:de\s*)?(?:siret|siren))\s*[:\s]+(\d[\d\s\.]{12,17})',
    re.IGNORECASE
)
SIRET_RAW     = re.compile(r'\b(\d{3}[\s]?\d{3}[\s]?\d{3}[\s]?\d{5})\b')
TVA_INTRA     = re.compile(r'\b(FR\s*\w{2}\s*\d{9})\b', re.IGNORECASE)

def _extract_all_sirets(text):
    results = []
    for m in SIRET_LABELED.finditer(text):
        c = _clean(m.group(1))
        if len(c) >= 9 and c not in results:
            results.append(c[:14])
    if not results:
        for m in SIRET_RAW.finditer(text):
            c = _clean(m.group(1))
            if c not in results:
                results.append(c)
    return results

# ── IBAN international (FR, DE, GB, ES, IT, BE, NL, CH...) ──────────────────

IBAN_RE = re.compile(
    r'\b([A-Z]{2}\d{2}[A-Z0-9][\w\s]{8,28})\b'
)
BIC_RE  = re.compile(r'\bBIC\s*[:\s]*([A-Z]{6}[A-Z0-9]{2,11})\b', re.IGNORECASE)

def _extract_iban(text):
    for m in IBAN_RE.finditer(text):
        candidate = re.sub(r'\s', '', m.group(1))
        if 15 <= len(candidate) <= 34 and candidate[:2].isalpha():
            return m.group(1).strip()
    return ""

# ── Emails et téléphones ──────────────────────────────────────────────────────

EMAIL_RE = re.compile(r'\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b')
PHONE_RE = re.compile(
    r'(?:t[ée]l[ée]?(?:phone)?|tel|mob(?:ile)?|portable|fax|contact)?\s*[:\.\-]?\s*'
    r'((?:\+33|0033|00\d{2}|0)[.\s\-]?[1-9](?:[.\s\-]?\d{2}){4})',
    re.IGNORECASE
)

# ── Dates ─────────────────────────────────────────────────────────────────────

MONTHS_MAP = {
    "janvier":1,"jan":1,"février":2,"fevrier":2,"fev":2,"mars":3,"mar":3,
    "avril":4,"avr":4,"mai":5,"juin":6,"juillet":7,"juil":7,
    "août":8,"aout":8,"septembre":9,"sep":9,"oct":10,"octobre":10,
    "novembre":11,"nov":11,"décembre":12,"decembre":12,"déc":12,"dec":12,
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
}

DATE_NUM   = re.compile(r'\b(\d{1,2})[/\.\-](\d{1,2})[/\.\-](20\d{2})\b')
DATE_ISO   = re.compile(r'\b(20\d{2})[/\.\-](\d{1,2})[/\.\-](\d{1,2})\b')
DATE_DASH  = re.compile(r'\b(\d{1,2})-(\d{1,2})-(20\d{2})\b')  # 17-03-2025
DATE_WORD  = re.compile(
    r'\b(\d{1,2})\s+(' + '|'.join(MONTHS_MAP.keys()) + r')\s+(20\d{2})\b',
    re.IGNORECASE
)

ECHEANCE_LABELS = re.compile(
    r'[eé]ch[eé]ance|due\s*date|expir|limit[e]?\s*(?:de\s*)?paiement|'
    r'r[eé]gler\s*avant|payer\s*avant|avant\s*le',
    re.IGNORECASE
)
EMISSION_LABELS = re.compile(
    r'[eé]mission|[eé]mit|date\s*(?:de\s*)?(?:la\s*)?(?:facture|document|envoi|d[eé]livrance)|'
    r'invoice\s*date|issued|[eé]tablie?\s*le|cr[eé][eé]e?\s*le',
    re.IGNORECASE
)

def _extract_date(text) -> str:
    """Retourne la date d'émission au format JJ/MM/AAAA."""
    lines = _lines(text)

    def _match_date(line):
        for pat in [DATE_NUM, DATE_DASH]:
            m = pat.search(line)
            if m: return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
        m = DATE_ISO.search(line)
        if m: return f"{int(m.group(3)):02d}/{int(m.group(2)):02d}/{m.group(1)}"
        m = DATE_WORD.search(line)
        if m:
            mo = MONTHS_MAP.get(m.group(2).lower(), 0)
            if mo: return f"{int(m.group(1)):02d}/{mo:02d}/{m.group(3)}"
        return None

    # Pass 1 : ligne avec label émission explicite (pas échéance)
    for line in lines:
        if EMISSION_LABELS.search(line) and not ECHEANCE_LABELS.search(line):
            d = _match_date(line)
            if d: return d

    # Pass 2 : ligne avec "date" sans "échéance"
    for line in lines:
        if re.search(r'\bdate\b', line, re.IGNORECASE) and not ECHEANCE_LABELS.search(line):
            d = _match_date(line)
            if d: return d

    # Pass 3 : première date du document
    for line in lines:
        d = _match_date(line)
        if d: return d

    return ""

# ── N° de document ────────────────────────────────────────────────────────────

DOC_NUM_RE = re.compile(
    r'(?:n[°o°ᵒ]?\s*(?:de\s*)?(?:facture|document|avoir|devis|commande|contrat|bon)|'
    r'facture\s*n[°o°ᵒ]?|invoice\s*(?:no\.?|n[°o°ᵒ]?)?|'
    r'num[eé]ro\s*(?:de\s*)?(?:facture|document|commande|avoir)?|'
    r'r[eé]f(?:[eé]rence)?\s*(?:facture|document|commande)?|'
    r'bon\s*de\s*commande\s*n[°o°ᵒ]?|'
    r'num[eé]ro\s+de\s+(?:commande|bon))'
    r'\s*[:\s#–\-]*([A-Z]{0,3}[\-]?[0-9][A-Z0-9\-\/\.]{1,25})',
    re.IGNORECASE | re.MULTILINE
)
REF_COMMANDE_RE = re.compile(
    r'(?:r[eé]f[eé]rence|r[eé]f\.?\s+commande|your\s+ref|'
    r'n[°o]?\s*commande|order\s*(?:n[°o]?|number|ref))'
    r'\s*[:\s]*([A-Z0-9][\w\-\/\.]{2,25})',
    re.IGNORECASE
)

INVALID_NUMS = re.compile(
    r'^(date|facture|client|total|montant|adresse|t[eé]l|email|'
    r'siret|siren|tva|iban|bic|page|r[eé]f|ref|le|du|au|de|la|un|une)$',
    re.IGNORECASE
)

def _extract_doc_number(text):
    # Essai 1 : pattern avec label (Facture N° xxx)
    for m in DOC_NUM_RE.finditer(text):
        c = m.group(1).strip().rstrip('.,;:').split('\n')[0].strip()
        # Couper avant un mot-clé de colonne tableau
        c = re.split(r'\s+(?:date|ech[eé]ance|mode|du\b|le\b|au\b)', c, flags=re.IGNORECASE)[0].strip()
        if not re.search(r'\d', c): continue
        if len(c) < 3 or len(c) > 35: continue
        if INVALID_NUMS.match(c): continue
        return c
    # Essai 2 : numéro alphanumérique typique seul sur une ligne (FA6528, FC-2024-001)
    for line in _lines(text):
        line = line.strip()
        if re.match(r'^[A-Z]{1,4}[-]?[0-9]{3,10}(?:[-/][0-9A-Z]{1,10})?$', line):
            return line
    return ""

# ── Montants ──────────────────────────────────────────────────────────────────

AMOUNT_PATTERN = re.compile(r'(\d[\d\s]*[.,]\d{2})')

TTC_LABELS = re.compile(
    r'total\s*(?:ttc|toutes?\s*taxes?\s*comprises?)|'
    r'net\s*[àa]\s*payer|total\s*[àa]\s*payer|'
    r'montant\s*total\s*(?:ttc)?|montant\s*[àa]\s*r[eé]gler|'
    r'total\s*d[ûu]|grand\s*total|total\s*invoice|amount\s*due|'
    r'total\s*factur[eé]|total\s*g[eé]n[eé]ral',
    re.IGNORECASE
)
HT_LABELS = re.compile(
    r'total\s*ht|sous[\s\-]?total\s*(?:ht)?|total\s*hors\s*tax[e]?s?|'
    r'montant\s*ht|base\s*(?:ht|hors\s*tax[e]?s?)|'
    r'subtotal|sous[\s\-]?total',
    re.IGNORECASE
)
TVA_LABELS = re.compile(
    r'(?:total\s*)?tva\s*(?:\(\s*[\d,\.]+\s*%\s*\))?|'
    r'montant\s*(?:de\s*la\s*)?tva|taxe\s*(?:sur\s*)?(?:la\s*)?valeur\s*ajout[eé]e|'
    r'vat\s*amount|tax\s*amount',
    re.IGNORECASE
)
REMISE_LABELS = re.compile(
    r'remise|r[eé]duction|discount|avoir|rabais|escompte',
    re.IGNORECASE
)

def _extract_amounts(text):
    lines   = _lines(text)
    result  = {}
    ttc_cands, ht_cands, tva_cands, remise_cands = [], [], [], []

    for line in lines:
        nums = AMOUNT_PATTERN.findall(line)
        if not nums: continue
        vals = [(n, _parse_amount(n)) for n in nums if _parse_amount(n) > 0]
        if not vals: continue
        best = max(vals, key=lambda x: x[1])

        if TTC_LABELS.search(line):
            ttc_cands.append(best)
        if HT_LABELS.search(line) and not TTC_LABELS.search(line):
            # Sur une ligne mixte HT+TVA+TTC, prendre le plus petit montant
            if len(vals) > 1:
                smallest = min(vals, key=lambda x: x[1])
                ht_cands.append(smallest)
            else:
                ht_cands.append(best)
        if TVA_LABELS.search(line) and not TTC_LABELS.search(line):
            # Si plusieurs montants sur la ligne et TVA est un mot en milieu de ligne,
            # prendre le montant qui suit le mot TVA
            tva_match = re.search(r'(?:tva|taxe)[^\d]*([\d][\d\s]*[.,]\d{2})', line, re.IGNORECASE)
            if tva_match:
                tva_val = tva_match.group(1)
                tva_cands.append((tva_val, _parse_amount(tva_val)))
            else:
                tva_cands.append(best)
        if REMISE_LABELS.search(line):
            remise_cands.append(best)

    if ttc_cands:
        b = max(ttc_cands, key=lambda x: x[1])
        n = _norm_amount(b[0])
        if n: result["montant_ttc"] = n + " €"
    if ht_cands:
        b = max(ht_cands, key=lambda x: x[1])
        n = _norm_amount(b[0])
        if n: result["montant_ht"] = n + " €"
    if tva_cands:
        b = max(tva_cands, key=lambda x: x[1])
        n = _norm_amount(b[0])
        if n: result["tva"] = n + " €"
    if remise_cands:
        b = max(remise_cands, key=lambda x: x[1])
        n = _norm_amount(b[0])
        if n and b[1] > 0: result["remise"] = n + " €"

    # Fallback TTC : plus grand montant du document
    if "montant_ttc" not in result:
        all_nums = re.findall(r'(\d[\d\s]*[.,]\d{2})\s*(?:€|EUR)', text, re.IGNORECASE)
        if all_nums:
            try:
                best = max(all_nums, key=_parse_amount)
                n = _norm_amount(best)
                if n: result["montant_ttc"] = n + " €"
            except Exception:
                pass

    return result

# ── Emetteur et Client ────────────────────────────────────────────────────────

CLIENT_TRIGGERS = re.compile(
    r'^(?:informations?\s*client|adresse\s*(?:de\s*)?(?:facturation|livraison|client)|'
    r'factur[eé]\s*[àa]|bill\s*(?:to|address)|destinataire|'
    r'client\s*[:\-]|nom\s*[:\-]|acheteur|'
    r'titulaire\s*(?:du\s*contrat|[:\-])|titulaire\b|'
    r'contract\s*holder|votre\s*contrat|abonné)',
    re.IGNORECASE
)

ADDRESS_RE = re.compile(
    r'(?:rue|avenue|all[eé]e|boulevard|impasse|chemin|route|place|'
    r'cit[eé]|r[eé]sidence|france|paris|lyon|marseille|toulouse|'
    r'bordeaux|nantes|strasbourg|lille|montpellier|'
    r'[0-9]{5}|cedex|bp\s*[0-9]|cs\s*[0-9]|tsa\s*[0-9]|tour\s+[a-z]|'
    r'service\s*client|la\s*d[eé]fense|la\s*defense|'
    r'zone\s*(?:industrielle|activit)|'
    r'parc\s*(?:activit|industriel)|\bzi\b|\bza\b|\bzac\b|'
    r'bat(?:iment)?|\betage\b|esc(?:alier)?)',
    re.IGNORECASE
)

IGNORE_WORDS = {
    'FACTURE','INVOICE','DEVIS','BON DE COMMANDE','AVOIR','RECEIPT',
    'DATE','TOTAL','MONTANT','ADRESSE','CLIENT','FOURNISSEUR',
    'SIRET','SIREN','TVA','IBAN','BIC','TELEPHONE','EMAIL','TEL',
    'DESCRIPTION','QUANTITE','PRIX','REFERENCE','NOTE','PAGE',
    'SUBTOTAL','SOUS-TOTAL','REMISE','DISCOUNT','TAXE','TAX',
    'COMMANDE','ORDER','CONTRACT','CONTRAT','DEVIS',
}

def _is_company(line):
    line = line.strip()
    if not (3 < len(line) < 80): return False
    if line[0].isdigit(): return False
    if '@' in line or 'http' in line.lower(): return False
    if ADDRESS_RE.search(line): return False
    if line.upper().strip('.,:-–') in IGNORE_WORDS: return False
    if not re.search(r'[A-Za-zÀ-ÿ]', line): return False
    # Rejeter lignes commençant par mot-clé de date/document/montant/instruction
    if re.match(r'^(?:facture\s+du|date|n[°o]\s*\d|avis|relev[eé]|bulletin|iban|'
                r'[àa]\s+payer|payer\s+avant|a\s+payer|r[eé]gler\s+avant|'
                r'montant|total|sous.total|sous\s+total|solde)', line, re.IGNORECASE):
        return False
    # Rejeter les sous-titres de société (taglines)
    if re.match(r'^(?:fournisseur\s+de|vendeur\s+de|sp[eé]cialiste\s+en|'
                r'expert\s+en|prestataire\s+de|distributeur\s+de|'
                r'fabricant\s+de|grossiste\s+en)', line, re.IGNORECASE):
        return False
    # Rejeter les lignes d'en-tête de tableau
    if re.match(r'^(?:facture\s+n|r[eé]f[eé]rence|d[eé]signation|quantit|ech[eé]ance|mode\s+de\s+paiement|lib[eé]ll[eé])', line, re.IGNORECASE):
        return False
    # Rejeter les lignes qui sont principalement des montants
    if re.match(r'^[A-Za-zÀ-ÿ\s]{2,30}\s+[\d][\d\s]*[.,]\d{2}\s*(?:€|EUR|\$)?\s*$', line, re.IGNORECASE):
        return False
    return True

def _clean_name(name):
    """Retire adresse et mentions légales du nom."""
    name = re.split(r'\s*[–\-,]\s*(?:\d{2,}|rue|av|all[eé]e|str|stra|blvd)', name, flags=re.IGNORECASE)[0]
    name = re.split(r'\s+–\s+', name)[0]
    name = re.split(r'\s+\-\s+(?=[A-Z][a-z])', name)[0]
    return name.strip().rstrip('.,;-–')

def _extract_entities(text):
    """Retourne (emetteur, client, ref_client)."""
    lines = _lines(text)
    emetteur = ""
    client   = ""
    ref_client = ""

    # Chercher le bloc client
    block_start = -1
    for i, line in enumerate(lines):
        if CLIENT_TRIGGERS.match(line):
            block_start = i
            break

    if block_start >= 0:
        # Émetteur = première ligne significative AVANT le bloc
        for line in lines[:block_start]:
            if _is_company(line):
                emetteur = _clean_name(line)
                break

        # Client = lignes APRÈS le trigger
        block = lines[block_start + 1: block_start + 12]
        i = 0
        while i < len(block):
            line = block[i]
            # "Nom : Société ABC"
            m = re.match(r'^(?:nom|soci[eé]t[eé]|company|entreprise|raison\s*sociale)\s*[:\-]\s*(.+)', line, re.IGNORECASE)
            if m:
                c = m.group(1).strip()
                if _is_company(c):
                    client = c
                    break
            elif _is_company(line) and not ADDRESS_RE.search(line):
                # Vérifier si ligne suivante complète le nom (prénom + nom sur 2 lignes)
                next_l = block[i+1] if i+1 < len(block) else ""
                if next_l and re.match(r'^[A-ZÀ-Ÿ][A-ZÀ-Ÿ\s\-]{1,35}$', next_l) and not ADDRESS_RE.search(next_l):
                    client = line + " " + next_l
                else:
                    client = line
                break
            i += 1
    else:
        # Pas de bloc client explicite
        # Stratégie : émetteur = premier nom, client = nom après ligne numéro+date
        found = []
        client_after_invoice_line = False
        for i, line in enumerate(lines[:30]):
            if _is_company(line) and not ADDRESS_RE.search(line):
                # Vérifier si on vient de passer une ligne de N°/date facture
                if client_after_invoice_line and found:
                    client = line
                    break
                found.append(_clean_name(line))
                if len(found) == 2:
                    break
            # Détecter ligne type "FA6528  13/01/2026  Chèque"
            elif re.match(r'^[A-Z]{0,4}[0-9][A-Z0-9\-]+\s+\d{2}[/\-]\d{2}[/\-]\d{4}', line):
                client_after_invoice_line = True
        if found: emetteur = found[0]
        if len(found) > 1 and not client: client = found[1]

    if not emetteur and lines:
        # N'utiliser la première ligne que si elle est courte (nom de société)
        first = _clean_name(lines[0])
        if len(first) <= 60:
            emetteur = first

    # Référence client
    m = re.search(
        r'(?:n[°o]?\s*client|r[eé]f(?:[eé]rence)?\s*client|customer\s*(?:id|ref|no))'
        r'\s*[:\s]+([A-Z0-9][\w\-]{2,20})',
        text, re.IGNORECASE
    )
    if m: ref_client = m.group(1).strip()

    return emetteur.strip(), client.strip(), ref_client

# ── Mode de paiement ──────────────────────────────────────────────────────────

PAYMENT_MODE_RE = re.compile(
    r'(?:mode|moyen)\s+(?:de\s+)?paiement\s*[:\-]?\s*([^\n]{3,40})|'
    r'paiement\s+(?:par|en)\s+([^\n]{3,30})|'
    r'r[eé]gl[eé]\s+(?:par|en)\s+([^\n]{3,30})',
    re.IGNORECASE
)

def _extract_payment_mode(text):
    m = PAYMENT_MODE_RE.search(text)
    if m:
        val = next((g for g in m.groups() if g), "").strip()
        return val[:50] if val else ""
    for kw in ["virement bancaire", "prélèvement", "chèque", "carte bancaire",
               "espèces", "paypal", "stripe", "paiement en ligne"]:
        if kw.lower() in text.lower():
            return kw.capitalize()
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION DATE
# ─────────────────────────────────────────────────────────────────────────────

def _date_tuple(date_str):
    if not date_str: return None
    m = re.match(r'(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})', date_str)
    if m:
        try: return int(m.group(1)), int(m.group(2)), int(m.group(3))
        except: pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def run_ocr(uploaded_file, api_key: str = "") -> dict:
    """
    Analyse complète et intelligente d'un document comptable.
    Supporte : PDF natif, PDF scanné, JPG, PNG, HEIC, WEBP.

    Retourne un dict structuré avec tous les champs extraits,
    le type de document détecté et la méthode OCR utilisée.
    """
    try:
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception as e:
        return {
            "filename": uploaded_file.name, "text": "", "fields": {},
            "available": False, "message": str(e),
            "invoice_date": None, "company_names": [],
            "siret": "", "siren": "",
            "client_email": "", "client_phone": "", "ocr_method": "error",
            "doc_type": "facture_vente", "doc_type_label": "Facture",
        }

    # Extraction du texte
    text, method = extract_text(uploaded_file.name, raw, api_key)

    if not text.strip():
        return {
            "filename": uploaded_file.name, "text": "", "fields": {},
            "available": False,
            "message": "Aucun texte extrait. Vérifiez GOOGLE_VISION_API_KEY dans secrets.toml.",
            "invoice_date": None, "company_names": [],
            "siret": "", "siren": "",
            "client_email": "", "client_phone": "", "ocr_method": method,
            "doc_type": "facture_vente", "doc_type_label": "Facture",
        }

    # Classification du document
    doc_type       = classify_document(text)
    doc_type_label = DOC_LABELS.get(doc_type, "Document")

    # Extraction des entités
    emetteur, client, ref_client = _extract_entities(text)
    sirets       = _extract_all_sirets(text)
    siret        = sirets[0] if sirets else ""
    siren        = siret[:9] if siret else ""
    siret_client = sirets[1] if len(sirets) > 1 else ""

    # Contacts
    emails = [e for e in EMAIL_RE.findall(text)
              if not any(x in e.lower() for x in ['noreply','no-reply','donotreply','mailer','postmaster'])]
    phones = [m.group(1).strip() for m in PHONE_RE.finditer(text)]
    client_email = emails[0] if emails else ""
    client_phone = phones[0] if phones else ""

    # Date et N° document
    date_str     = _extract_date(text)
    invoice_date = _date_tuple(date_str)
    doc_number   = _extract_doc_number(text)

    # Montants
    amounts = _extract_amounts(text)

    # IBAN / BIC
    iban = _extract_iban(text)
    bic  = ""
    m    = BIC_RE.search(text)
    if m: bic = m.group(1).strip()

    # Mode de paiement
    payment_mode = _extract_payment_mode(text)

    # TVA intracommunautaire
    tva_intra = ""
    m = TVA_INTRA.search(text)
    if m: tva_intra = m.group(1).strip()

    # Noms de sociétés (pour le classifieur)
    company_names = [n for n in [emetteur, client] if n]

    # ── Champs affichés dans l'UI ─────────────────────────────────────────────
    display = {}
    if emetteur:                      display["Émetteur"]          = emetteur
    if client:                        display["Client"]             = client
    if siret:                         display["SIRET émetteur"]     = siret
    if siret_client:                  display["SIRET client"]       = siret_client
    if tva_intra:                     display["N° TVA"]             = tva_intra
    if doc_number:                    display["N° Document"]        = doc_number
    if ref_client:                    display["Réf. client"]        = ref_client
    if date_str:                      display["Date émission"]      = date_str
    if amounts.get("montant_ht"):     display["Montant HT"]         = amounts["montant_ht"]
    if amounts.get("tva"):            display["TVA"]                = amounts["tva"]
    if amounts.get("montant_ttc"):    display["Montant TTC"]        = amounts["montant_ttc"]
    if amounts.get("remise"):         display["Remise"]             = amounts["remise"]
    if iban:                          display["IBAN"]               = iban
    if bic:                           display["BIC"]                = bic
    if payment_mode:                  display["Mode de paiement"]   = payment_mode
    if client_email:                  display["Email"]              = client_email
    if client_phone:                  display["Téléphone"]          = client_phone
    if len(emails) > 1:               display["Email (2)"]          = emails[1]
    if len(phones) > 1:               display["Tél. (2)"]           = phones[1]

    nb_fields = len(display)

    return {
        "filename":       uploaded_file.name,
        "text":           text,
        "available":      True,
        "message":        f"✅ {method} · {doc_type_label} · {nb_fields} champs",
        "fields":         display,
        "invoice_date":   invoice_date,
        "company_names":  company_names,
        "siret":          siret,
        "siren":          siren,
        "client_email":   client_email,
        "client_phone":   client_phone,
        "ocr_method":     method,
        "doc_type":       doc_type,
        "doc_type_label": doc_type_label,
        "amounts":        amounts,
    }