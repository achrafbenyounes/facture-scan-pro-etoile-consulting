# 📄 FactureScan Pro — v2

Application Streamlit permettant aux clients d'un cabinet comptable de scanner
et transmettre leurs factures en quelques clics — avec Google Drive, OCR et multi-cabinets.

---

## ✨ Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| 📤 Upload multi-fichiers | PDF, JPG, PNG, HEIC jusqu'à 25 Mo |
| 📧 Email comptable | Envoi automatique avec PJ et résumé structuré |
| ✅ Confirmation client | Email HTML stylisé envoyé au client |
| ☁️ Google Drive | Dépôt auto dans dossier Client / Période |
| 🔍 OCR | Extraction montant, date, numéro, SIREN |
| 🏢 Multi-cabinets | Un déploiement, N cabinets isolés |
| 🔐 Espace comptable | Dashboard protégé, historique, export CSV |

---

## 🚀 Déploiement rapide — Streamlit Cloud (gratuit)

### 1. Préparer le repo GitHub

```bash
git init facturescan
cd facturescan
# Copiez tous les fichiers du projet ici
git add .
git commit -m "FactureScan Pro v2"
git remote add origin https://github.com/vous/facturescan.git
git push -u origin main
```

> ⚠️ N'ajoutez **jamais** `secrets.toml` au repo. Ajoutez `.streamlit/secrets.toml` à `.gitignore`.

### 2. Déployer

1. Allez sur [share.streamlit.io](https://share.streamlit.io)
2. **New app** → sélectionnez votre repo → fichier principal : `app.py`
3. **Advanced settings → Secrets** → collez votre configuration (voir ci-dessous)
4. Cliquez **Deploy**

### 3. URL personnalisée (optionnel)
Dans les paramètres de l'app Streamlit Cloud, vous pouvez définir un sous-domaine :
`https://facturescan-dupont.streamlit.app`

---

## ⚙️ Configuration

### Mode single cabinet (minimal)

```toml
CABINET_NAME    = "Cabinet Dupont & Associés"
COMPTABLE_EMAIL = "comptable@cabinet.fr"
SMTP_HOST       = "smtp.gmail.com"
SMTP_PORT       = 587
SMTP_USER       = "expediteur@gmail.com"
SMTP_PASSWORD   = "xxxx xxxx xxxx xxxx"
ADMIN_PASSWORD  = "motdepasse_fort"
DRIVE_ENABLED   = false
OCR_ENABLED     = false
```

### Mode multi-cabinets

```toml
[cabinets.dupont]
CABINET_NAME    = "Cabinet Dupont"
COMPTABLE_EMAIL = "dupont@cabinet.fr"
SMTP_USER       = "noreply@facturescan.fr"
SMTP_PASSWORD   = "xxxx xxxx xxxx xxxx"
ADMIN_PASSWORD  = "dupont_admin"
DRIVE_ENABLED   = true
DRIVE_ROOT_FOLDER_ID = "ID_dossier_dupont"
DRIVE_CREDENTIALS_JSON = '''{ "type": "service_account", ... }'''
OCR_ENABLED     = true

[cabinets.martin]
CABINET_NAME    = "Cabinet Martin & Fils"
...
```

---

## ☁️ Configurer Google Drive

### 1. Créer un projet Google Cloud

1. [console.cloud.google.com](https://console.cloud.google.com) → Nouveau projet
2. Activez l'**API Google Drive**
3. **IAM & Admin → Comptes de service** → Créer un compte de service
4. Créez une clé JSON → téléchargez-la

### 2. Partager le dossier Drive

1. Dans Google Drive, créez un dossier racine (ex: `FactureScan_Cabinet`)
2. Partagez-le avec l'email du compte de service (ex: `facturescan@projet.iam.gserviceaccount.com`) en tant qu'**Éditeur**
3. Copiez l'ID du dossier depuis l'URL : `https://drive.google.com/drive/folders/`**`1AbCdEfGhIjK...`**

### 3. Ajouter dans les secrets

```toml
DRIVE_ENABLED        = true
DRIVE_ROOT_FOLDER_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
DRIVE_CREDENTIALS_JSON = '''
{
  "type": "service_account",
  "project_id": "mon-projet",
  ...contenu complet du JSON téléchargé...
}
'''
```

---

## 🔍 Configurer l'OCR

### Sur Streamlit Cloud (automatique)
Le fichier `packages.txt` installe Tesseract automatiquement.
Décommentez `pytesseract` dans `requirements.txt` et activez :

```toml
OCR_ENABLED = true
```

### En local

```bash
# macOS
brew install tesseract tesseract-lang

# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-fra

pip install pytesseract Pillow pdfminer.six
```

---

## 📧 Configurer Gmail SMTP

1. Activez la vérification en 2 étapes → [myaccount.google.com/security](https://myaccount.google.com/security)
2. Créez un mot de passe d'application → [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Sélectionnez **Autre** → nommez-le "FactureScan"
4. Copiez le code 16 caractères dans `SMTP_PASSWORD`

> Fonctionne aussi avec **OVH, Infomaniak, Brevo (SendinBlue), Mailjet** — adaptez `SMTP_HOST` et `SMTP_PORT`.

---

## 🧪 Test en local

```bash
git clone https://github.com/vous/facturescan.git
cd facturescan

pip install -r requirements.txt

# Créez .streamlit/secrets.toml à partir du template
cp .streamlit/secrets_template.toml .streamlit/secrets.toml
# Éditez secrets.toml avec vos vraies valeurs

streamlit run app.py
```

---

## 📁 Structure du projet

```
facturescan_pro/
├── app.py                          # Point d'entrée Streamlit
├── requirements.txt                # Dépendances Python
├── packages.txt                    # Dépendances système (Tesseract)
├── pages/
│   ├── client.py                   # Interface client (upload + envoi)
│   └── admin.py                    # Dashboard comptable
├── utils/
│   ├── config.py                   # Chargement config / multi-cabinets
│   ├── styles.py                   # CSS global
│   ├── email_utils.py              # Envoi emails (comptable + client)
│   ├── drive_utils.py              # Intégration Google Drive
│   ├── ocr_utils.py                # OCR + extraction structurée
│   └── history.py                  # Historique session
└── .streamlit/
    ├── config.toml                 # Thème Streamlit
    └── secrets_template.toml       # Modèle de configuration
```

---

## 💡 Roadmap (v3)

- [ ] Stockage persistant (SQLite / Supabase)
- [ ] Notifications Slack/Teams au comptable
- [ ] Signature électronique des documents
- [ ] Dashboard analytique avancé (charts Plotly)
- [ ] Application mobile PWA

---

*FactureScan Pro — Tous droits réservés*
