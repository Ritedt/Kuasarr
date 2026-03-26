# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import html

import kuasarr.providers.ui.html_images as images
from kuasarr.providers.version import get_version
from kuasarr.providers.auth import is_auth_enabled, is_browser_authenticated
from kuasarr.storage.config import Config


def render_centered_html(inner_content, footer_content=""):
    # Inject API key into WebUI when auth is disabled OR browser is authenticated
    api_key = ""
    if not is_auth_enabled() or is_browser_authenticated():
        try:
            api_key = Config("API").get("key") or ""
        except Exception:
            api_key = ""

    api_key = api_key.replace('"', '')
    api_key_script = f'        <script>\n            window.KUASARR_API_KEY = "{api_key}";\n        </script>\n' if api_key else ''

    head = (
        f'''
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="theme-color" content="#0d6efd">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <title>kuasarr</title>
        <link rel="icon" href="'''
        + images.logo
        + '''" type="image/png">
        <link rel="manifest" href="/static/manifest.webmanifest">
        <link rel="apple-touch-icon" href="/static/logo-192.png">
        <link rel="preload" href="/static/fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin>
        <style>
            /* Inter font (self-hosted, latin subset) */
            @font-face {
                font-family: 'Inter';
                font-style: normal;
                font-weight: 100 900;
                font-display: swap;
                src: url('/static/fonts/inter-latin.woff2') format('woff2');
                unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA,
                               U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122,
                               U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
            }
            /* Theme variables */
            :root {
                --bg-color: #f8f9fa;
                --fg-color: #212529;
                --card-bg: #ffffff;
                --card-shadow: rgba(0, 0, 0, 0.1);
                --card-border: #dee2e6;
                --primary: #0d6efd;
                --primary-hover: #0b5ed7;
                --secondary: #6c757d;
                --secondary-hover: #5c636a;
                --code-bg: #e9ecef;
                --spacing: 1rem;
                --border-radius: 0.5rem;
                --info-border: #2d5a2d;
                --setup-border: var(--primary);
                --divider-color: #dee2e6;
                --border-color: #dee2e6;
                --btn-subtle-bg: #e9ecef;
                --btn-subtle-border: #ced4da;
                --text-muted: #666;
                --link-color: #0d6efd;
                --success-color: #198754;
                --success-bg: #d1e7dd;
                --success-border: #a3cfbb;
                --error-color: #dc3545;
                --error-bg: #f8d7da;
                --error-border: #f1aeb5;
                --warning-color: #856404;
                --warning-bg: #fff3cd;
                --warning-border: #ffda6a;
            }
            @media (prefers-color-scheme: dark) {
                :root {
                    --bg-color: #121212;
                    --fg-color: #e9ecef;
                    --card-bg: #1e1e1e;
                    --card-shadow: rgba(0, 0, 0, 0.5);
                    --card-border: #4a5568;
                    --primary: #4d8fd4;
                    --primary-hover: #3a7bc8;
                    --secondary: #444444;
                    --secondary-hover: #333333;
                    --code-bg: #2d2d2d;
                    --info-border: #4a8c4a;
                    --setup-border: var(--primary);
                    --divider-color: #444;
                    --border-color: #4a5568;
                    --btn-subtle-bg: #444;
                    --btn-subtle-border: #666;
                    --text-muted: #a0aec0;
                    --link-color: #63b3ed;
                    --success-color: #68d391;
                    --success-bg: #1c4532;
                    --success-border: #276749;
                    --error-color: #fc8181;
                    --error-bg: #3d2d2d;
                    --error-border: #c53030;
                    --warning-color: #f6e05e;
                    --warning-bg: #2d2a0e;
                    --warning-border: #b7791f;
                }
            }
            /* Manual dark theme override via data attribute */
            :root[data-theme="dark"] {
                --bg-color: #121212;
                --fg-color: #e9ecef;
                --card-bg: #1e1e1e;
                --card-shadow: rgba(0, 0, 0, 0.5);
                --card-border: #4a5568;
                --primary: #4d8fd4;
                --primary-hover: #3a7bc8;
                --secondary: #444444;
                --secondary-hover: #333333;
                --code-bg: #2d2d2d;
                --info-border: #4a8c4a;
                --setup-border: var(--primary);
                --divider-color: #444;
                --border-color: #4a5568;
                --btn-subtle-bg: #444;
                --btn-subtle-border: #666;
                --text-muted: #a0aec0;
                --link-color: #63b3ed;
                --success-color: #68d391;
                --success-bg: #1c4532;
                --success-border: #276749;
                --error-color: #fc8181;
                --error-bg: #3d2d2d;
                --error-border: #c53030;
                --warning-color: #f6e05e;
                --warning-bg: #2d2a0e;
                --warning-border: #b7791f;
            }
            /* Info box styling */
            .info-box {
                border: 1px solid var(--info-border);
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 24px;
            }
            .info-box h3 {
                margin-top: 0;
                color: var(--info-border);
            }
            /* Setup box styling */
            .setup-box {
                border: 1px solid var(--setup-border);
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 24px;
            }
            .setup-box h3 {
                margin-top: 0;
                color: var(--setup-border);
            }
            /* Status pill styling */
            .status-pill {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 12px;
                border-radius: 999px;
                font-size: 0.85rem;
                font-weight: 500;
                margin: 4px 2px;
            }
            .status-pill.success {
                background: var(--success-bg);
                color: var(--success-color);
                border: 1px solid var(--success-border);
            }
            .status-pill.error {
                background: var(--error-bg);
                color: var(--error-color);
                border: 1px solid var(--error-border);
            }
            .status-pill.warning {
                background: var(--warning-bg);
                color: var(--warning-color);
                border: 1px solid var(--warning-border);
            }
            /* Subtle button styling */
            .btn-subtle {
                background: transparent;
                color: var(--fg-color);
                border: 1.5px solid var(--btn-subtle-border);
                padding: 8px 16px;
                border-radius: var(--border-radius);
                cursor: pointer;
                font-size: 1rem;
                font-weight: 500;
                transition: background-color 0.2s ease, border-color 0.2s ease;
            }
            .btn-subtle:hover {
                background: var(--btn-subtle-bg);
                border-color: var(--fg-color);
            }
            /* Divider styling */
            .section-divider {
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid var(--divider-color);
            }
            /* Logo and heading alignment */
            h1 {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                margin-bottom: 0.5rem;
                font-size: 2rem;
                cursor: pointer;
            }
            .logo {
                width: 48px;
                height: 48px;
                margin-right: 0.5rem;
            }
            /* Form labels and inputs */
            label {
                display: block;
                font-weight: 600;
                margin-bottom: 0.5rem;
            }
            input, select {
                display: block;
                width: 100%;
                padding: 0.5rem;
                font-size: 1rem;
                border: 1px solid var(--card-border);
                border-radius: var(--border-radius);
                background-color: var(--card-bg);
                color: var(--fg-color);
                box-sizing: border-box;
                transition: border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
            }
            input:focus, select:focus {
                border-color: var(--primary);
                outline: 0;
                box-shadow: 0 0 0 0.2rem rgba(13, 110, 253, 0.2);
            }
            *, *::before, *::after {
                box-sizing: border-box;
            }
            /* make body a column flex so footer can stick to bottom */
            html, body {
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                background-color: var(--bg-color);
                color: var(--fg-color);
                font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto,
                    'Helvetica Neue', 'Noto Sans', Arial, sans-serif;
                line-height: 1.6;
                display: flex;
                flex-direction: column;
                min-height: 100vh;
            }
            .outer {
                flex: 1;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: var(--spacing);
            }
            .inner {
                background-color: var(--card-bg);
                border-radius: 1rem;
                box-shadow: 0 0.5rem 1.5rem var(--card-shadow);
                padding: calc(var(--spacing) * 2);
                text-align: center;
                width: 100%;
                max-width: 600px;
            }
            /* No padding on the sides for captcha view on small screens */
            @media (max-width: 600px) {
                body:has(iframe) .outer {
                    padding-left: 0;
                    padding-right: 0;
                }
                body:has(iframe) .inner {
                    padding-left: 0;
                    padding-right: 0;
                }
            }
            h2 {
                margin-top: var(--spacing);
                margin-bottom: 0.75rem;
                font-size: 1.5rem;
            }
            h3 {
                margin-top: var(--spacing);
                margin-bottom: 0.5rem;
                font-size: 1.125rem;
                font-weight: 500;
            }
            p {
                margin: 0.5rem 0;
            }
            .copy-input {
                background-color: var(--code-bg);
            }
            .url-wrapper .api-key-wrapper {
                display: flex;
                gap: 0.5rem;
                flex-wrap: wrap;
                justify-content: center;
                margin-bottom: var(--spacing);
            }
            .captcha-container {
                background-color: var(--secondary);
            }
            button {
                padding: 0.5rem 1rem;
                font-size: 1rem;
                border-radius: var(--border-radius);
                font-weight: 500;
                cursor: pointer;
                transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
                border: none;
                margin-top: 0.5rem;
                display: inline-block;
            }
            .btn-primary {
                background-color: var(--primary);
                color: #fff;
                border: 1.5px solid transparent;
            }
            .btn-primary:hover {
                background-color: var(--primary-hover);
                box-shadow: 0 2px 6px rgba(13, 110, 253, 0.4);
            }
            .btn-secondary {
                background-color: var(--secondary);
                color: #fff;
                border: 1.5px solid transparent;
            }
            .btn-secondary:hover {
                background-color: var(--secondary-hover);
                box-shadow: 0 2px 6px rgba(108, 117, 125, 0.4);
            }
            .btn-danger {
                background-color: var(--error-color);
                color: #fff;
                border: 1.5px solid var(--error-border);
            }
            .btn-danger:hover {
                background-color: #c82333;
                box-shadow: 0 2px 6px rgba(220, 53, 69, 0.4);
            }
            .btn-sm {
                padding: 0.25rem 0.5rem;
                font-size: 0.875rem;
                margin-top: 0;
            }
            button:not(:disabled):active {
                transform: translateY(1px);
                box-shadow: none;
            }
            button:disabled {
                opacity: 0.65;
                cursor: not-allowed;
            }
            a {
                color: var(--link-color);
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
            button:focus-visible {
                outline: 2px solid var(--primary);
                outline-offset: 2px;
            }
            a:focus-visible {
                outline: 2px solid var(--primary);
                outline-offset: 2px;
            }
            @media (prefers-reduced-motion: reduce) {
                *, *::before, *::after {
                    transition-duration: 0.01ms !important;
                    animation-duration: 0.01ms !important;
                }
            }
            /* Top navigation */
            .top-nav {
                display: flex;
                justify-content: center;
                gap: 1.5rem;
                padding: 0.75rem 0;
                margin-bottom: 1rem;
                border-bottom: 1px solid var(--border-color, #ddd);
            }
            .nav-link {
                color: var(--text-muted, #666);
                text-decoration: none;
                font-weight: 500;
                padding: 0.25rem 0.5rem;
                border-radius: 4px;
                transition: color 0.2s;
            }
            .nav-link:hover {
                color: var(--primary);
            }
            .nav-active {
                color: var(--primary);
                border-bottom: 2px solid var(--primary);
            }
            /* footer styling */
            footer {
                text-align: center;
                font-size: 0.75rem;
                color: var(--text-muted);
                padding: 0.5rem 0;
            }
            footer a {
                color: var(--text-muted);
            }
            footer a:hover {
                color: var(--fg-color);
            }
            /* Global Modal Styles */
            .status-modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                justify-content: center;
                z-index: 9999;
                visibility: hidden;
                opacity: 0;
                transition: visibility 0s, opacity 0.2s;
                overflow-y: auto;
                padding: 1rem;
            }
            .status-modal-overlay.active {
                visibility: visible;
                opacity: 1;
            }
            .status-modal {
                background: var(--card-bg);
                border-radius: 0.5rem;
                padding: 1.5rem;
                max-width: 420px;
                width: 90%;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
                transform: scale(0.9);
                transition: transform 0.2s;
                margin: auto;
            }
            .status-modal-overlay.active .status-modal {
                transform: scale(1);
            }
            .status-modal h3 {
                margin: 0 0 1rem 0;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }
            .status-modal p {
                margin: 0 0 1rem 0;
                word-break: break-word;
            }
            .status-modal .btn-row {
                display: flex;
                gap: 0.5rem;
                justify-content: flex-end;
            }
        </style>
        <script>
        // SECURITY: API key is NOT exposed to JavaScript.
        // WebUI endpoints rely on BasicAuth (if configured).
        // External API endpoints (/api/* for Radarr/Sonarr) use X-API-Key header.

        document.addEventListener('DOMContentLoaded', function() {
            const h1 = document.querySelector('h1');
            if (h1) {
                h1.onclick = function() { window.location.href = '/'; };
            }
            // Auto-inject apikey into HTML forms targeting /api endpoints
            if (window.KUASARR_API_KEY) {
                document.querySelectorAll('form[action^="/api"]').forEach(function(form) {
                    if (form.querySelector('input[name="apikey"]')) return;
                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'apikey';
                    input.value = window.KUASARR_API_KEY;
                    form.appendChild(input);
                });
            }
        });

        // Helper for WebUI API calls — injects X-API-Key header when available
        function kuasarrApiFetch(path, options) {
            const opts = options ? { ...options } : {};
            const headers = new Headers(opts.headers || {});
            if (window.KUASARR_API_KEY && !headers.has('X-API-Key')) {
                headers.set('X-API-Key', window.KUASARR_API_KEY);
            }
            opts.headers = headers;
            return fetch(path, opts);
        }
        </script>
'''
        + api_key_script
        + '''    </head>'''
    )

    sw_script = '''
        <script>
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('/static/sw.js')
                    .catch(function(err) {
                        console.log('SW registration failed:', err);
                    });
            }
        </script>
    '''

    # Global modal script
    modal_script = """
    <script>
    function showModal(title, content, buttonsHtml) {
        let overlay = document.getElementById('global-modal-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'global-modal-overlay';
            overlay.className = 'status-modal-overlay';
            overlay.innerHTML = `
                <div class="status-modal">
                    <h3 id="global-modal-title"></h3>
                    <div id="global-modal-content"></div>
                    <div class="btn-row" id="global-modal-buttons"></div>
                </div>
            `;
            document.body.appendChild(overlay);
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) closeModal();
            });
        }
        document.getElementById('global-modal-title').innerHTML = title;
        document.getElementById('global-modal-content').innerHTML = content;
        const btns = buttonsHtml || '<button class="btn-secondary" onclick="closeModal()">Close</button>';
        document.getElementById('global-modal-buttons').innerHTML = btns;
        requestAnimationFrame(() => { overlay.classList.add('active'); });
    }

    function closeModal() {
        const overlay = document.getElementById('global-modal-overlay');
        if (overlay) {
            overlay.classList.remove('active');
            setTimeout(() => { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); }, 200);
        }
    }

    function showConfirm(title, content, onConfirm) {
        showModal(title, content,
            `<button class="btn-secondary btn-sm" onclick="closeModal()">Cancel</button>
             <button class="btn-danger btn-sm" onclick="closeModal(); (${onConfirm})()">Confirm</button>`
        );
    }
    </script>
    """

    footer_parts = [footer_content, f"kuasarr v.{get_version()}"]
    footer_html = " &middot; ".join(filter(None, footer_parts))

    body = f'''
    {head}
    <body>
        <div class="outer">
            <div class="inner">
                {inner_content}
            </div>
        </div>
        <footer>
            {footer_html}
        </footer>
        {modal_script}
        {sw_script}
    </body>
    '''
    return f'<!DOCTYPE html><html lang="en">{body}</html>'


def render_button(text, button_type="primary", attributes=None):
    cls = "btn-primary" if button_type == "primary" else ("btn-danger" if button_type == "danger" else "btn-secondary")
    attr_str = ''
    if attributes:
        attr_str = ' '.join(f'{key}="{value}"' for key, value in attributes.items())
    return f'<button class="{cls}" {attr_str}>{text}</button>'


def render_nav(active_page=""):
    pages = [
        ("/", "Home"),
        ("/settings", "Settings"),
        ("/categories", "Categories"),
        ("/captcha-config", "CAPTCHA"),
        ("/hosters", "Hosters"),
        ("/notifications", "Notifications"),
    ]
    items = "".join(
        f'<a href="{url}" class="nav-link{" nav-active" if url == active_page else ""}">{label}</a>'
        for url, label in pages
    )
    return f'<nav class="top-nav">{items}</nav>'


def render_form(header, form="", script="", footer_content="", active_page=""):
    nav = render_nav(active_page)
    content = f'''
    <h1><img src="{images.logo}" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    {nav}
    <h2>{header}</h2>
    {form}
    {script}
    '''
    return render_centered_html(content, footer_content)


def render_success(message, timeout=5, optional_text=""):
    script = f'''
        <script>
            let counter = {timeout};
            const btn = document.getElementById('nextButton');
            const info = document.getElementById('redirect-info');
            const interval = setInterval(() => {{
                counter--;
                if (info) info.textContent = `Redirecting in ${{counter}}s...`;
                if (counter <= 0) {{
                    clearInterval(interval);
                    window.location.href = '/';
                    return;
                }}
            }}, 1000);
            btn.onclick = () => {{ clearInterval(interval); window.location.href = '/'; }};
        </script>
    '''
    button_html = render_button("Go to Home", "primary", {"id": "nextButton"})
    safe_message = html.escape(message)
    safe_optional = html.escape(optional_text) if optional_text else ""
    content = f"""
    <h1><img src="{images.logo}" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    <h2>{safe_message}</h2>
    {safe_optional}
    <p id="redirect-info" style="color:var(--text-muted);font-size:0.85rem;">Redirecting in {timeout}s...</p>
    {button_html}
    {script}
    """
    return render_centered_html(content)


def render_success_no_wait(message, optional_text=""):
    button_html = render_button("Continue", "primary", {"onclick": "window.location.href='/'"})
    safe_message = html.escape(message)
    safe_optional = html.escape(optional_text) if optional_text else ""
    content = f'''<h1><img src="{images.logo}" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    <h2>{safe_message}</h2>
    {safe_optional}
    {button_html}
    '''
    return render_centered_html(content)


def render_fail(message):
    button_html = render_button("Back", "secondary", {"onclick": "window.location.href='/'"})
    safe_message = html.escape(message)
    return render_centered_html(f"""<h1><img src="{images.logo}" alt="kuasarr logo" class="logo"/>kuasarr</h1>
        <h2>{safe_message}</h2>
        {button_html}
    """)


def render_core_settings_form(internal_address="", external_address="", timezone="Europe/Berlin", csrf_token=""):
    """Render the Core Settings form for Sprint H2/H5 with CSRF protection."""
    common_timezones = [
        "UTC",
        "Europe/Berlin",
        "Europe/London",
        "Europe/Paris",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "Asia/Tokyo",
        "Asia/Shanghai",
        "Australia/Sydney",
    ]

    timezone_options = "\n".join(
        f'<option value="{tz}"{" selected" if tz == timezone else ""}>{tz}</option>'
        for tz in common_timezones
    )

    # Sprint H5: Include CSRF token in form
    csrf_input = f'<input type="hidden" name="csrf_token" id="csrf_token" value="{html.escape(csrf_token)}">' if csrf_token else ''

    form_html = f"""
    <form id="core-settings-form" class="form-container">
        {csrf_input}
        <div class="form-group">
            <label for="internal_address" class="form-label">
                Internal Address
                <span class="required" aria-label="required">*</span>
            </label>
            <input type="url" id="internal_address" name="internal_address"
                   value="{html.escape(internal_address)}"
                   placeholder="http://localhost:8080" required
                   pattern="https?://.*" class="form-input"
                   aria-describedby="internal_help">
            <small id="internal_help" class="form-help">
                Address for JDownloader callback. Must be reachable from JDownloader.
            </small>
        </div>

        <div class="form-group">
            <label for="external_address" class="form-label">
                External Address
                <span class="optional">(optional)</span>
            </label>
            <input type="url" id="external_address" name="external_address"
                   value="{html.escape(external_address)}"
                   placeholder="https://kuasarr.example.com"
                   pattern="https?://.*" class="form-input"
                   aria-describedby="external_help">
            <small id="external_help" class="form-help">
                External URL for generated links. Leave empty to use internal address.
            </small>
        </div>

        <div class="form-group">
            <label for="timezone" class="form-label">Timezone</label>
            <select id="timezone" name="timezone" class="form-select" required>
                {timezone_options}
            </select>
        </div>

        <div class="form-actions">
            <button type="submit" class="btn-primary">
                <span class="btn-text">Save Settings</span>
                <span class="btn-spinner" hidden>
                    <svg class="spinner" viewBox="0 0 24 24" width="16" height="16">
                        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor"
                                stroke-width="3" stroke-dasharray="31.4 31.4" transform="rotate(-90 12 12)">
                            <animateTransform attributeName="transform" type="rotate"
                                              from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/>
                        </circle>
                    </svg>
                    Saving...
                </span>
            </button>
            <button type="button" class="btn-secondary" onclick="location.href='/settings'">Back</button>
            <div id="form-feedback" class="form-feedback" role="status" aria-live="polite"></div>
        </div>
    </form>
    """

    script = """
    <script>
    function initializeCoreSettingsForm() {
        const form = document.getElementById('core-settings-form');
        const feedback = document.getElementById('form-feedback');
        const submitBtn = form.querySelector('button[type="submit"]');
        // Sprint H5: Get CSRF token from hidden input or cookie
        const csrfToken = document.getElementById('csrf_token')?.value || document.cookie.match(/kuasarr_csrf=([^;]+)/)?.[1] || '';

        // Create error message elements for each field
        const fields = ['internal_address', 'external_address', 'timezone'];
        fields.forEach(fieldName => {
            const input = document.getElementById(fieldName);
            if (input) {
                const errorId = fieldName + '-error';
                let errorEl = document.getElementById(errorId);
                if (!errorEl) {
                    errorEl = document.createElement('div');
                    errorEl.id = errorId;
                    errorEl.className = 'field-error';
                    errorEl.setAttribute('role', 'alert');
                    input.parentNode.insertBefore(errorEl, input.nextSibling);
                }
            }
        });

        // URL validation helper
        function isValidUrl(url, allowEmpty = false) {
            if (!url || url.trim() === '') return allowEmpty;
            try {
                const parsed = new URL(url);
                return parsed.protocol === 'http:' || parsed.protocol === 'https:';
            } catch (e) {
                return false;
            }
        }

        // Get specific error message for URL validation
        function getUrlErrorMessage(fieldName, url) {
            if (!url || url.trim() === '') {
                return fieldName + ' is required. Please enter a valid URL.';
            }
            try {
                new URL(url);
                return fieldName + ' must use http:// or https:// protocol.';
            } catch (e) {
                return fieldName + ' must be a valid URL starting with http:// or https://';
            }
        }

        // Show field error
        function showFieldError(fieldName, message) {
            const input = document.getElementById(fieldName);
            const errorEl = document.getElementById(fieldName + '-error');
            if (input) {
                input.setAttribute('aria-invalid', 'true');
                input.classList.add('has-error');
            }
            if (errorEl) {
                errorEl.textContent = message;
                errorEl.style.display = 'block';
            }
        }

        // Clear field error
        function clearFieldError(fieldName) {
            const input = document.getElementById(fieldName);
            const errorEl = document.getElementById(fieldName + '-error');
            if (input) {
                input.removeAttribute('aria-invalid');
                input.classList.remove('has-error');
            }
            if (errorEl) {
                errorEl.textContent = '';
                errorEl.style.display = 'none';
            }
        }

        // Clear all field errors
        function clearAllErrors() {
            fields.forEach(clearFieldError);
        }

        // Real-time URL validation on blur
        const urlInputs = form.querySelectorAll('input[type="url"]');
        urlInputs.forEach(input => {
            input.addEventListener('blur', () => {
                const value = input.value.trim();
                const fieldName = input.id === 'internal_address' ? 'Internal Address' : 'External Address';
                const isOptional = input.id === 'external_address';

                if (!value && isOptional) {
                    clearFieldError(input.id);
                    return;
                }

                if (!value && !isOptional) {
                    showFieldError(input.id, fieldName + ' is required. Please enter a valid URL.');
                    return;
                }

                if (!isValidUrl(value, isOptional)) {
                    showFieldError(input.id, getUrlErrorMessage(fieldName, value));
                } else {
                    // Additional validation for localhost without port
                    try {
                        const parsed = new URL(value);
                        if ((parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') && !parsed.port) {
                            showFieldError(input.id, fieldName + ' using localhost must include a port (e.g., http://localhost:8080).');
                            return;
                        }
                        // External address cannot use localhost
                        if (input.id === 'external_address' && (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1')) {
                            showFieldError(input.id, 'External Address cannot use localhost or 127.0.0.1. Use your public IP or domain name.');
                            return;
                        }
                    } catch (e) {
                        // URL parsing failed, already handled above
                    }
                    clearFieldError(input.id);
                }
            });

            // Clear error on input
            input.addEventListener('input', () => {
                if (input.getAttribute('aria-invalid') === 'true') {
                    clearFieldError(input.id);
                }
            });
        });

        // Timezone validation
        const timezoneSelect = document.getElementById('timezone');
        if (timezoneSelect) {
            timezoneSelect.addEventListener('change', () => {
                if (timezoneSelect.value) {
                    clearFieldError('timezone');
                }
            });

            timezoneSelect.addEventListener('blur', () => {
                if (!timezoneSelect.value) {
                    showFieldError('timezone', 'Please select a valid timezone from the dropdown.');
                }
            });
        }

        // Form submission with validation
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            // Clear previous errors
            clearAllErrors();
            feedback.className = 'form-feedback';
            feedback.textContent = '';

            // Validate all fields before submission
            let hasErrors = false;
            const formData = new FormData(form);
            const data = Object.fromEntries(formData);

            // Validate internal_address
            const internalValue = (data.internal_address || '').trim();
            if (!internalValue) {
                showFieldError('internal_address', 'Internal Address is required. Please enter the URL Radarr/Sonarr will use to connect to Kuasarr.');
                hasErrors = true;
            } else if (!isValidUrl(internalValue)) {
                showFieldError('internal_address', 'Internal Address must be a valid URL starting with http:// or https://');
                hasErrors = true;
            } else {
                try {
                    const parsed = new URL(internalValue);
                    if ((parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') && !parsed.port) {
                        showFieldError('internal_address', 'Internal Address using localhost must include a port (e.g., http://localhost:8080).');
                        hasErrors = true;
                    }
                } catch (e) {
                    showFieldError('internal_address', 'Internal Address must be a valid URL starting with http:// or https://');
                    hasErrors = true;
                }
            }

            // Validate external_address (optional)
            const externalValue = (data.external_address || '').trim();
            if (externalValue) {
                if (!isValidUrl(externalValue, true)) {
                    showFieldError('external_address', 'External Address must be a valid URL starting with http:// or https:// Leave empty if not using external access.');
                    hasErrors = true;
                } else {
                    try {
                        const parsed = new URL(externalValue);
                        if (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') {
                            showFieldError('external_address', 'External Address cannot use localhost or 127.0.0.1. Use your public IP or domain name.');
                            hasErrors = true;
                        }
                    } catch (e) {
                        // Already handled above
                    }
                }
            }

            // Validate timezone
            const timezoneValue = (data.timezone || '').trim();
            if (!timezoneValue) {
                showFieldError('timezone', 'Timezone is required. Please select a valid timezone from the dropdown.');
                hasErrors = true;
            }

            if (hasErrors) {
                feedback.classList.add('error');
                feedback.textContent = 'Please correct the errors above before saving.';
                // Focus first error field
                const firstError = form.querySelector('[aria-invalid="true"]');
                if (firstError) firstError.focus();
                return;
            }

            // Set loading state
            submitBtn.setAttribute('aria-busy', 'true');
            submitBtn.disabled = true;

            try {
                const headers = { 'Content-Type': 'application/json' };
                // Sprint H5: Include CSRF token in request header
                if (csrfToken) {
                    headers['X-CSRF-Token'] = csrfToken;
                }

                const response = await kuasarrApiFetch('/api/settings/core', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(data)
                });

                let result;
                try {
                    result = await response.json();
                } catch (parseError) {
                    throw new Error('Invalid response from server. Please try again.');
                }

                if (response.ok && result.success) {
                    feedback.classList.add('success');
                    let message = result.message || 'Settings saved successfully!';
                    if (result.warning) {
                        message += ' (' + result.warning + ')';
                    }
                    feedback.textContent = message;
                } else {
                    feedback.classList.add('error');

                    // Handle field-specific errors from server
                    if (result.errors && typeof result.errors === 'object') {
                        Object.keys(result.errors).forEach(fieldName => {
                            showFieldError(fieldName, result.errors[fieldName]);
                        });
                        feedback.textContent = result.error || 'Validation failed. Please correct the errors above.';
                    } else {
                        feedback.textContent = result.error || 'Failed to save settings. Please try again.';
                    }
                }
            } catch (err) {
                feedback.classList.add('error');
                if (err.name === 'TypeError' && err.message.includes('fetch')) {
                    feedback.textContent = 'Network error: Unable to connect to server. Please check your connection and try again.';
                } else if (err.name === 'AbortError') {
                    feedback.textContent = 'Request timed out. Please try again.';
                } else {
                    feedback.textContent = err.message || 'An unexpected error occurred. Please try again.';
                }
            } finally {
                submitBtn.setAttribute('aria-busy', 'false');
                submitBtn.disabled = false;
            }
        });
    }

    initializeCoreSettingsForm();
    </script>
    """

    # Form-specific CSS styles
    form_css = """
    <style>
    /* Form Container */
    .form-container {
        max-width: 480px;
        margin: 0 auto;
        text-align: left;
    }

    /* Form Groups */
    .form-group {
        margin-bottom: 1.5rem;
    }

    .form-group:last-of-type {
        margin-bottom: 2rem;
    }

    /* Labels */
    .form-label {
        display: block;
        font-weight: 600;
        font-size: 0.875rem;
        color: var(--fg-color);
        margin-bottom: 0.5rem;
    }

    .form-label .required {
        color: var(--error-color);
        margin-left: 0.25rem;
    }

    .form-label .optional {
        color: var(--text-muted);
        font-weight: 400;
        font-size: 0.8rem;
        margin-left: 0.25rem;
    }

    /* Inputs */
    .form-input,
    .form-select {
        width: 100%;
        padding: 0.625rem 0.875rem;
        font-size: 1rem;
        line-height: 1.5;
        color: var(--fg-color);
        background-color: var(--card-bg);
        border: 1.5px solid var(--border-color);
        border-radius: var(--border-radius);
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
        box-sizing: border-box;
    }

    .form-input:hover,
    .form-select:hover {
        border-color: var(--primary-hover);
    }

    .form-input:focus,
    .form-select:focus {
        outline: none;
        border-color: var(--primary);
        box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.15);
    }

    /* Dark mode focus ring */
    @media (prefers-color-scheme: dark) {
        .form-input:focus,
        .form-select:focus {
            box-shadow: 0 0 0 3px rgba(77, 143, 212, 0.25);
        }
    }

    :root[data-theme="dark"] .form-input:focus,
    :root[data-theme="dark"] .form-select:focus {
        box-shadow: 0 0 0 3px rgba(77, 143, 212, 0.25);
    }

    /* Help Text */
    .form-help {
        display: block;
        margin-top: 0.375rem;
        font-size: 0.8rem;
        color: var(--text-muted);
        line-height: 1.4;
    }

    /* Form Actions */
    .form-actions {
        display: flex;
        flex-direction: column;
        gap: 1rem;
        align-items: flex-start;
    }

    /* Button with Loading State */
    .btn-primary {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        min-width: 140px;
    }

    .btn-primary[aria-busy="true"] .btn-text {
        opacity: 0;
    }

    .btn-primary[aria-busy="true"] .btn-spinner {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        position: absolute;
    }

    .btn-spinner {
        display: none;
    }

    .spinner {
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }

    @media (prefers-reduced-motion: reduce) {
        .spinner {
            animation: none;
        }
    }

    /* Form Feedback */
    .form-feedback {
        padding: 0.75rem 1rem;
        border-radius: var(--border-radius);
        font-size: 0.875rem;
        font-weight: 500;
        width: 100%;
        box-sizing: border-box;
    }

    .form-feedback.success {
        background-color: var(--success-bg);
        color: var(--success-color);
        border: 1px solid var(--success-border);
    }

    .form-feedback.error {
        background-color: var(--error-bg);
        color: var(--error-color);
        border: 1px solid var(--error-border);
    }

    .form-feedback:empty {
        display: none;
    }

    /* Validation States */
    .form-input:invalid:not(:placeholder-shown) {
        border-color: var(--error-color);
    }

    .form-input:invalid:not(:placeholder-shown):focus {
        box-shadow: 0 0 0 3px rgba(220, 53, 69, 0.15);
    }

    /* Field Error Messages */
    .field-error {
        display: none;
        margin-top: 0.375rem;
        padding: 0.5rem 0.75rem;
        background-color: var(--error-bg);
        color: var(--error-color);
        border: 1px solid var(--error-border);
        border-radius: var(--border-radius);
        font-size: 0.8rem;
        font-weight: 500;
        line-height: 1.4;
    }

    .field-error[role="alert"] {
        display: block;
    }

    .form-input.has-error,
    .form-select.has-error {
        border-color: var(--error-color);
        background-color: rgba(220, 53, 69, 0.05);
    }

    .form-input.has-error:focus,
    .form-select.has-error:focus {
        box-shadow: 0 0 0 3px rgba(220, 53, 69, 0.15);
    }

    /* Dark mode error styles */
    @media (prefers-color-scheme: dark) {
        .form-input.has-error,
        .form-select.has-error {
            background-color: rgba(252, 129, 129, 0.1);
        }
    }

    :root[data-theme="dark"] .form-input.has-error,
    :root[data-theme="dark"] .form-select.has-error {
        background-color: rgba(252, 129, 129, 0.1);
    }

    /* Mobile Optimization */
    @media (max-width: 480px) {
        .form-container {
            padding: 0 0.5rem;
        }

        .form-input,
        .form-select {
            font-size: 16px; /* Prevents iOS zoom */
        }

        .form-actions {
            width: 100%;
        }

        .btn-primary {
            width: 100%;
        }
    }
    </style>
    """

    return render_form(
        header="Core Settings",
        form=form_css + form_html,
        script=script,
        footer_content="",
        active_page="/settings"
    )


def render_category_selector(selected_category: str = "", id_prefix: str = "", required: bool = False) -> str:
    """Render a category dropdown selector.

    Args:
        selected_category: The currently selected category ID
        id_prefix: Prefix for element IDs to avoid conflicts
        required: Whether the field is required

    Returns:
        HTML string for the category selector
    """
    from kuasarr.providers import shared_state

    required_attr = ' required' if required else ''
    required_mark = ' <span class="required">*</span>' if required else ''

    # Get categories from database
    try:
        db = shared_state.get_db("categories")
        raw_data = db.retrieve_all_titles()
        categories = []
        for key, value in raw_data:
            try:
                import json
                category = json.loads(value)
                categories.append(category)
            except json.JSONDecodeError:
                continue
        categories = sorted(categories, key=lambda x: x.get('name', ''))
    except Exception:
        categories = []

    options = '<option value="">-- Select Category --</option>'
    for cat in categories:
        selected = ' selected' if cat.get('id') == selected_category else ''
        options += f'<option value="{cat.get("id", "")}"{selected}>{html.escape(cat.get("name", ""))}</option>'

    select_id = f"{id_prefix}category" if id_prefix else "category"

    return f"""
    <div class="form-group">
        <label for="{select_id}">Category{required_mark}</label>
        <select id="{select_id}" name="category" class="form-select"{required_attr}>
            {options}
        </select>
        <div class="field-error" id="{select_id}-error"></div>
    </div>
    """


def get_categories_for_selector() -> list:
    """Get categories formatted for selector use.

    Returns:
        List of dicts with 'id', 'name', 'download_path' keys
    """
    from kuasarr.providers import shared_state

    try:
        db = shared_state.get_db("categories")
        raw_data = db.retrieve_all_titles()
        categories = []
        for key, value in raw_data:
            try:
                import json
                category = json.loads(value)
                categories.append({
                    'id': category.get('id', ''),
                    'name': category.get('name', ''),
                    'download_path': category.get('download_path', '')
                })
            except json.JSONDecodeError:
                continue
        return sorted(categories, key=lambda x: x['name'])
    except Exception:
        return []

