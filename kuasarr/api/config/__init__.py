# -*- coding: utf-8 -*-
# Quasarr
# Project by https://github.com/rix1337

from kuasarr.providers.auth import require_api_key, require_csrf_token, rate_limit, get_csrf_token
from kuasarr.providers.ui.html_templates import render_form, render_button, render_success
from kuasarr.storage.setup import hostname_form_html, save_hostnames, dbc_credentials_config


def setup_config(app, shared_state):
    @app.get('/hostnames')
    def hostnames_ui():
        message = """<p>
            At least one hostname must be kept.
        </p>"""
        back_button = f'''<p>
                        {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
                    </p>'''
        return render_form("Hostnames", hostname_form_html(shared_state, message) + back_button, active_page="/hosters")

    @app.post("/api/hostnames")
    @require_api_key
    def hostnames_api():
        return save_hostnames(shared_state, timeout=1, first_run=False)

    @app.get('/captcha-config')
    def captcha_config_ui():
        # Reuse the form logic from setup.py but wrapped for the main UI
        from kuasarr.storage.config import Config
        captcha_cfg = Config('Captcha')
        default_service = (captcha_cfg.get('service') or 'dbc').lower().strip()
        default_authtoken = captcha_cfg.get('dbc_authtoken') or ""
        default_twocaptcha = captcha_cfg.get('twocaptcha_api_key') or ""

        form_html = f'''
        <p>Choose your captcha service and provide credentials.</p>
        <form action="/api/dbc_credentials" method="post" id="captchaForm">
            <label for="service">Captcha Service</label>
            <select id="service" name="service" onchange="toggleFields()">
                <option value="dbc" {'selected' if default_service == 'dbc' else ''}>DeathByCaptcha</option>
                <option value="2captcha" {'selected' if default_service == '2captcha' else ''}>2Captcha (50% cheaper for CutCaptcha)</option>
            </select><br><br>
            
            <div id="dbc_fields" style="display: {'block' if default_service == 'dbc' else 'none'};">
                <label for="authtoken">DBC API Token</label>
                <input type="text" id="authtoken" name="authtoken" placeholder="your_api_token" value="{default_authtoken}">
                <p class="small">Get your token at <a href="https://deathbycaptcha.com" target="_blank">deathbycaptcha.com</a></p>
            </div>

            <div id="twocaptcha_fields" style="display: {'block' if default_service == '2captcha' else 'none'};">
                <label for="twocaptcha_api_key">2Captcha API Key</label>
                <input type="text" id="twocaptcha_api_key" name="twocaptcha_api_key" placeholder="your_2captcha_key" value="{default_twocaptcha}">
                <p class="small">Get your key at <a href="https://2captcha.com" target="_blank">2captcha.com</a></p>
            </div>

            <br>
            {render_button("Save", "primary", {"type": "submit"})}
            {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
        </form>

        <style>
            .small {{ font-size: 0.85rem; color: #666; margin-top: 0.25rem; }}
            #captchaForm label {{ display: block; margin-bottom: 0.5rem; font-weight: 600; }}
            #captchaForm input, #captchaForm select {{ width: 100%; padding: 0.5rem; margin-bottom: 1rem; border: 1px solid #ccc; border-radius: 4px; }}
        </style>
        '''

        js = '''
        <script>
        function toggleFields() {
            var service = document.getElementById('service').value;
            document.getElementById('dbc_fields').style.display = (service === 'dbc') ? 'block' : 'none';
            document.getElementById('twocaptcha_fields').style.display = (service === '2captcha') ? 'block' : 'none';
        }
        </script>
        '''
        return render_form("Configure Captcha Service", form_html, js, active_page="/captcha-config")

    @app.post('/api/dbc_credentials')
    @require_api_key
    def set_dbc_credentials():
        from bottle import response, redirect
        from kuasarr.storage.config import Config
        import kuasarr.providers.web_server
        
        service = (request.forms.get("service") or "dbc").strip()
        authtoken = (request.forms.get("authtoken") or "").strip()
        twocaptcha_key = (request.forms.get("twocaptcha_api_key") or "").strip()

        config = Config('Captcha')
        config.save("service", service)
        config.save("dbc_authtoken", authtoken)
        config.save("twocaptcha_api_key", twocaptcha_key)

        # Update shared state immediately
        shared_state.update("captcha_service", service)
        shared_state.update("twocaptcha_api_key", twocaptcha_key)
        
        dbc_config = shared_state.values.get("dbc_config", {})
        dbc_config["authtoken"] = authtoken
        shared_state.update("dbc_config", dbc_config)
        
        # Enable if any credentials are set
        shared_state.update("dbc_enabled", bool(authtoken or twocaptcha_key))

    @app.get('/settings')
    def settings_ui():
        from kuasarr.storage.config import Config
        sections_html = []
        
        # Sections to exclude from the general settings page (they have special UIs or are internal)
        exclude_sections = ['Hostnames', 'PWA', 'Connection', 'API', 'BlockedHosters']
        
        for section_name, params in Config._DEFAULT_CONFIG.items():
            if section_name in exclude_sections:
                continue
                
            config = Config(section_name)
            fields_html = []
            
            for key, key_type, default_val in params:
                value = config.get(key)
                if key_type == 'bool':
                    checked = 'checked' if value else ''
                    fields_html.append(f'''
                        <div class="field-row">
                            <label for="{section_name}_{key}">{key.replace("_", " ").title()}</label>
                            <input type="checkbox" id="{section_name}_{key}" name="{section_name}:{key}" {checked}>
                        </div>
                    ''')
                elif key_type == 'secret':
                    # Mask secrets but allow editing
                    display_val = "" if not value else "********"
                    fields_html.append(f'''
                        <div class="field-row">
                            <label for="{section_name}_{key}">{key.replace("_", " ").title()}</label>
                            <input type="password" id="{section_name}_{key}" name="{section_name}:{key}" placeholder="Enter to change..." value="">
                            <small>Leave empty to keep existing value</small>
                        </div>
                    ''')
                else:
                    fields_html.append(f'''
                        <div class="field-row">
                            <label for="{section_name}_{key}">{key.replace("_", " ").title()}</label>
                            <input type="text" id="{section_name}_{key}" name="{section_name}:{key}" value="{value or ""}">
                        </div>
                    ''')
            
            if fields_html:
                sections_html.append(f'''
                    <div class="settings-card">
                        <h3>{section_name}</h3>
                        {"".join(fields_html)}
                    </div>
                ''')

        form_html = f'''
        <form action="/api/settings" method="post" id="settingsForm">
            {"".join(sections_html)}
            <div class="actions">
                {render_button("Save All Settings", "primary", {"type": "submit"})}
                {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
            </div>
        </form>

        <style>
            .settings-card {{
                background: var(--card-bg);
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 1.5rem;
                margin-bottom: 1.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }}
            .settings-card h3 {{
                margin-top: 0;
                margin-bottom: 1.2rem;
                border-bottom: 2px solid #eee;
                padding-bottom: 0.5rem;
                color: #333;
            }}
            .field-row {{
                margin-bottom: 1rem;
            }}
            .field-row label {{
                display: block;
                font-weight: 600;
                margin-bottom: 0.4rem;
                font-size: 0.95rem;
            }}
            .field-row input[type="text"], 
            .field-row input[type="password"] {{
                width: 100%;
                padding: 0.6rem;
                border: 1px solid #ccc;
                border-radius: 4px;
                box-sizing: border-box;
            }}
            .field-row input[type="checkbox"] {{
                width: 20px;
                height: 20px;
            }}
            .field-row small {{
                color: #777;
                font-size: 0.8rem;
            }}
            .actions {{
                margin-top: 2rem;
                display: flex;
                gap: 1rem;
                justify-content: center;
            }}
            body.dark .settings-card {{
                background: #2d3748;
                border-color: #4a5568;
            }}
            body.dark .settings-card h3 {{
                color: #edf2f7;
                border-bottom-color: #4a5568;
            }}
            body.dark .field-row label {{
                color: #e2e8f0;
            }}
            body.dark .field-row input[type="text"],
            body.dark .field-row input[type="password"] {{
                background: #1a202c;
                color: white;
                border-color: #4a5568;
            }}
        </style>
        '''
        return render_form("Global Settings", form_html, active_page="/settings")

    @app.post('/api/settings')
    @require_api_key
    def save_settings_api():
        from kuasarr.storage.config import Config
        forms = request.forms
        
        # Group by section
        updates = {}
        for full_key in forms.keys():
            if ":" not in full_key:
                continue
            section, key = full_key.split(":", 1)
            if section not in updates:
                updates[section] = {}
            updates[section][key] = forms.get(full_key)

        # Handle checkboxes (if not in forms, they are False)
        for section_name, params in Config._DEFAULT_CONFIG.items():
            if section_name in ['Hostnames', 'PWA', 'Connection', 'API', 'BlockedHosters']:
                continue
            for key, key_type, _ in params:
                if key_type == 'bool':
                    full_key = f"{section_name}:{key}"
                    val = forms.get(full_key)
                    is_checked = (val == 'on')
                    Config(section_name).save(key, "true" if is_checked else "false")
                elif key_type == 'secret':
                    new_val = updates.get(section_name, {}).get(key)
                    if new_val and new_val.strip(): # Only update if not empty
                        Config(section_name).save(key, new_val.strip())
                else:
                    new_val = updates.get(section_name, {}).get(key)
                    if new_val is not None:
                        Config(section_name).save(key, new_val.strip())

        return render_success("All settings saved successfully! Some changes might require a restart.", 5)

    # ============================================================================
    # Sprint H1/H3 — Core Settings API with Enhanced Validation
    # ============================================================================

    @app.get('/api/settings/core')
    @require_api_key
    def get_core_settings():
        """Returns current core settings: internal_address, external_address, timezone"""
        from bottle import response
        import json
        from kuasarr.storage.config import Config

        config = Config('Connection')
        internal_address = config.get('internal_address') or shared_state.values.get('internal_address', '')
        external_address = config.get('external_address') or shared_state.values.get('external_address', '')
        timezone = config.get('timezone') or 'Europe/Berlin'

        response.content_type = 'application/json'
        return json.dumps({
            "internal_address": internal_address,
            "external_address": external_address,
            "timezone": timezone
        })

    @app.post('/api/settings/core')
    @require_api_key
    @require_csrf_token
    @rate_limit(max_requests=5, window=60)  # Sprint H5: Rate limiting - 5 requests per minute
    def save_core_settings():
        """Saves core settings to kuasarr.ini with enhanced security validation (Sprint H5)"""
        from bottle import response, request
        import json
        import re
        import socket
        from urllib.parse import urlparse
        from zoneinfo import available_timezones
        from kuasarr.storage.config import Config
        from kuasarr.providers.log import audit_core_settings_change, audit_security_event

        response.content_type = 'application/json'

        # Get client IP for audit logging
        client_ip = request.environ.get('REMOTE_ADDR', 'unknown')

        # Read POST JSON body
        try:
            payload = request.json or {}
        except Exception:
            response.status = 400
            return json.dumps({"success": False, "error": "Invalid JSON body. Please ensure you're sending valid JSON."})

        internal_address = (payload.get('internal_address') or '').strip()
        external_address = (payload.get('external_address') or '').strip()
        timezone = (payload.get('timezone') or '').strip()

        errors = {}

        # Sprint H5: Enhanced URL validation with security checks
        def _is_valid_url(url, allow_empty=False, is_external=False):
            """Validate URL with security checks for SSRF prevention."""
            if not url:
                return allow_empty
            try:
                parsed = urlparse(url)

                # Check scheme - only http/https allowed
                if parsed.scheme not in ('http', 'https'):
                    return False

                # Must have a netloc (hostname)
                if not parsed.netloc:
                    return False

                # Sprint H5: Reject URLs with userinfo (http://user:pass@host)
                if parsed.username or parsed.password:
                    return False

                # Sprint H5: Reject file://, ftp://, etc. (already handled by scheme check)
                # Additional check for dangerous schemes in the URL
                dangerous_schemes = ('file', 'ftp', 'sftp', 'ssh', 'telnet', 'ldap', 'gopher')
                if parsed.scheme in dangerous_schemes:
                    return False

                hostname = parsed.hostname
                if not hostname:
                    return False

                # Sprint H5: Reject localhost/127.0.0.0/8 for external_address
                if is_external:
                    localhost_patterns = [
                        'localhost', '127.', '0.0.0.0', '::1',
                        '[::1]', '[0:0:0:0:0:0:0:1]'
                    ]
                    if any(hostname.startswith(p) or hostname == p.rstrip('.') for p in localhost_patterns):
                        return False

                    # Check for private IP ranges
                    try:
                        import ipaddress
                        ip = ipaddress.ip_address(hostname)
                        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
                            return False
                    except ValueError:
                        # Not an IP address, that's fine
                        pass

                # Sprint H5: Prevent SSRF by validating against internal metadata services
                blocked_hosts = [
                    '169.254.169.254',  # AWS, Azure, GCP metadata
                    'metadata.google.internal',
                    'metadata.google.internal.',
                    'instance-data',     # AWS
                    'metadata',          # Generic
                    'alibaba.xxx',       # Alibaba Cloud
                ]
                hostname_lower = hostname.lower()
                for blocked in blocked_hosts:
                    if blocked in hostname_lower:
                        return False

                return True
            except Exception:
                return False

        def _get_url_error_message(field_name, is_external=False):
            base_msg = f"{field_name} must be a valid URL starting with http:// or https://"
            if is_external:
                base_msg += " Cannot use localhost, private IPs, or cloud metadata endpoints."
            return base_msg

        # Sprint H5: Sanitize URL inputs (prevent XSS in URL fields)
        def _sanitize_url(url):
            """Sanitize URL to prevent XSS."""
            if not url:
                return url
            # Remove any HTML/script tags
            url = re.sub(r'<[^>]+>', '', url)
            # Remove null bytes
            url = url.replace('\x00', '')
            # Remove control characters
            url = ''.join(char for char in url if ord(char) >= 32 or char in '\t\n\r')
            return url.strip()

        internal_address = _sanitize_url(internal_address)
        external_address = _sanitize_url(external_address)

        # Validate internal_address (required)
        if not internal_address:
            errors['internal_address'] = "Internal Address is required. Please enter the URL Radarr/Sonarr will use to connect to Kuasarr."
        elif not _is_valid_url(internal_address, is_external=False):
            errors['internal_address'] = _get_url_error_message("Internal Address")
        else:
            # Additional check: validate URL components more thoroughly
            try:
                parsed = urlparse(internal_address)
                # Check for common mistakes
                if parsed.hostname in ['localhost', '127.0.0.1'] and not parsed.port:
                    errors['internal_address'] = "Internal Address using localhost must include a port (e.g., http://localhost:8080)."
            except Exception:
                pass

        # Validate external_address (optional but must be valid if provided)
        if external_address:
            if not _is_valid_url(external_address, allow_empty=True, is_external=True):
                errors['external_address'] = _get_url_error_message("External Address", is_external=True) + " Leave empty if not using external access."

        # Validate timezone against IANA timezone database
        if timezone:
            valid_timezones = available_timezones()
            if timezone not in valid_timezones:
                errors['timezone'] = f"'{timezone}' is not a valid timezone. Please select a valid IANA timezone identifier (e.g., Europe/Berlin, America/New_York)."
        else:
            errors['timezone'] = "Timezone is required. Please select a valid timezone from the dropdown."

        # Return all validation errors if any
        if errors:
            response.status = 400
            audit_security_event('validation_failure', f"Core settings validation failed: {errors}", ip=client_ip)
            return json.dumps({
                "success": False,
                "errors": errors,
                "error": "Validation failed. Please correct the errors below."
            })

        # Get old values for audit logging
        config = Config('Connection')
        old_internal = config.get('internal_address') or ''
        old_external = config.get('external_address') or ''
        old_timezone = config.get('timezone') or 'Europe/Berlin'

        # Track what changed
        internal_changed = (old_internal != internal_address)
        external_changed = (old_external != external_address)
        timezone_changed = (old_timezone != timezone)

        # Optional: Check if internal_address is reachable (best effort, don't fail if check errors)
        reachability_warning = None
        try:
            parsed = urlparse(internal_address)
            hostname = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            if hostname and hostname not in ['localhost', '127.0.0.1']:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((hostname, port))
                sock.close()
                if result != 0:
                    # Not reachable, but don't fail - just log warning in response
                    reachability_warning = f"Warning: Could not connect to {hostname}:{port}. Ensure this address is reachable from your network."
        except Exception:
            pass  # Silently ignore reachability check failures

        # Save to Config
        config.save('internal_address', internal_address)
        config.save('external_address', external_address)
        config.save('timezone', timezone)

        # Update shared_state.values
        shared_state.update('internal_address', internal_address)
        shared_state.update('external_address', external_address)
        shared_state.update('timezone', timezone)

        # Sprint H5: Audit logging - log settings changes
        if internal_changed or external_changed or timezone_changed:
            audit_core_settings_change(
                internal_address_changed=internal_changed,
                external_address_changed=external_changed,
                timezone_changed=timezone_changed,
                old_values={
                    'internal_address': old_internal,
                    'external_address': old_external,
                    'timezone': old_timezone
                },
                new_values={
                    'internal_address': internal_address,
                    'external_address': external_address,
                    'timezone': timezone
                },
                user=client_ip
            )

        # Notify observers of core settings change (Sprint H4: Live-Update without Restart)
        try:
            from kuasarr.providers.settings_observer import notify_core_settings_changed
            notify_core_settings_changed({
                'internal_address': internal_address,
                'external_address': external_address,
                'timezone': timezone
            })
        except ImportError:
            pass  # settings_observer may not exist yet

        response_data = {
            "success": True,
            "message": "Core settings saved successfully",
            "settings": {
                "internal_address": internal_address,
                "external_address": external_address,
                "timezone": timezone
            }
        }

        if reachability_warning:
            response_data['warning'] = reachability_warning

        return json.dumps(response_data)

    @app.get('/settings/core')
    def core_settings_ui():
        """Render the Core Settings form (Sprint H2/H5 with CSRF protection)."""
        from kuasarr.providers.ui.html_templates import render_core_settings_form
        from kuasarr.storage.config import Config

        config = Config('Connection')
        internal_address = config.get('internal_address') or shared_state.values.get('internal_address', '')
        external_address = config.get('external_address') or shared_state.values.get('external_address', '')
        timezone = config.get('timezone') or 'Europe/Berlin'

        # Sprint H5: Generate CSRF token for the form
        csrf_token = get_csrf_token()

        return render_core_settings_form(
            internal_address=internal_address,
            external_address=external_address,
            timezone=timezone,
            csrf_token=csrf_token
        )
