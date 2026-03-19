# -*- coding: utf-8 -*-
# Quasarr
# Project by https://github.com/rix1337

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
        return render_form("Hostnames", hostname_form_html(shared_state, message) + back_button)

    @app.post("/api/hostnames")
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
        return render_form("Configure Captcha Service", form_html, js)

    @app.post('/api/dbc_credentials')
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
        return render_form("Global Settings", form_html)

    @app.post('/api/settings')
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
