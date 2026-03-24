# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

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
                gap: 0.25rem;
                flex-wrap: wrap;
                justify-content: center;
                margin-bottom: 1.5rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid var(--divider-color);
            }
            .nav-link {
                padding: 0.35rem 0.75rem;
                border-radius: var(--border-radius);
                font-size: 0.875rem;
                color: var(--text-muted);
                transition: background 0.15s, color 0.15s;
                text-decoration: none;
            }
            .nav-link:hover {
                background: var(--btn-subtle-bg);
                color: var(--fg-color);
                text-decoration: none;
            }
            .nav-active {
                background: var(--btn-subtle-bg);
                color: var(--fg-color);
                font-weight: 600;
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
        ("/captcha-config", "CAPTCHA"),
        ("/hosters", "Hosters"),
        ("/notifications", "Notifications"),
    ]
    items = "".join(
        f'<a href="{url}" class="nav-link{"  nav-active" if url == active_page else ""}">{label}</a>'
        for url, label in pages
    )
    return f'<nav class="top-nav">{items}</nav>'


def render_form(header, form="", script="", footer_content="", active_page=""):
    nav = render_nav(active_page)
    content = f'''
    <h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    {nav}
    <h2>{header}</h2>
    {form}
    {script}
    '''
    return render_centered_html(content, footer_content)


def render_success(message, timeout=5, optional_text=""):
    button_html = render_button("Go to Home", "primary", {"id": "nextButton"})
    script = f'''
        <script>
            let counter = {timeout};
            const btn = document.getElementById('nextButton');
            const info = document.getElementById('redirect-info');
            const interval = setInterval(() => {{
                counter--;
                if (info) info.textContent = `Redirecting in ${{counter}}s...`;
                if (counter === 0) {{
                    clearInterval(interval);
                    window.location.href = '/';
                }}
            }}, 1000);
            btn.onclick = () => {{ clearInterval(interval); window.location.href = '/'; }};
        </script>
    '''
    content = f'''<h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    <h2>{message}</h2>
    {optional_text}
    <p id="redirect-info" style="color:var(--text-muted);font-size:0.85rem;">Redirecting in {timeout}s...</p>
    {button_html}
    {script}
    '''
    return render_centered_html(content)


def render_success_no_wait(message, optional_text=""):
    button_html = render_button("Continue", "primary", {"onclick": "window.location.href='/'"})
    content = f'''<h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    <h2>{message}</h2>
    {optional_text}
    {button_html}
    '''
    return render_centered_html(content)


def render_fail(message):
    button_html = render_button("Back", "secondary", {"onclick": "window.location.href='/'"})
    return render_centered_html(f"""<h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
        <h2>{message}</h2>
        {button_html}
    """)
