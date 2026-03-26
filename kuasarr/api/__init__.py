# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import json
import os

from bottle import Bottle, static_file, request, response, abort

# Static files directory (resolved at import time)
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))
WEBUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'webui', 'dist'))
from kuasarr.api.arr import setup_arr_routes
from kuasarr.api.captcha import setup_captcha_routes
from kuasarr.api.categories import setup_categories_routes
from kuasarr.api.config import setup_config
from kuasarr.api.hosters import setup_hosters_routes
from kuasarr.api.dbc import setup_dbc_routes
from kuasarr.api.notifications import setup_notifications_routes
from kuasarr.api.search import setup_search_routes
from kuasarr.api.packages import setup_packages_routes
from kuasarr.api.statistics import setup_statistics
from kuasarr.providers import shared_state
from kuasarr.providers.auth import add_auth_hook, add_auth_routes, require_api_key
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
        api_key = Config('API').get('key')
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
                        <button class="btn-subtle btn-sm" onclick="showConfirm(
                            '🔄 Regenerate API Key',
                            '<p>This will invalidate the current API key. You will need to update it in Radarr/Sonarr.</p>',
                            'function(){{ location.href=\\'/regenerate-api-key\\'; }}'
                        )">🔄 Regenerate API Key</button>
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
              if (data.success) {{
                statusEl.innerHTML = '<span style="color:var(--success-color)">✅ Connected! Reloading...</span>';
                setTimeout(() => location.reload(), 1500);
              }} else {{
                statusEl.innerHTML = '<span style="color:var(--error-color)">❌ ' + (data.error || 'Failed to connect.') + '</span>';
              }}
            }})
            .catch(e => {{
              statusEl.innerHTML = '<span style="color:var(--error-color)">❌ Request failed: ' + e + '</span>';
            }});
          }}
        </script>
        """
        return render_centered_html(info)

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
        return json.dumps({'data': {
            'email': jd_cfg.get('user') or '',
            'password': '',
            'device_name': jd_cfg.get('device') or '',
            'auto_reconnect': True,
            'max_downloads': 3,
            'max_speed': 0,
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
        response.content_type = 'application/json'
        try:
            data = json.loads(request.body.read().decode('utf-8'))
            user = (data.get('email') or data.get('user') or '').strip()
            password = data.get('password', '').strip()
            device = (data.get('device_name') or data.get('device') or '').strip()
        except Exception:
            return json.dumps({'success': False, 'error': 'Invalid request'})

        if not user or not password or not device:
            return json.dumps({'success': False, 'error': 'All fields required'})

        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', user):
            return json.dumps({'success': False, 'error': 'Invalid email format'})

        from kuasarr.providers.jdownloader import set_device
        ok = set_device(user, password, device)
        if not ok:
            return json.dumps({'success': False, 'error': 'Connection failed. Please verify credentials and device name.'})

        config = Config('JDownloader')
        config.save('user', user)
        config.save('password', password)
        config.save('device', device)

        return json.dumps({'success': True})

    @app.post('/api/jdownloader/config')
    @require_api_key
    def jd_config_post():
        # WebUI uses POST /api/jdownloader/config to save settings
        return jd_save()

    @app.get('/regenerate-api-key')
    def regenerate_api_key():
        new_key = shared_state.generate_api_key()
        return render_success_no_wait(
            "API Key regenerated",
            f'<p>New key: <code>{new_key}</code></p><p>Update it in Radarr/Sonarr before continuing.</p>'
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
        # Don't interfere with PWA files
        if path in ('manifest.webmanifest', 'registerSW.js', 'sw.js'):
            abort(404)

        spa = try_serve_spa()
        if spa is not None:
            return spa

        # If no React build, return 404
        abort(404)

    Server(app, listen='0.0.0.0', port=shared_state.values["port"]).serve_forever()
