# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import json
import os
import time as _time

_APP_START = _time.time()

from bottle import Bottle, static_file, request, response, abort

# Static files directory (resolved at import time)
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))
WEBUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'webui', 'dist'))
from kuasarr.api.arr import setup_arr_routes
from kuasarr.api.captcha import setup_captcha_routes
from kuasarr.api.error_handler import json_error, setup_error_handlers
from kuasarr.api.categories import setup_categories_routes
from kuasarr.api.config import setup_config
from kuasarr.api.hosters import setup_hosters_routes
from kuasarr.api.dbc import setup_dbc_routes
from kuasarr.api.notifications import setup_notifications_routes
from kuasarr.api.search import setup_search_routes
from kuasarr.api.packages import setup_packages_routes
from kuasarr.api.statistics import setup_statistics
from kuasarr.providers import shared_state
from kuasarr.providers.auth import (
    add_auth_hook,
    add_auth_routes,
    require_api_key,
    require_csrf_token,
    get_browser_token,
    get_csrf_token,
    rotate_browser_token,
)
from kuasarr.providers.log import debug
from kuasarr.providers.ui.html_templates import render_button, render_centered_html, render_success_no_wait
from kuasarr.providers.ui.spa import try_serve_spa
from kuasarr.providers.web_server import Server
from kuasarr.storage.config import Config
from kuasarr.storage.setup.notifications import initialize_notification_settings


def get_api(shared_state_dict, shared_state_lock):
    shared_state.set_state(shared_state_dict, shared_state_lock)

    app = Bottle()

    add_auth_routes(app)
    add_auth_hook(app, whitelist=[".user.js"])
    setup_error_handlers(app)

    setup_arr_routes(app)
    setup_captcha_routes(app)
    setup_categories_routes(app)
    setup_config(app, shared_state)
    setup_hosters_routes(app)
    setup_statistics(app, shared_state)
    setup_dbc_routes(app)
    setup_notifications_routes(app, shared_state)
    setup_search_routes(app)
    setup_packages_routes(app)

    # Initialize notification settings from storage
    initialize_notification_settings(shared_state)

    # Serve static files (React build assets first, then legacy static)
    @app.get('/static/<filename:path>')
    def serve_static(filename):
        # Try React build assets first
        webui_path = os.path.join(WEBUI_DIR, filename)
        if os.path.exists(webui_path):
            mimetype = None
            if filename.endswith('.js'):
                mimetype = 'application/javascript'
            elif filename.endswith('.css'):
                mimetype = 'text/css'
            return static_file(filename, root=WEBUI_DIR, mimetype=mimetype)

        # Fallback to legacy static directory (logo, PWA assets)
        mimetype = None
        if filename.endswith('.webmanifest'):
            mimetype = 'application/manifest+json'
        elif filename.endswith('.js'):
            mimetype = 'application/javascript'
        return static_file(filename, root=STATIC_DIR, mimetype=mimetype)

    # Serve Vite build assets from /assets/ path
    @app.get('/assets/<filename:path>')
    def serve_assets(filename):
        mimetype = None
        if filename.endswith('.js'):
            mimetype = 'application/javascript'
        elif filename.endswith('.css'):
            mimetype = 'text/css'
        elif filename.endswith('.svg'):
            mimetype = 'image/svg+xml'
        elif filename.endswith('.png'):
            mimetype = 'image/png'
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            mimetype = 'image/jpeg'
        return static_file(filename, root=os.path.join(WEBUI_DIR, 'assets'), mimetype=mimetype)

    # Serve PWA manifest and service worker from root
    @app.get('/manifest.webmanifest')
    def serve_manifest():
        return static_file('manifest.webmanifest', root=WEBUI_DIR, mimetype='application/manifest+json')

    @app.get('/registerSW.js')
    def serve_service_worker():
        return static_file('registerSW.js', root=WEBUI_DIR, mimetype='application/javascript')

    @app.get('/sw.js')
    def serve_sw():
        return static_file('sw.js', root=WEBUI_DIR, mimetype='application/javascript')

    # PWA installation page
    @app.get('/pwa-install')
    def pwa_install():
        return static_file('pwa-install.html', root=STATIC_DIR)

    @app.get('/')
    def index():
        spa = try_serve_spa()
        if spa is not None:
            return spa

        # Legacy HTML fallback
        protected = shared_state.get_db("protected").retrieve_all_titles()
        # Browser-Token statt Maschinen-Key: dieser Wert landet im HTML der
        # Legacy-Seite und damit fuer jeden lesbar, der sie bekommt (#99).
        api_key = get_browser_token()
        csrf_token = get_csrf_token()
        jd_config = Config('JDownloader')
        jd_user = jd_config.get('user') or ""
        jd_device_cfg = jd_config.get('device') or ""

        # JDownloader connection status
        device = shared_state.values.get("device")
        from kuasarr.providers.myjd_api import Jddevice
        jd_connected = isinstance(device, Jddevice)
        if jd_connected:
            jd_status_pill = '<span class="status-pill success">&#9679; JDownloader connected</span>'
        elif jd_user and jd_device_cfg:
            jd_status_pill = '<span class="status-pill warning">&#9679; JDownloader configured (connecting...)</span>'
        else:
            jd_status_pill = '<span class="status-pill error">&#9679; JDownloader not configured</span>'

        captcha_hint = ""
        if protected:
            plural = 's' if len(protected) > 1 else ''
            captcha_hint += f"""
            <div class="section">
                <h2>Link{plural} waiting for CAPTCHA solution</h2>
                """

            if not shared_state.values.get("helper_active"):
                captcha_hint += """
                <p>
                    Enable the integrated CaptchaHelper to automatically decrypt protected packages.
                </p>
                """

            captcha_hint += f"""
                <p>{render_button(f"Solve CAPTCHA{plural}", 'primary', {'onclick': "location.href='/captcha'"})}</p>
            </div>
            <hr>
            """

        info = f"""
        <div class="header-section">
            <img src="/static/logo.png" alt="Kuasarr Logo" class="main-logo"/>
            <p class="tagline">Automated Downloads for Sonarr &amp; Radarr</p>
            <div class="status-pills">
                {jd_status_pill}
            </div>
        </div>

        {captcha_hint}

        <div class="section">
            <h2>📖 Setup Instructions</h2>
            <p>
                <a href="https://github.com/Ritedt/Kuasarr" target="_blank">
                    📚 Refer to the README for detailed instructions.
                </a>
            </p>
        </div>

        <hr>

        <div class="section">
            <h2>🔧 API Configuration</h2>
            <p>Use the URL and API Key below to set up a <strong>Newznab Indexer</strong> and <strong>SABnzbd Download Client</strong> in Radarr/Sonarr:</p>

            <details id="apiDetails">
                <summary id="apiSummary">🔑 Show API Settings</summary>
                <div class="api-settings">

                    <h3>🌐 URL</h3>
                    <div class="url-wrapper">
                      <input id="urlInput" class="copy-input" type="text" readonly value="{shared_state.values['internal_address']}" />
                      <button id="copyUrl" class="btn-primary btn-sm">📋 Copy</button>
                    </div>

                    <h3>🔐 API Key</h3>
                    <div class="api-key-wrapper">
                      <input id="apiKeyInput" class="copy-input" type="password" readonly value="{api_key}" />
                      <button id="toggleKey" class="btn-secondary btn-sm">👁️ Show</button>
                      <button id="copyKey" class="btn-primary btn-sm">📋 Copy</button>
                    </div>

                    <p>
                        <!-- POST statt GET: die Route rotiert einen Zustand und
                             ist CSRF-geschuetzt. Ein GET laesst sich per img-Tag
                             ausloesen, ein POST nicht. -->
                        <form method="post" action="/regenerate-api-key" onsubmit="return confirm(
                            'Regenerate API Key?\\n\\nThis invalidates the current API key. You will need to update it in Radarr/Sonarr.'
                        )">
                            <input type="hidden" name="csrf_token" value="{csrf_token}">
                            <button type="submit" class="btn-subtle btn-sm">🔄 Regenerate API Key</button>
                        </form>
                        <form method="post" action="/regenerate-browser-token" onsubmit="return confirm(
                            'Regenerate the browser token?\\n\\nOnly this web interface is logged out. Radarr/Sonarr keep working.'
                        )" style="margin-top: 0.5rem;">
                            <!-- Getrennt von /regenerate-api-key: nach einer XSS in der
                                 SPA muss das gestohlene Token entzogen werden koennen,
                                 ohne die *arr-Integration mitzunehmen. -->
                            <input type="hidden" name="csrf_token" value="{csrf_token}">
                            <button type="submit" class="btn-subtle btn-sm">🔑 Regenerate WebUI Token</button>
                        </form>
                    </p>
                </div>
            </details>
        </div>

        <hr>

        <div class="section">
            <h2>☁️ JDownloader</h2>
            <details id="jdDetails">
                <summary>Configure JDownloader credentials</summary>
                <div style="text-align:left; margin-top: 1rem;">
                    <label for="jd_user">MyJDownloader Email</label>
                    <input type="email" id="jd_user" placeholder="your@email.com" value="{jd_user}">

                    <label for="jd_pass" style="margin-top: 0.75rem;">MyJDownloader Password</label>
                    <input type="password" id="jd_pass" placeholder="{'••••••••' if jd_user else 'enter password'}">

                    <p style="margin-top: 0.75rem;">
                        <button class="btn-primary btn-sm" onclick="verifyJD()">🔍 Verify &amp; load devices</button>
                    </p>

                    <div id="jd_device_section" style="display:none; margin-top: 0.75rem;">
                        <label for="jd_device">Select Device</label>
                        <select id="jd_device"></select>
                        <p style="margin-top: 0.5rem;">
                            <button class="btn-primary btn-sm" onclick="saveJD()">💾 Save &amp; connect</button>
                        </p>
                    </div>
                    <div id="jd_status_msg" style="margin-top: 0.5rem; font-size: 0.9rem;"></div>
                </div>
            </details>
        </div>

        <hr>

        <div class="section">
            <h2>⚡ Quick Actions</h2>
            <div class="action-grid">
                <button class="action-btn" onclick="location.href='/categories'">
                    <span class="action-icon">📁</span>
                    <span class="action-text">Categories</span>
                </button>
                <button class="action-btn" onclick="location.href='/hostnames'">
                    <span class="action-icon">🌍</span>
                    <span class="action-text">Update Hostnames</span>
                </button>
                <button class="action-btn" onclick="location.href='/hosters'">
                    <span class="action-icon">🚫</span>
                    <span class="action-text">Manage Hosters</span>
                </button>
                <button class="action-btn" onclick="location.href='/statistics'">
                    <span class="action-icon">📊</span>
                    <span class="action-text">Statistics</span>
                </button>
                <button class="action-btn" onclick="location.href='/captcha-config'">
                    <span class="action-icon">🔑</span>
                    <span class="action-text">Captcha Settings</span>
                </button>
                <button class="action-btn" onclick="location.href='/settings'">
                    <span class="action-icon">⚙️</span>
                    <span class="action-text">Global Settings</span>
                </button>
                <button class="action-btn" onclick="location.href='/captcha'">
                    <span class="action-icon">🔓</span>
                    <span class="action-text">CAPTCHA Queue</span>
                </button>
                <button class="action-btn" onclick="location.href='/packages'">
                    <span class="action-icon">📦</span>
                    <span class="action-text">Packages</span>
                </button>
                <button class="action-btn" onclick="location.href='/notifications'">
                    <span class="action-icon">🔔</span>
                    <span class="action-text">Notifications</span>
                </button>
            </div>
        </div>

        <style>
            .header-section {{
                text-align: center;
                margin-bottom: 24px;
            }}
            .main-logo {{
                width: 120px;
                height: auto;
                margin-bottom: 8px;
                filter: drop-shadow(0 4px 8px rgba(0,0,0,0.2));
            }}
            .tagline {{
                font-size: 1.05em;
                color: var(--text-muted);
                margin: 0 0 8px 0;
            }}
            .status-pills {{
                margin-top: 6px;
            }}
            .section {{ margin: 16px 0; }}
            .api-settings {{ padding: 12px 0; text-align: left; }}
            .api-settings h3 {{ text-align: left; margin-top: 0.75rem; }}
            hr {{ margin: 20px 0; border: none; border-top: 1px solid var(--divider-color); }}
            details {{ margin: 8px 0; }}
            summary {{
                cursor: pointer;
                padding: 6px 0;
                font-weight: 500;
                user-select: none;
            }}
            summary:hover {{ color: var(--primary); }}
            .url-wrapper, .api-key-wrapper {{
                display: flex;
                gap: 0.5rem;
                align-items: center;
                margin-bottom: 0.5rem;
            }}
            .url-wrapper input, .api-key-wrapper input {{
                flex: 1;
                margin-bottom: 0;
            }}
            .action-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
                gap: 10px;
                margin-top: 12px;
            }}
            .action-btn {{
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: 18px 12px;
                border: 1px solid var(--card-border);
                border-radius: 10px;
                background: var(--card-bg);
                cursor: pointer;
                transition: all 0.2s ease;
                color: var(--fg-color);
                margin-top: 0;
                font-size: 1rem;
            }}
            .action-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 16px var(--card-shadow);
                border-color: var(--primary);
            }}
            .action-icon {{
                font-size: 1.8em;
                margin-bottom: 6px;
            }}
            .action-text {{
                font-size: 0.85em;
                font-weight: 500;
            }}
        </style>

        <script>
          // Copy URL
          const urlInput = document.getElementById('urlInput');
          const copyUrlBtn = document.getElementById('copyUrl');
          if (copyUrlBtn) {{
            copyUrlBtn.onclick = () => {{
              navigator.clipboard.writeText(urlInput.value).catch(() => {{
                urlInput.select(); document.execCommand('copy');
              }});
              copyUrlBtn.innerText = '✅ Copied!';
              setTimeout(() => {{ copyUrlBtn.innerText = '📋 Copy'; }}, 2000);
            }};
          }}

          // Show/copy API key
          const apiInput = document.getElementById('apiKeyInput');
          const toggleBtn = document.getElementById('toggleKey');
          const copyBtn = document.getElementById('copyKey');
          if (toggleBtn) {{
            toggleBtn.onclick = () => {{
              const isHidden = apiInput.type === 'password';
              apiInput.type = isHidden ? 'text' : 'password';
              toggleBtn.innerText = isHidden ? '🙈 Hide' : '👁️ Show';
            }};
          }}
          if (copyBtn) {{
            copyBtn.onclick = () => {{
              navigator.clipboard.writeText(apiInput.value).catch(() => {{
                apiInput.type = 'text'; apiInput.select(); document.execCommand('copy');
              }});
              copyBtn.innerText = '✅ Copied!';
              setTimeout(() => {{ copyBtn.innerText = '📋 Copy'; }}, 2000);
            }};
          }}

          // API details toggle label
          const apiDetails = document.getElementById('apiDetails');
          const apiSummary = document.getElementById('apiSummary');
          if (apiDetails && apiSummary) {{
            apiDetails.addEventListener('toggle', () => {{
              apiSummary.textContent = apiDetails.open ? '🔒 Hide API Settings' : '🔑 Show API Settings';
            }});
          }}

          // JDownloader verify & save
          function verifyJD() {{
            const user = document.getElementById('jd_user').value.trim();
            const pass = document.getElementById('jd_pass').value.trim();
            const statusEl = document.getElementById('jd_status_msg');
            if (!user || !pass) {{
              statusEl.innerHTML = '<span style="color:var(--error-color)">Please enter email and password.</span>';
              return;
            }}
            statusEl.innerHTML = 'Verifying...';
            kuasarrApiFetch('/api/jdownloader/verify', {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify({{user, password: pass}})
            }})
            .then(r => r.json())
            .then(data => {{
              if (data.devices && data.devices.length > 0) {{
                const sel = document.getElementById('jd_device');
                sel.innerHTML = '';
                data.devices.forEach(d => {{
                  const opt = document.createElement('option');
                  opt.value = d;
                  opt.textContent = d;
                  sel.appendChild(opt);
                }});
                // Pre-select configured device
                const cfg = "{jd_device_cfg}";
                if (cfg) {{
                  const existing = [...sel.options].find(o => o.value === cfg);
                  if (existing) existing.selected = true;
                }}
                document.getElementById('jd_device_section').style.display = 'block';
                statusEl.innerHTML = '<span style="color:var(--success-color)">✅ ' + data.devices.length + ' device(s) found.</span>';
              }} else {{
                statusEl.innerHTML = '<span style="color:var(--error-color)">❌ ' + (data.error || 'No devices found.') + '</span>';
              }}
            }})
            .catch(e => {{
              statusEl.innerHTML = '<span style="color:var(--error-color)">❌ Request failed: ' + e + '</span>';
            }});
          }}

          function saveJD() {{
            const user = document.getElementById('jd_user').value.trim();
            const pass = document.getElementById('jd_pass').value.trim();
            const device = document.getElementById('jd_device').value;
            const statusEl = document.getElementById('jd_status_msg');
            statusEl.innerHTML = 'Saving and connecting...';
            kuasarrApiFetch('/api/jdownloader/save', {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify({{user, password: pass, device}})
            }})
            .then(r => r.json())
            .then(data => {{
              if (data.data && data.data.success) {{
                statusEl.innerHTML = '<span style="color:var(--success-color)">✅ Connected! Reloading...</span>';
                setTimeout(() => location.reload(), 1500);
              }} else {{
                var msg = (data.error && data.error.message) || 'Failed to connect.';
                statusEl.innerHTML = '<span style="color:var(--error-color)">❌ ' + msg + '</span>';
              }}
            }})
            .catch(e => {{
              statusEl.innerHTML = '<span style="color:var(--error-color)">❌ Request failed: ' + e + '</span>';
            }});
          }}
        </script>
        """
        return render_centered_html(info)

    @app.get('/api/key')
    def get_api_key():
        """Liefert das Token, mit dem sich die WebUI ausweist.

        Das ist bewusst *nicht* der Maschinen-Key aus `[API]`. Vorher stand
        hier der vollwertige Key im Klartext in der Antwort - und damit
        im Modul-Scope des Browsers. Wer die WebUI erreichte, bekam damit
        denselben Schluessel, mit dem Radarr/Sonarr den Newznab- und
        SABnzbd-Zugang nutzen. Das Browser-Token gilt fuer dieselben
        Routen, laesst sich aber unabhaengig rotieren (siehe
        `rotate_browser_token`), ohne die *arr-Integration zu trennen.

        Geschuetzt durch Browser-Auth (Session-Cookie oder Basic Auth),
        sobald eine konfiguriert ist. Ohne konfigurierte WebUI-Auth ist
        die gesamte WebUI offen - nicht nur diese Route.
        """
        response.content_type = 'application/json'
        return json.dumps({'data': {'key': get_browser_token()}})

    @app.get('/api/csrf')
    def get_csrf_token_route():
        """Liefert das CSRF-Token fuer die React-WebUI aus.

        Das Cookie `kuasarr_csrf` wurde bisher nur auf der serverseitig
        gerenderten Legacy-Seite `/settings/core` gesetzt. Die SPA rendert
        diese Seite nie, das Cookie existierte dort also nie - und
        `validate_csrf_token` liefert bei fehlendem Cookie immer False. Damit
        scheiterten `POST /api/categories` und `POST /api/notifications` aus
        der SPA heraus immer mit 403.

        Bewusst ohne `@require_api_key`: die SPA holt den Token vor dem ersten
        authentifizierten Aufruf. Geschuetzt ist der Endpunkt durch die
        Browser-Auth - ohne konfigurierte WebUI-Auth ist auch die ganze
        WebUI nicht geschuetzt, dann gibt es hier nichts zu schuetzen.
        """
        response.content_type = 'application/json'
        return json.dumps({'data': {'csrf_token': get_csrf_token()}})

    @app.get('/api/version')
    @require_api_key
    def get_version_route():
        """Liefert die laufende Version fuer die WebUI.

        Der Sidebar-Fuss zeigte fest `v1.0.0`, weil es keinen Endpunkt gab,
        aus dem die SPA ihre Version haette ziehen koennen. Der Wert darf
        auf keinen Fall fest im Bundle stehen - dann ist er beim naechsten
        Release wieder falsch.

        `current` kommt lokal aus `version.json` und ist damit immer
        verfuegbar. Die Remote-Felder kommen aus dem Cache des
        Update-Checkers: ein GitHub-Aufruf wuerde hier bis zu 10 Sekunden
        blockieren, und die Sidebar darf daran nicht haengen. Mit
        `?refresh=1` wird live geprueft.
        """
        from kuasarr.providers import version as version_provider

        current = version_provider.get_version()
        # `last_checked_version` wird beim ersten Start mit der *laufenden*
        # Version belegt (`kuasarr/__init__.py`). Ungeprueft weiterzureichen
        # hiesse: bei jeder aktuellen Installation meldet die WebUI ein
        # Update, das es nicht gibt. Nur was sich davon unterscheidet, zaehlt.
        cached = shared_state.values.get('last_checked_version')
        payload = {
            'current': current,
            'latest_stable': None,
            'latest_prerelease': None,
            'update_available': (
                cached if cached and cached.lstrip('v') != current.lstrip('v') else None
            ),
            'releases_url': version_provider.LATEST_RELEASE_LINK,
        }

        if request.query.get('refresh') == '1':
            try:
                payload.update(version_provider.get_release_info())
            except Exception as e:
                # Kein Netz ist kein Fehler der WebUI. Die lokale Version
                # steht bereits, der Rest bleibt null.
                debug(f'Version route: remote check failed: {e}')
                payload['error'] = 'Could not reach GitHub for release information'

            # `get_release_info()` liefert bewusst kein fertiges
            # `update_available` - es kann nicht wissen, was der Aufrufer
            # gerade als "aktuell" fuehrt. Hier wird es aus dem Vergleich
            # gebildet, statt es ungeprueft zu uebernehmen.
            latest = payload.get('latest_stable')
            payload['update_available'] = (
                latest if latest and version_provider.is_newer(latest, current) else None
            )

        response.content_type = 'application/json'
        return json.dumps({'data': payload})

    @app.get('/api/statistics')
    @require_api_key
    def get_statistics():
        response.content_type = 'application/json'
        from kuasarr.providers.statistics import StatsHelper
        stats = StatsHelper(shared_state).get_stats()
        return json.dumps({'data': {
            'total_packages': stats['total_download_attempts'],
            'completed_packages': stats['packages_downloaded'],
            'failed_packages': stats['failed_downloads'],
            'total_downloaded': 0,
            'average_speed': 0,
            'uptime_seconds': int(_time.time() - _APP_START),
            'api_calls_today': 0,
            'captchas_solved_today': stats['total_captcha_decryptions'],
            'hoster_status': [],
            'daily_stats': [],
        }})

    @app.get('/api/jdownloader/status')
    @require_api_key
    def jd_status():
        response.content_type = 'application/json'
        from kuasarr.providers.myjd_api import Jddevice
        device = shared_state.values.get("device")
        connected = isinstance(device, Jddevice)
        jd_cfg = Config('JDownloader')
        return json.dumps({'data': {
            'connected': connected,
            'email': jd_cfg.get('user') or '',
            'device_name': jd_cfg.get('device') or '',
            'total_downloads': 0,
            'active_downloads': 0,
            'global_speed': 0,
            'reconnect_enabled': False,
        }})

    @app.get('/api/jdownloader/config')
    @require_api_key
    def jd_config_get():
        response.content_type = 'application/json'
        jd_cfg = Config('JDownloader')
        # `password` bleibt bewusst leer - das gespeicherte Passwort wird nie
        # ausgeliefert. `password_set` sagt dem Formular stattdessen, ob
        # ueberhaupt eins hinterlegt ist. Ohne das musste der Nutzer das
        # Passwort bei *jedem* Speichern neu tippen, weil `validateForm` es
        # verlangte und das Feld beim Laden leer war.
        #
        # `auto_reconnect`/`max_downloads`/`max_speed` sind entfernt: sie
        # wurden nie gelesen und nie persistiert. Das Formular tat so, als
        # waeren sie wirksam (#95).
        return json.dumps({'data': {
            'email': jd_cfg.get('user') or '',
            'password': '',
            'password_set': bool(jd_cfg.get('password')),
            'device_name': jd_cfg.get('device') or '',
        }})

    @app.post('/api/jdownloader/verify')
    @require_api_key
    def jd_verify():
        response.content_type = 'application/json'
        try:
            data = json.loads(request.body.read().decode('utf-8'))
            # Accept both 'email' (WebUI) and 'user' (legacy)
            user = (data.get('email') or data.get('user') or '').strip()
            password = data.get('password', '').strip()
        except Exception:
            return json.dumps({'data': {'valid': False}})

        if not user or not password:
            return json.dumps({'data': {'valid': False}})

        from kuasarr.providers.jdownloader import get_devices
        devices = get_devices(user, password)
        return json.dumps({'data': {'valid': devices is not None}})

    @app.post('/api/jdownloader/save')
    @require_api_key
    def jd_save():
        """Speichert die JDownloader-Zugangsdaten.

        Setzt in jedem Fehlerzweig einen echten Statuscode. Vorher lieferten
        alle Zweige HTTP 200 mit ``success: false`` - und ``fetchApi`` wirft
        nur bei ``!response.ok``. Falsche E-Mail, fehlendes Geraet oder
        falsches Passwort wurden deshalb als "Settings saved successfully!"
        angezeigt (#95).

        ``password`` darf leer bleiben, wenn bereits eines hinterlegt ist:
        das GET liefert das gespeicherte Passwort niemals aus, also kann der
        Nutzer es nicht unveraendert mitschicken, ohne es jedes Mal neu zu
        tippen.
        """
        response.content_type = 'application/json'
        try:
            data = json.loads(request.body.read().decode('utf-8'))
            user = (data.get('email') or data.get('user') or '').strip()
            password = data.get('password', '').strip()
            device = (data.get('device_name') or data.get('device') or '').strip()
        except Exception:
            return json_error(400, 'Invalid request')

        config = Config('JDownloader')

        if not user or not device:
            return json_error(400, 'E-Mail und Geraetename sind erforderlich')

        if not password:
            # Kein neues Passwort -> das gespeicherte weiterverwenden.
            password = config.get('password') or ''
            if not password:
                return json_error(400, 'E-Mail, Passwort und Geraetename sind erforderlich')

        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', user):
            return json_error(400, 'Invalid email format')

        from kuasarr.providers.jdownloader import set_device
        ok = set_device(user, password, device)
        if not ok:
            return json_error(
                502,
                'Connection failed. Please verify credentials and device name.'
            )

        config.save('user', user)
        config.save('password', password)
        config.save('device', device)

        return json.dumps({'data': {'success': True}})

    @app.post('/api/jdownloader/config')
    @require_api_key
    def jd_config_post():
        # WebUI uses POST /api/jdownloader/config to save settings
        return jd_save()

    @app.post('/regenerate-api-key')
    @require_csrf_token
    def regenerate_api_key():
        """Rotiert den Master-API-Key.

        War als GET registriert: ein `<img src="http://kuasarr:9999/regenerate-api-key">`
        auf irgendeiner Seite im LAN genuegte, um den Key zu rotieren und
        Radarr/Sonarr abzutrennen - Browser-Same-Origin-Policies greifen bei
        einem GET aus einem img-Tag nicht.
        """
        new_key = shared_state.generate_api_key()
        return render_success_no_wait(
            "API Key regenerated",
            f'<p>New key: <code>{new_key}</code></p><p>Update it in Radarr/Sonarr before continuing.</p>'
        )

    @app.post('/regenerate-browser-token')
    @require_csrf_token
    def regenerate_browser_token_route():
        """Rotiert nur das Token, mit dem sich die WebUI ausweist.

        Ohne diese Route waere die Trennung aus #99 wertlos: nach einer XSS
        in der SPA muss der Betreiber das gestohlene Token entziehen koennen,
        ohne Radarr/Sonarr zu trennen - und `POST /regenerate-api-key`
        rotiert genau das mit. Diese Route aendert ausschliesslich
        `WebUI.api_token`; der Master-Key in `API.key` bleibt unberuehrt.
        """
        rotate_browser_token()
        return render_success_no_wait(
            "Browser token regenerated",
            '<p>The web interface token was replaced. Radarr/Sonarr keep '
            'working. Reload this page to obtain the new token.</p>'
        )

    # SPA catch-all: serve index.html for all non-API routes
    @app.get('/<path:path>')
    def spa_catchall(path):
        """Serve React SPA for all non-API routes."""
        # Don't interfere with API routes
        if path.startswith('api/') or path.startswith('captcha') or path.startswith('download'):
            abort(404)
        # Don't interfere with static assets
        if path.startswith('assets/') or path.startswith('static/'):
            abort(404)

        # Serve any existing file from the webui dist root with the correct MIME type
        # (handles workbox-*.js, favicon.svg, icons.svg, registerSW.js, sw.js, etc.)
        candidate = os.path.join(WEBUI_DIR, path)
        if os.path.isfile(candidate) and path == os.path.basename(path):
            mimetype = None
            if path.endswith('.js'):
                mimetype = 'application/javascript'
            elif path.endswith('.css'):
                mimetype = 'text/css'
            elif path.endswith('.svg'):
                mimetype = 'image/svg+xml'
            elif path.endswith('.webmanifest'):
                mimetype = 'application/manifest+json'
            return static_file(path, root=WEBUI_DIR, mimetype=mimetype)

        spa = try_serve_spa()
        if spa is not None:
            return spa

        # If no React build, return 404
        abort(404)

    Server(app, listen='0.0.0.0', port=shared_state.values["port"]).serve_forever()
