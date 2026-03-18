"""
Injection PWA dans Streamlit.
- Manifeste + meta tags (iOS, Android, thème)
- Enregistrement du Service Worker
- Bouton "Installer l'application" (banner custom)
- Accès caméra natif via composant HTML
"""
import streamlit as st
import streamlit.components.v1 as components


PWA_HEAD = """
<link rel="manifest" href="/app/static/manifest.json">
<link rel="apple-touch-icon" href="/app/static/apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="FactureScan">
<meta name="application-name" content="FactureScan">
<meta name="theme-color" content="#1a472a">
<meta name="msapplication-TileColor" content="#0d0d0d">
<meta name="msapplication-TileImage" content="/app/static/icon-144x144.png">
"""

PWA_SCRIPT = """
<script>
// ── Service Worker ─────────────────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/app/static/sw.js', { scope: '/' })
      .then(reg => console.log('[SW] Registered:', reg.scope))
      .catch(err => console.warn('[SW] Error:', err));
  });
}

// ── Install Banner ─────────────────────────────────────────────────────────
let deferredPrompt = null;
const INSTALL_KEY = 'fs_install_dismissed';

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  deferredPrompt = e;

  if (sessionStorage.getItem(INSTALL_KEY)) return;

  const banner = document.getElementById('pwa-banner');
  if (banner) banner.style.display = 'flex';
});

function installApp() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  deferredPrompt.userChoice.then(choice => {
    deferredPrompt = null;
    document.getElementById('pwa-banner').style.display = 'none';
  });
}

function dismissBanner() {
  sessionStorage.setItem('fs_install_dismissed', '1');
  document.getElementById('pwa-banner').style.display = 'none';
}

// Masque le banner si déjà installé (mode standalone)
if (window.matchMedia('(display-mode: standalone)').matches) {
  sessionStorage.setItem('fs_install_dismissed', '1');
}
</script>

<!-- Install Banner -->
<div id="pwa-banner" style="
  display:none; position:fixed; bottom:0; left:0; right:0; z-index:9999;
  background:#0d0d0d; color:#f5f2eb;
  padding:14px 20px; align-items:center; gap:12px;
  border-top:2px solid #1a472a;
  font-family:'DM Sans',sans-serif;
  box-shadow:0 -4px 20px rgba(0,0,0,0.3);
">
  <img src="/app/static/icon-72x72.png" style="width:40px;height:40px;border-radius:8px;flex-shrink:0;">
  <div style="flex:1;">
    <div style="font-weight:700;font-size:0.9rem;">Installer FactureScan Pro</div>
    <div style="font-size:0.75rem;color:#9ca3af;">Accès rapide depuis votre écran d'accueil</div>
  </div>
  <button onclick="installApp()" style="
    background:#1a472a;color:#fff;border:none;border-radius:3px;
    padding:8px 16px;font-weight:700;font-size:0.82rem;cursor:pointer;white-space:nowrap;
  ">Installer</button>
  <button onclick="dismissBanner()" style="
    background:transparent;color:#9ca3af;border:none;
    font-size:1.2rem;cursor:pointer;padding:0 4px;line-height:1;
  ">×</button>
</div>
"""

# Instructions iOS (Safari ne supporte pas beforeinstallprompt)
IOS_INSTRUCTIONS = """
<div id="ios-hint" style="display:none;
  background:#fff; border:1.5px solid #d4cfc6; border-radius:4px;
  padding:14px 18px; margin:12px 0; font-size:0.85rem; color:#374151;
  box-shadow:2px 2px 0 #d4cfc6;
">
  <strong>📱 Installer sur iPhone</strong><br>
  <span style="color:#6b7280;">
    Appuyez sur <strong>⎋ Partager</strong> dans Safari →
    <strong>"Sur l'écran d'accueil"</strong>
  </span>
</div>
<script>
const isIos = /iphone|ipad|ipod/.test(navigator.userAgent.toLowerCase());
const isStandalone = window.navigator.standalone;
if (isIos && !isStandalone) {
  document.getElementById('ios-hint').style.display = 'block';
}
</script>
"""


def inject_pwa(cabinet_name: str = "FactureScan Pro"):
    """Injecte tous les éléments PWA dans la page Streamlit."""
    # Meta tags dans le head
    st.markdown(PWA_HEAD, unsafe_allow_html=True)
    # Scripts + banner Android
    st.markdown(PWA_SCRIPT, unsafe_allow_html=True)
    # Hint iOS
    st.markdown(IOS_INSTRUCTIONS, unsafe_allow_html=True)


def camera_uploader(label: str = "Prendre une photo ou choisir un fichier") -> bytes | None:
    """
    Composant caméra natif pour mobile.
    Retourne les bytes du fichier sélectionné ou None.
    Sur mobile : ouvre directement l'appareil photo.
    Sur desktop : ouvre le sélecteur de fichiers classique.
    """
    html = f"""
    <div style="margin:8px 0;">
      <label style="
        display:flex; align-items:center; justify-content:center; gap:10px;
        background:#0d0d0d; color:#f5f2eb;
        border-radius:3px; padding:14px 20px; cursor:pointer;
        font-family:'Syne',sans-serif; font-weight:700; font-size:0.9rem;
        letter-spacing:0.04em;
      ">
        <span>📷</span> {label}
        <input type="file" id="cameraInput"
          accept="image/*,application/pdf"
          capture="environment"
          multiple
          style="display:none;"
          onchange="handleFiles(this.files)"
        >
      </label>
      <div id="preview" style="margin-top:12px;"></div>
    </div>

    <script>
    function handleFiles(files) {{
      const preview = document.getElementById('preview');
      preview.innerHTML = '';
      Array.from(files).forEach(file => {{
        const div = document.createElement('div');
        div.style.cssText = 'display:flex;align-items:center;gap:10px;padding:8px 12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:3px;margin-bottom:6px;font-family:sans-serif;font-size:13px;';
        const icon = file.type.includes('pdf') ? '📄' : '🖼️';
        const size = (file.size/1024).toFixed(0);
        div.innerHTML = `<span>${{icon}}</span><span style="flex:1;font-weight:500;">${{file.name}}</span><span style="color:#9ca3af;">${{size}} Ko</span>`;
        preview.appendChild(div);

        // Si c'est une image → miniature
        if (file.type.startsWith('image/')) {{
          const img = document.createElement('img');
          img.style.cssText = 'width:100%;max-height:180px;object-fit:cover;border-radius:3px;margin-bottom:6px;';
          img.src = URL.createObjectURL(file);
          preview.insertBefore(img, div);
        }}
      }});
    }}
    </script>
    """
    components.html(html, height=200)
