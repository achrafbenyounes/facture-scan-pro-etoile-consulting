"""
Moteur de classification — v3 autonome.

Plus de liste clients dans secrets.toml.
Le client est identifié DIRECTEMENT depuis la facture via l'OCR :
  1. SIRET/SIREN extrait → identité légale certaine
  2. Nom société extrait → base de données session (clients vus)
  3. Nouveau client → créé automatiquement dans la base session

La base clients est stockée dans st.session_state["client_db"]
et persistée en JSON dans .streamlit/clients.json si possible.
"""

import re
import json
import os
import difflib
from datetime import datetime
from typing import Optional
import streamlit as st

# ────────────────────────────────────────────────────────────────────────────
# Catégories comptables (plan comptable général français)
# ────────────────────────────────────────────────────────────────────────────

CATEGORIES = {
    "Achats_Fournisseurs": {
        "label":  "Achats — Fournisseurs",
        "folder": "1_Achats_Fournisseurs",
        "compte": "60x / 40x",
        "keywords": [
            "facture fournisseur","bon de commande","avoir fournisseur",
            "achat","approvisionnement","fourniture","prestation",
            "sous-traitance","edf","engie","orange","sfr","free",
            "electricité","gaz","eau","téléphone","internet","fibre",
            "loyer","bail","assurance","mutuelle fournisseur",
            "total","bp","carburant","maintenance","réparation",
            "matériel","équipement","informatique","logiciel","licence",
            "publicité","impression","transport","livraison","coursier",
            "nettoyage","sécurité","gardiennage","comptabilité",
            "règlement à","payer avant","échéance",
        ],
    },
    "Ventes_Clients": {
        "label":  "Ventes — Clients",
        "folder": "2_Ventes_Clients",
        "compte": "70x / 41x",
        "keywords": [
            "facture client","facture de vente","avoir client",
            "vente","prestation de service","honoraires",
            "devis accepté","commande client","livraison client",
            "facturé à","client :","doit la somme","solde dû",
            "règlement reçu","encaissement","acompte reçu",
            "consulting","mission","développement","formation",
        ],
    },
    "Notes_Frais": {
        "label":  "Notes de Frais",
        "folder": "3_Notes_Frais",
        "compte": "625 / 626",
        "keywords": [
            "note de frais","remboursement frais","frais de déplacement",
            "ticket","reçu","restaurant","hôtel","hébergement",
            "train","sncf","avion","taxi","uber","bolt","parking",
            "péage","autoroute","essence","carburant mission",
            "repas","repas d'affaires","déjeuner","dîner","café",
            "fournitures bureau","timbre","poste",
        ],
    },
    "Salaires_Social": {
        "label":  "Salaires — Social",
        "folder": "4_Salaires_Social",
        "compte": "64x / 43x",
        "keywords": [
            "bulletin de salaire","bulletin de paie","fiche de paie",
            "salaire","rémunération","cotisation","urssaf",
            "cpam","retraite","prévoyance","mutuelle salarié",
            "charges sociales","masse salariale","net à payer",
            "brut","congés payés","arrêt maladie",
            "pole emploi","france travail","apprentissage",
        ],
    },
    "Immobilisations": {
        "label":  "Immobilisations",
        "folder": "5_Immobilisations",
        "compte": "20x / 21x",
        "keywords": [
            "immobilisation","investissement","amortissement",
            "bien immobilisé","véhicule","machine","installation",
            "agencement","mobilier","crédit-bail","leasing",
            "acquisition","cession immobilisation",
        ],
    },
    "Banque_Tresorerie": {
        "label":  "Banque — Trésorerie",
        "folder": "6_Banque_Tresorerie",
        "compte": "51x",
        "keywords": [
            "relevé de compte","relevé bancaire","extrait de compte",
            "virement","prélèvement","chèque","rib","iban","bic",
            "solde compte","bordereau","remise de chèque",
        ],
    },
}

FALLBACK_CATEGORY = {"label": "À classer", "folder": "0_A_Classer", "compte": "—"}

MONTHS_FR = {
    1:"01_Janvier",2:"02_Février",3:"03_Mars",4:"04_Avril",
    5:"05_Mai",6:"06_Juin",7:"07_Juillet",8:"08_Août",
    9:"09_Septembre",10:"10_Octobre",11:"11_Novembre",12:"12_Décembre",
}

# ────────────────────────────────────────────────────────────────────────────
# Base clients (session + fichier JSON local)
# ────────────────────────────────────────────────────────────────────────────

CLIENT_DB_FILE = os.path.join(
    os.path.dirname(__file__), "..", ".streamlit", "clients_db.json"
)

def _load_db() -> dict:
    """Charge la base depuis session ou fichier JSON."""
    if "client_db" in st.session_state:
        return st.session_state["client_db"]
    try:
        if os.path.exists(CLIENT_DB_FILE):
            with open(CLIENT_DB_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                st.session_state["client_db"] = db
                return db
    except Exception:
        pass
    st.session_state["client_db"] = {}
    return st.session_state["client_db"]

def _save_db(db: dict):
    """Persiste la base en session et en JSON."""
    st.session_state["client_db"] = db
    try:
        os.makedirs(os.path.dirname(CLIENT_DB_FILE), exist_ok=True)
        with open(CLIENT_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_all_clients() -> list[dict]:
    db = _load_db()
    return list(db.values())

def _register_client(name: str, siret: str = "", siren: str = "", email: str = "", phone: str = "") -> dict:
    """Enregistre ou met à jour un client dans la base."""
    db  = _load_db()
    key = re.sub(r'\s+', '_', name.upper().strip())[:40]

    if key not in db:
        db[key] = {
            "name":       name.strip(),
            "siret":      siret,
            "siren":      siren or siret[:9] if siret else "",
            "email":      email,
            "phone":      phone,
            "seen_count": 1,
            "first_seen": datetime.now().strftime("%Y-%m-%d"),
            "last_seen":  datetime.now().strftime("%Y-%m-%d"),
            "is_new":     True,
        }
    else:
        db[key]["seen_count"] = db[key].get("seen_count", 0) + 1
        db[key]["last_seen"]  = datetime.now().strftime("%Y-%m-%d")
        if siret and not db[key].get("siret"):
            db[key]["siret"] = siret
        if siren and not db[key].get("siren"):
            db[key]["siren"] = siren
        if email and not db[key].get("email"):
            db[key]["email"] = email
        if phone and not db[key].get("phone"):
            db[key]["phone"] = phone
        db[key]["is_new"] = False

    _save_db(db)
    return db[key]


# ────────────────────────────────────────────────────────────────────────────
# Identification client depuis OCR
# ────────────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    s = s.lower().strip()
    for noise in ["sarl","sas","sa ","sasu","eurl","sci","snc","s.a.r.l.","s.a.s.","s.a."]:
        s = s.replace(noise, " ")
    return re.sub(r'[^a-zà-ÿ0-9\s]', ' ', s).strip()

def _find_in_db_by_siret(siret: str, siren: str) -> Optional[dict]:
    db = _load_db()
    for entry in db.values():
        if siret and entry.get("siret", "").startswith(siret[:9]):
            return entry
        if siren and entry.get("siren") == siren:
            return entry
    return None

def _find_in_db_by_name(name: str) -> Optional[dict]:
    db   = _load_db()
    norm = _normalize(name)
    best_ratio, best_entry = 0.0, None
    for entry in db.values():
        ratio = difflib.SequenceMatcher(None, norm, _normalize(entry["name"])).ratio()
        if ratio > best_ratio:
            best_ratio, best_entry = ratio, entry
    if best_ratio >= 0.80:
        return best_entry
    return None

def identify_client_from_ocr(ocr_result: dict) -> dict:
    """
    Identifie le client directement depuis les données OCR.
    Ne dépend plus d'aucune liste dans secrets.toml.
    """
    siret         = ocr_result.get("siret", "")
    siren         = ocr_result.get("siren", "")
    company_names = ocr_result.get("company_names", [])
    client_email  = ocr_result.get("client_email", "")
    client_phone  = ocr_result.get("client_phone", "")

    # Couche 1 : SIRET/SIREN → cherche dans la base existante
    if siret or siren:
        existing = _find_in_db_by_siret(siret, siren)
        if existing:
            existing["_match_method"] = "siret_db"
            existing["_confidence"]   = 1.0
            _register_client(existing["name"], siret, siren)
            return existing

    # Couche 2 : Noms extraits → cherche dans la base
    for name in company_names:
        existing = _find_in_db_by_name(name)
        if existing:
            existing["_match_method"] = "name_db"
            existing["_confidence"]   = 0.9
            _register_client(existing["name"], siret, siren)
            return existing

    # Couche 3 : Nouveau client → on le crée depuis la facture
    if company_names:
        # Prendre le premier nom détecté (haut de la facture = émetteur)
        best_name = company_names[0]
        client = _register_client(best_name, siret, siren, client_email, client_phone)
        client["_match_method"] = "ocr_new"
        client["_confidence"]   = 0.75
        return client

    # Couche 4 : Rien du tout → fallback
    # Mais si le siret/siren est présent, créer un client "inconnu" avec ces infos
    if siret or siren:
        client = _register_client(f"Client SIRET {siren or siret[:9]}", siret, siren, client_email, client_phone)
        client["_match_method"] = "siret_only"
        client["_confidence"]   = 0.6
        return client

    return {
        "name":          "Inconnu",
        "siret":         siret,
        "siren":         siren,
        "is_new":        False,
        "_match_method": "none",
        "_confidence":   0.0,
    }


# ────────────────────────────────────────────────────────────────────────────
# Classification catégorie
# ────────────────────────────────────────────────────────────────────────────

def classify_category_from_doctype(doc_type: str) -> dict:
    """Mappe le type de document IDP vers la catégorie comptable."""
    mapping = {
        "facture_achat":   "Achats_Fournisseurs",
        "facture_vente":   "Ventes_Clients",
        "note_frais":      "Notes_Frais",
        "bulletin_salaire":"Salaires_Social",
        "releve_bancaire": "Banque_Tresorerie",
        "bon_commande":    "Achats_Fournisseurs",
        "avoir":           "Ventes_Clients",
        "avis_echeance":   "Achats_Fournisseurs",
        "devis":           "Achats_Fournisseurs",
        "contrat":         "Achats_Fournisseurs",
    }
    cat_key = mapping.get(doc_type, "Achats_Fournisseurs")
    return {**CATEGORIES[cat_key], "_key": cat_key, "_score": 5, "_method": "doc_type"}

def classify_category(text: str) -> dict:
    text_lower = text.lower()
    scores = {k: sum(1 for kw in v["keywords"] if kw in text_lower)
              for k, v in CATEGORIES.items()}
    best_key   = max(scores, key=scores.get)
    best_score = scores[best_key]
    if best_score == 0:
        return {**FALLBACK_CATEGORY, "_score": 0, "_method": "fallback"}
    return {**CATEGORIES[best_key], "_key": best_key, "_score": best_score, "_method": "keyword"}


# ────────────────────────────────────────────────────────────────────────────
# Construction du chemin Drive
# ────────────────────────────────────────────────────────────────────────────

def build_drive_path(client: dict, category: dict, date_tuple=None) -> dict:
    from datetime import datetime as dt
    if date_tuple:
        try:
            date = dt(date_tuple[2], date_tuple[1], date_tuple[0])
        except Exception:
            date = dt.now()
    else:
        date = dt.now()

    exercice     = str(date.year)
    month_folder = MONTHS_FR.get(date.month, f"{date.month:02d}")

    if client and client.get("name") and client["name"] != "Inconnu":
        siret        = client.get("siret", "") or client.get("siren", "")
        siren_suffix = f" — {siret[:9]}" if siret else ""
        client_folder = f"{client['name']}{siren_suffix}"
    else:
        client_folder = FALLBACK_CATEGORY["folder"]

    cat_folder  = category.get("folder", FALLBACK_CATEGORY["folder"])
    is_fallback = client_folder == FALLBACK_CATEGORY["folder"] or cat_folder == FALLBACK_CATEGORY["folder"]

    return {
        "client_folder":   client_folder,
        "exercice_folder": exercice,
        "category_folder": cat_folder,
        "month_folder":    month_folder,
        "path_display":    f"{client_folder} / {exercice} / {cat_folder} / {month_folder}",
        "is_fallback":     is_fallback,
    }


# ────────────────────────────────────────────────────────────────────────────
# Analyse complète (point d'entrée)
# ────────────────────────────────────────────────────────────────────────────

def analyze_invoice(ocr_result: dict) -> dict:
    """
    Analyse complète à partir du résultat OCR.
    Ne prend plus de client_list en paramètre.
    """
    text         = ocr_result.get("text", "")
    client       = identify_client_from_ocr(ocr_result)
    # Utiliser le type IDP si disponible (plus précis), sinon keywords
    doc_type     = ocr_result.get("doc_type", "")
    if doc_type and doc_type != "facture_vente":
        category = classify_category_from_doctype(doc_type)
    else:
        category = classify_category(text)
    # Si le classifieur keywords trouve mieux, on le prend
    kw_cat = classify_category(text)
    if kw_cat.get("_score", 0) >= 2:
        category = kw_cat
    date_tuple   = ocr_result.get("invoice_date")
    drive_path   = build_drive_path(client, category, date_tuple)

    return {
        "client":         client,
        "category":       category,
        "invoice_date":   date_tuple,
        "drive_path":     drive_path,
        "siret":          ocr_result.get("siret", ""),
        "siren":          ocr_result.get("siren", ""),
        "company_names":  ocr_result.get("company_names", []),
        # is_fallback=True seulement si client vraiment inconnu ET catégorie non trouvée
        "is_fallback":    (client.get("name","Inconnu") == "Inconnu" and drive_path["is_fallback"]),
        "confidence":     client.get("_confidence", 0.0),
        "match_method":   client.get("_match_method", "none"),
        "is_new_client":  client.get("is_new", False),
    }