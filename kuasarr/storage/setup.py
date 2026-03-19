# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import os
import sys

import requests
from bottle import Bottle, request, static_file

import kuasarr
import kuasarr.providers.ui.html_images as images
import kuasarr.providers.shared_state
import kuasarr.providers.web_server
from kuasarr.providers.ui.html_templates import render_button, render_form, render_success, render_fail
from kuasarr.providers.log import info
from kuasarr.providers import shared_state, web_server
from kuasarr.providers.shared_state import extract_valid_hostname
from kuasarr.providers.web_server import Server
from kuasarr.storage.config import Config

# Static files directory for PWA assets
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))


def add_static_route(app):
    """Add static file serving route to a Bottle app for PWA support."""
    @app.get('/static/<filename:path>')
    def serve_static(filename):
        mimetype = None
        if filename.endswith('.webmanifest'):
            mimetype = 'application/manifest+json'
        elif filename.endswith('.js'):
            mimetype = 'application/javascript'
        return static_file(filename, root=STATIC_DIR, mimetype=mimetype)

    @app.get('/pwa-install')
    def pwa_install():
        return static_file('pwa-install.html', root=STATIC_DIR)


def _validate_address(address):
    if not address:
        return False
    value = address.strip()
    return value.startswith("http://") or value.startswith("https://")


def path_config(shared_state):
    app = Bottle()
    add_static_route(app)

    current_path = os.path.dirname(os.path.abspath(sys.argv[0]))

    @app.get('/')
    def config_form():
        config_form_html = f'''
            <form action="/api/config" method="post">
                <label for="config_path">Path</label>
                <input type="text" id="config_path" name="config_path" placeholder="{current_path}"><br>
                {render_button("Save", "primary", {"type": "submit"})}
            </form>
            '''
        return render_form("Press 'Save' to set desired path for configuration",
                           config_form_html)

    def set_config_path(config_path):
        config_path_file = "kuasarr.conf"

        if not config_path:
            config_path = current_path

        config_path = config_path.replace("\\", "/")
        config_path = config_path[:-1] if config_path.endswith('/') else config_path

        if not os.path.exists(config_path):
            os.makedirs(config_path)

        with open(config_path_file, "w") as f:
            f.write(config_path)

        return config_path

    @app.post("/api/config")
    def set_config():
        config_path = request.forms.get("config_path")
        config_path = set_config_path(config_path)
        web_server.temp_server_success = True
        return render_success(f'Config path set to: "{config_path}"',
                              5)

    info(f"Starting web server for config at: \"{shared_state.values['internal_address']}\".")
    info("Please set desired config path there!")
    return Server(app, listen='0.0.0.0', port=shared_state.values['port']).serve_temporarily()


def connection_config(shared_state):
    app = Bottle()
    add_static_route(app)

    @app.get('/')
    def connection_form():
        connection_cfg = Config('Connection')
        default_internal = connection_cfg.get('internal_address') or shared_state.values.get("internal_address", "")
        default_external = connection_cfg.get('external_address') or shared_state.values.get("external_address", "")
        form_html = f'''
        <form action="/api/connection" method="post">
            <label for="internal_address">Internal URL (Radarr/Sonarr will use this)</label>
            <input type="text" id="internal_address" name="internal_address" placeholder="http://192.168.0.1:9999" value="{default_internal}"><br>

            <label for="external_address">External URL (used in notifications, defaults to internal)</label>
            <input type="text" id="external_address" name="external_address" placeholder="http://mydomain.example:9999" value="{default_external}"><br>

            {render_button("Save", "primary", {"type": "submit"})}
        </form>
        '''
        return render_form("Configure the base URLs Kuasarr will advertise.", form_html)

    @app.post("/api/connection")
    def set_connection():
        internal = (request.forms.get("internal_address") or "").strip()
        external = (request.forms.get("external_address") or "").strip()

        if not _validate_address(internal):
            return render_fail("Internal address must start with http:// or https://")

        if not external:
            external = internal

        if not _validate_address(external):
            return render_fail("External address must start with http:// or https://")

        config = Config('Connection')
        config.save("internal_address", internal)
        config.save("external_address", external)

        shared_state.set_connection_info(internal, external, shared_state.values['port'])

        kuasarr.providers.web_server.temp_server_success = True
        return render_success("Connection settings saved successfully!", 5)

    info(f'Starting connection setup server at: "{shared_state.values["internal_address"]}".')
    info("Please set the internal/external URL there!")
    return Server(app, listen='0.0.0.0', port=shared_state.values['port']).serve_temporarily()


def hostname_form_html(shared_state, message):
    hostname_fields = '''
    <label for="{id}" style="display:inline-flex; align-items:center; gap:4px;">{label}{img_html}</label>
    <input type="text" id="{id}" name="{id}" placeholder="example.com" autocorrect="off" autocomplete="off" value="{value}"><br>
    '''

    field_html = []
    hostnames = Config('Hostnames')  # Load once outside the loop
    for label in shared_state.values["sites"]:
        field_id = label.lower()
        img_html = ''
        try:
            img_data = getattr(images, field_id)
            if img_data:
                img_html = f' <img src="{img_data}" width="16" height="16" style="filter: blur(2px);" alt="{label} icon">'
        except AttributeError:
            pass

        # Get the current value (if any and non-empty)
        current_value = hostnames.get(field_id)
        if not current_value:
            current_value = ''  # Ensure it's empty if None or ""

        field_html.append(hostname_fields.format(
            id=field_id,
            label=label,
            img_html=img_html,
            value=current_value
        ))

    hostname_form_content = "".join(field_html)
    button_html = render_button("Save", "primary", {"type": "submit"})

    template = """
<div id="message" style="margin-bottom:0.5em;">{message}</div>
<div id="error-msg" style="color:red; margin-bottom:1em;"></div>

<form action="/api/hostnames" method="post" onsubmit="return validateHostnames(this)">
    {hostname_form_content}
    {button}
</form>

<script>
  function validateHostnames(form) {{
    var errorDiv = document.getElementById('error-msg');
    errorDiv.textContent = '';

    var inputs = form.querySelectorAll('input[type="text"]');
    for (var i = 0; i < inputs.length; i++) {{
      if (inputs[i].value.trim() !== '') {{
        return true;
      }}
    }}

    errorDiv.textContent = 'Please fill in at least one hostname!';
    inputs[0].focus();
    return false;
  }}
</script>
"""
    return template.format(
        message=message,
        hostname_form_content=hostname_form_content,
        button=button_html
    )


def save_hostnames(shared_state, timeout=5, first_run=True):
    hostnames = Config('Hostnames')

    # Collect submitted hostnames, validate, and track errors
    valid_domains = {}
    errors = {}

    for site_key in shared_state.values['sites']:
        shorthand = site_key.lower()
        raw_value = request.forms.get(shorthand)
        # treat missing or empty string as intentional clear, no validation
        if raw_value is None or raw_value.strip() == '':
            continue

        # non-empty submission: must validate
        result = extract_valid_hostname(raw_value, shorthand)
        domain = result.get('domain')
        message = result.get('message', 'Error checking the hostname you provided!')
        if domain:
            valid_domains[site_key] = domain
        else:
            errors[site_key] = message

    # Filter out any accidental empty domains and require at least one valid hostname overall
    valid_domains = {k: d for k, d in valid_domains.items() if d}
    if not valid_domains:
        # report last or generic message
        fail_msg = next(iter(errors.values()), 'No valid hostname provided!')
        return render_fail(fail_msg)

    # Save: valid ones, explicit empty for those omitted cleanly, leave untouched if error
    changed_sites = []
    for site_key in shared_state.values['sites']:
        shorthand = site_key.lower()
        raw_value = request.forms.get(shorthand)
        # determine if change applies
        if site_key in valid_domains:
            new_val = valid_domains[site_key]
            old_val = hostnames.get(shorthand) or ''
            if old_val != new_val:
                hostnames.save(shorthand, new_val)
                changed_sites.append(shorthand)
        elif raw_value is None:
            # no submission: leave untouched
            continue
        elif raw_value.strip() == '':
            old_val = hostnames.get(shorthand) or ''
            if old_val != '':
                hostnames.save(shorthand, '')

    kuasarr.providers.web_server.temp_server_success = True

    # Build success message, include any per-site errors
    success_msg = 'At least one valid hostname set!'
    if errors:
        optional_text = "<br>".join(f"{site}: {msg}" for site, msg in errors.items()) + "<br>"
    else:
        optional_text = "All provided hostnames are valid.<br>"

    if not first_run:
        # Append restart notice for specific sites that actually changed
        for site in changed_sites:
            if site.lower() in {'al', 'dd', 'nx'}:
                optional_text += f"{site.upper()}: You must restart Quasarr and follow additional steps to start using this site.<br>"

    return render_success(success_msg, timeout, optional_text=optional_text)


def hostnames_config(shared_state):
    app = Bottle()
    add_static_route(app)

    @app.get('/')
    def hostname_form():
        message = """<p>
          If you're having trouble setting this up, take a closer look at 
          <a href="https://github.com/rix1337/Quasarr?tab=readme-ov-file#instructions" target="_blank" rel="noopener noreferrer">
            step one of these instructions.
          </a>
        </p>"""
        return render_form("Set at least one valid hostname", hostname_form_html(shared_state, message))

    @app.post("/api/hostnames")
    def set_hostnames():
        return save_hostnames(shared_state)

    info(f"Hostnames not set. Starting web server for config at: \"{shared_state.values['internal_address']}\".")
    info("Please set at least one valid hostname there!")
    return Server(app, listen='0.0.0.0', port=shared_state.values['port']).serve_temporarily()


def dbc_credentials_config(shared_state):
    app = Bottle()
    add_static_route(app)

    @app.get('/')
    def credentials_form():
        captcha_cfg = Config('Captcha')
        default_service = (captcha_cfg.get('service') or 'dbc').lower().strip()
        default_authtoken = captcha_cfg.get('dbc_authtoken') or ""
        default_twocaptcha = captcha_cfg.get('twocaptcha_api_key') or ""
        
        form_html = f'''
        <p>Choose your captcha service and provide your API token.</p>
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
            {render_button("Skip", "secondary", {"type": "submit", "name": "skip", "value": "1"})}
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
        if request.forms.get("skip"):
            kuasarr.providers.web_server.temp_server_success = True
            return render_success("Skipped captcha setup. You can configure it later via the Kuasarr UI.", 5)

        service = (request.forms.get("service") or "dbc").strip()
        authtoken = (request.forms.get("authtoken") or "").strip()
        twocaptcha_key = (request.forms.get("twocaptcha_api_key") or "").strip()

        if service == "2captcha" and not twocaptcha_key:
            return render_fail("Provide 2Captcha API key.")
        if service == "dbc" and not authtoken:
            return render_fail("Provide DBC API token.")

        config = Config('Captcha')
        config.save("service", service)
        config.save("dbc_authtoken", authtoken)
        config.save("twocaptcha_api_key", twocaptcha_key)

        kuasarr.providers.web_server.temp_server_success = True
        return render_success("Captcha credentials saved!", 5)

    info("starting captcha credential setup...")
    info(f"at: \"{shared_state.values['internal_address']}\"")
    info("Please enter your DeathByCaptcha or 2Captcha API token there!")
    info("Need one? Get yours here:")
    info("DeathByCaptcha: https://deathbycaptcha.com?refid=1237432788a")
    info("2Captcha: https://2captcha.com/?from=26376359")
    return Server(app, listen='0.0.0.0', port=shared_state.values['port']).serve_temporarily()


def hostname_credentials_config(shared_state, shorthand, domain):
    app = Bottle()
    add_static_route(app)

    shorthand = shorthand.upper()

    @app.get('/')
    def credentials_form():
        form_content = f'''
        <span>If required register account at: <a href="https://{domain}">{domain}</a>!</span><br><br>
        <label for="user">Username</label>
        <input type="text" id="user" name="user" placeholder="User" autocorrect="off"><br>

        <label for="password">Password</label>
        <input type="password" id="password" name="password" placeholder="Password"><br>
        '''

        form_html = f'''
        <form action="/api/credentials/{shorthand}" method="post">
            {form_content}
            {render_button("Save", "primary", {"type": "submit"})}
        </form>
        '''

        return render_form(f"Set User and Password for {shorthand}", form_html)

    @app.post("/api/credentials/<sh>")
    def set_credentials(sh):
        user = request.forms.get('user')
        password = request.forms.get('password')
        config = Config(shorthand)

        if user and password:
            config.save("user", user)
            config.save("password", password)

            if sh.lower() == "al":
                if kuasarr.providers.sessions.al.create_and_persist_session(shared_state):
                    kuasarr.providers.web_server.temp_server_success = True
                    return render_success(f"{sh} credentials set successfully", 5)
            if sh.lower() == "dd":
                if kuasarr.providers.sessions.dd.create_and_persist_session(shared_state):
                    kuasarr.providers.web_server.temp_server_success = True
                    return render_success(f"{sh} credentials set successfully", 5)
            if sh.lower() == "dl":
                if kuasarr.providers.sessions.dl.create_and_persist_session(shared_state):
                    kuasarr.providers.web_server.temp_server_success = True
                    return render_success(f"{sh} credentials set successfully", 5)
            if sh.lower() == "nx":
                if kuasarr.providers.sessions.nx.create_and_persist_session(shared_state):
                    kuasarr.providers.web_server.temp_server_success = True
                    return render_success(f"{sh} credentials set successfully", 5)

        config.save("user", "")
        config.save("password", "")
        return render_fail("User and Password wrong or empty!")

    info(
        f'"{shorthand.lower()}" credentials required to access download links. '
        f"Starting web server for config at: \"{shared_state.values['internal_address']}\".")
    info(f"If needed register here: 'https://{domain}'")
    info("Please set your credentials now, to allow Quasarr to launch!")
    return Server(app, listen='0.0.0.0', port=shared_state.values['port']).serve_temporarily()


def flaresolverr_config(shared_state):
    app = Bottle()
    add_static_route(app)

    @app.get('/')
    def url_form():
        form_content = '''
        <span><a href="https://github.com/FlareSolverr/FlareSolverr?tab=readme-ov-file#installation">A local instance</a>
        must be running and reachable to Quasarr!</span><br><br>
        <label for="url">FlareSolverr URL</label>
        <input type="text" id="url" name="url" placeholder="http://192.168.0.1:8191/v1"><br>
        '''
        form_html = f'''
        <form action="/api/flaresolverr" method="post">
            {form_content}
            {render_button("Save", "primary", {"type": "submit"})}
        </form>
        '''
        return render_form("Set FlareSolverr URL", form_html)

    @app.post('/api/flaresolverr')
    def set_flaresolverr_url():
        url = request.forms.get('url').strip()
        config = Config("FlareSolverr")

        if url:
            try:
                headers = {"Content-Type": "application/json"}
                data = {
                    "cmd": "request.get",
                    "url": "http://www.google.com/",
                    "maxTimeout": 30000
                }
                response = requests.post(url, headers=headers, json=data, timeout=30)
                if response.status_code == 200:
                    config.save("url", url)
                    print(f'Using Flaresolverr URL: "{url}"')
                    kuasarr.providers.web_server.temp_server_success = True
                    return render_success("FlareSolverr URL saved successfully!", 5)
            except requests.RequestException:
                pass

        # on failure, clear any existing value and notify user
        config.save("url", "")
        return render_fail("Could not reach FlareSolverr at that URL (expected HTTP 200).")

    info(
        '"flaresolverr" URL is required for proper operation. '
        f'Starting web server for config at: "{shared_state.values["internal_address"]}".'
    )
    info("Please enter your FlareSolverr URL now.")
    return Server(app, listen='0.0.0.0', port=shared_state.values['port']).serve_temporarily()


def jdownloader_config(shared_state):
    app = Bottle()
    add_static_route(app)

    @app.get('/')
    def jd_form():
        verify_form_html = f'''
        <span>If required register account at: <a href="https://my.jdownloader.org/login.html#register">
        my.jdownloader.org</a>!</span><br>

        <p><strong>JDownloader must be running and connected to My JDownloader!</strong></p><br>

        <form id="verifyForm" action="/api/verify_jdownloader" method="post">
            <label for="user">E-Mail</label>
            <input type="text" id="user" name="user" placeholder="user@example.org" autocorrect="off"><br>
            <label for="pass">Password</label>
            <input type="password" id="pass" name="pass" placeholder="Password"><br>
            {render_button("Verify Credentials",
                           "secondary",
                           {"id": "verifyButton", "type": "button", "onclick": "verifyCredentials()"})}
        </form>

        <p>Some JDownloader settings will be enforced by Quasarr on startup.</p>

        <form action="/api/store_jdownloader" method="post" id="deviceForm" style="display: none;">
            <input type="hidden" id="hiddenUser" name="user">
            <input type="hidden" id="hiddenPass" name="pass">
            <label for="device">JDownloader</label>
            <select id="device" name="device"></select><br>
            {render_button("Save", "primary", {"type": "submit"})}
        </form>
        <p><strong>Saving may take a while!</strong></p><br>
        '''

        verify_script = '''
        <script>
        function verifyCredentials() {
            var user = document.getElementById('user').value;
            var pass = document.getElementById('pass').value;
            fetch('/api/verify_jdownloader', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({user: user, pass: pass}),
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    var select = document.getElementById('device');
                    data.devices.forEach(device => {
                        var opt = document.createElement('option');
                        opt.value = device;
                        opt.innerHTML = device;
                        select.appendChild(opt);
                    });
                    document.getElementById('hiddenUser').value = document.getElementById('user').value;
                    document.getElementById('hiddenPass').value = document.getElementById('pass').value;
                    document.getElementById("verifyButton").style.display = "none";
                    document.getElementById('deviceForm').style.display = 'block';
                } else {
                    alert('Fehler! Bitte die Zugangsdaten überprüfen.');
                }
            })
            .catch((error) => {
                console.error('Error:', error);
            });
        }
        </script>
        '''
        return render_form("Set your credentials for My JDownloader", verify_form_html, verify_script)

    @app.post("/api/verify_jdownloader")
    def verify_jdownloader():
        data = request.json
        username = data['user']
        password = data['pass']

        devices = shared_state.get_devices(username, password)
        device_names = []

        if devices:
            for device in devices:
                device_names.append(device['name'])

        if device_names:
            return {"success": True, "devices": device_names}
        else:
            return {"success": False}

    @app.post("/api/store_jdownloader")
    def store_jdownloader():
        username = request.forms.get('user')
        password = request.forms.get('pass')
        device = request.forms.get('device')

        if username and password and device:
            # Verify connection works before saving credentials
            if shared_state.set_device(username, password, device):
                config = Config('JDownloader')
                config.save('user', username)
                config.save('password', password)
                config.save('device', device)
                kuasarr.providers.web_server.temp_server_success = True
                return render_success("Credentials set", 15)

        return render_fail("Could not set credentials!")

    info(
        f'My-JDownloader-Credentials not set. '
        f"Starting web server for config at: \"{shared_state.values['internal_address']}\".")
    info("If needed register here: 'https://my.jdownloader.org/login.html#register'")
    info("Please set your credentials now, to allow Quasarr to launch!")
    return Server(app, listen='0.0.0.0', port=shared_state.values['port']).serve_temporarily()
