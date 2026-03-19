# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""Provider-specific CAPTCHA routes - Junkies, KeepLinks, ToLink, Cutcaptcha, Circle."""

from bottle import request, response

import kuasarr.providers.ui.html_images as images
from kuasarr.providers import shared_state
from kuasarr.providers.ui.html_templates import render_button, render_centered_html, render_fail, render_success
from kuasarr.providers.obfuscated import (
    captcha_js, captcha_values, filecrypt_quasarr_helper_user_js,
    keeplinks_quasarr_helper_user_js, tolink_quasarr_helper_user_js
)

from .helpers import js_single_quoted_string_safe, check_package_exists, decode_payload
from .ui_components import render_bypass_section
from kuasarr.downloads.linkcrypters.hide import unhide_links
from kuasarr.providers.log import info


def setup_provider_routes(app):
    """Register provider-specific CAPTCHA routes."""

    @app.get("/captcha/junkies")
    def serve_junkies_captcha():
        payload = decode_payload()

        if "error" in payload:
            return render_fail(payload["error"])

        package_id = payload.get("package_id")
        check_package_exists(package_id)
        title = payload.get("title")
        password = payload.get("password")
        urls = payload.get("links") or []

        if not urls:
            return render_fail(f"No download links available for package: {title}")

        first_url = urls[0][0] if isinstance(urls[0], (list, tuple)) else urls[0]

        return render_centered_html(f"""
        <!DOCTYPE html>
        <html>
        <body>
        <h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
        <p><b>Package:</b> {title}</p>
        {render_bypass_section(first_url, package_id, title, password)}
        <p>
            {render_button("Delete Package", "secondary", {"onclick": f"location.href='/captcha/delete/{package_id}'"})}
        </p>
        <p>
            {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
        </p>
        </body>
        </html>""")

    @app.get("/captcha/keeplinks")
    def serve_keeplinks_captcha():
        payload = decode_payload()

        if "error" in payload:
            return render_fail(payload["error"])

        package_id = payload.get("package_id")
        check_package_exists(package_id)
        title = payload.get("title")
        password = payload.get("password")
        urls = payload.get("links") or []

        if not urls:
            return render_fail(f"No download links available for package: {title}")

        first_url = urls[0][0] if isinstance(urls[0], (list, tuple)) else urls[0]

        return render_centered_html(f"""
        <!DOCTYPE html>
        <html>
        <body>
        <h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
        <p><b>Package:</b> {title}</p>
        {render_bypass_section(first_url, package_id, title, password, provider_name="KeepLinks", storage_key="hideSetupInstructionsKeeplinks", userscript_url="/captcha/keeplinks.user.js")}
        <p>
            {render_button("Delete Package", "secondary", {"onclick": f"location.href='/captcha/delete/{package_id}'"})}
        </p>
        <p>
            {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
        </p>
        </body>
        </html>""")

    @app.get("/captcha/tolink")
    def serve_tolink_captcha():
        payload = decode_payload()

        if "error" in payload:
            return render_fail(payload["error"])

        package_id = payload.get("package_id")
        check_package_exists(package_id)
        title = payload.get("title")
        password = payload.get("password")
        urls = payload.get("links") or []

        if not urls:
            return render_fail(f"No download links available for package: {title}")

        first_url = urls[0][0] if isinstance(urls[0], (list, tuple)) else urls[0]

        return render_centered_html(f"""
        <!DOCTYPE html>
        <html>
        <body>
        <h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
        <p><b>Package:</b> {title}</p>
        {render_bypass_section(first_url, package_id, title, password, provider_name="ToLink", storage_key="hideSetupInstructionsTolink", userscript_url="/captcha/tolink.user.js")}
        <p>
            {render_button("Delete Package", "secondary", {"onclick": f"location.href='/captcha/delete/{package_id}'"})}
        </p>
        <p>
            {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
        </p>
        </body>
        </html>""")

    @app.get("/captcha/hide")
    def serve_hide_captcha():
        """Handle hide.cx links - decrypt via API (no CAPTCHA needed)."""
        from kuasarr.downloads.linkcrypters.hide import get_hide_api_key
        
        payload = decode_payload()

        if "error" in payload:
            return render_fail(payload["error"])

        package_id = payload.get("package_id")
        check_package_exists(package_id)
        title = payload.get("title")
        password = payload.get("password")
        urls = payload.get("links") or []

        if not urls:
            return render_fail(f"No download links available for package: {title}")

        api_key = get_hide_api_key(shared_state)
        if not api_key:
            return render_centered_html(f"""
            <!DOCTYPE html>
            <html>
            <body>
            <h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
            <p><b>Package:</b> {title}</p>
            <div class="info-box" style="background: #fff3cd; border: 1px solid #ffc107; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                <h3 style="color: #856404; margin-top: 0;">⚠️ hide.cx API Key erforderlich</h3>
                <p style="color: #856404; margin-bottom: 0.5rem;">
                    Um hide.cx Links zu entschlüsseln, wird ein API Key benötigt.
                </p>
                <p style="color: #856404; margin-bottom: 0.5rem;">
                    <b>So erhältst du einen kostenlosen API Key:</b>
                </p>
                <ol style="color: #856404; margin-bottom: 0.5rem; padding-left: 1.5rem;">
                    <li>Erstelle einen kostenlosen Account auf <a href="https://hide.cx" target="_blank">hide.cx</a></li>
                    <li>Gehe zu Settings → Account → Application API Keys</li>
                    <li>Erstelle einen neuen API Key</li>
                    <li>Trage den Key in Kuasarr unter Settings → HideCX → api_key ein</li>
                </ol>
            </div>
            <p>
                {render_button("Zu den Settings", "primary", {"onclick": "location.href='/settings'"})}
            </p>
            <p>
                {render_button("Delete Package", "secondary", {"onclick": f"location.href='/captcha/delete/{package_id}'"})}
            </p>
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
            </p>
            </body>
            </html>""")

        first_url = urls[0][0] if isinstance(urls[0], (list, tuple)) else urls[0]
        
        info(f"Decrypting hide.cx link via API: {first_url}")
        decrypted_links, error = unhide_links(shared_state, first_url, password)
        
        if decrypted_links:
            info(f"Successfully decrypted {len(decrypted_links)} links from hide.cx")
            added = shared_state.download_package(
                decrypted_links,
                title,
                password
            )
            
            if added:
                shared_state.get_db("protected").delete(package_id)
                
                remaining_protected = shared_state.get_db("protected").retrieve_all_titles()
                has_more_captchas = bool(remaining_protected)
                
                if has_more_captchas:
                    solve_button = render_button("Solve another CAPTCHA", "primary", {"onclick": "location.href='/captcha'"})
                else:
                    solve_button = "<b>No more CAPTCHAs</b>"
                
                return render_success(
                    f"Successfully decrypted {len(decrypted_links)} links from hide.cx!",
                    timeout=0,
                    optional_text=f"<p>{solve_button}</p>"
                )
            else:
                return render_fail(f"Failed to add decrypted links to JDownloader for: {title}")
        else:
            error_msg = error or "Failed to decrypt hide.cx link. The link may be expired or invalid."
            info(f"Failed to decrypt hide.cx link: {first_url} - {error_msg}")
            return render_centered_html(f"""
            <!DOCTYPE html>
            <html>
            <body>
            <h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
            <p><b>Package:</b> {title}</p>
            <p><b>Error:</b> {error_msg}</p>
            <p>
                {render_button("Delete Package", "secondary", {"onclick": f"location.href='/captcha/delete/{package_id}'"})}
            </p>
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
            </p>
            </body>
            </html>""")

    @app.get('/captcha/kuasarr.user.js')
    def serve_kuasarr_user_js():
        content = filecrypt_quasarr_helper_user_js()
        response.content_type = 'application/javascript'
        return content

    @app.get('/captcha/keeplinks.user.js')
    def serve_keeplinks_user_js():
        content = keeplinks_quasarr_helper_user_js()
        response.content_type = 'application/javascript'
        return content

    @app.get('/captcha/tolink.user.js')
    def serve_tolink_user_js():
        content = tolink_quasarr_helper_user_js()
        response.content_type = 'application/javascript'
        return content

    @app.get('/captcha/cutcaptcha')
    def serve_cutcaptcha():
        payload = decode_payload()

        if "error" in payload:
            return render_fail(payload["error"])

        package_id = payload.get("package_id")
        check_package_exists(package_id)
        title = payload.get("title")
        password = payload.get("password")
        desired_mirror = payload.get("mirror")
        prioritized_links = payload.get("links")

        if not prioritized_links:
            return render_fail(f"No download links available for package: {title}")

        link_options = ""
        if len(prioritized_links) > 1:
            for link in prioritized_links:
                if "filecrypt." in link[0]:
                    link_options += f'<option value="{link[0]}">{link[1]}</option>'
            link_select = f'''<div id="mirrors-select">
                    <label for="link-select">Mirror:</label>
                    <select id="link-select">
                        {link_options}
                    </select>
                </div>
                <script>
                    document.getElementById("link-select").addEventListener("change", function() {{
                        var selectedLink = this.value;
                        document.getElementById("link-hidden").value = selectedLink;
                    }});
                </script>
            '''
        else:
            link_select = f'<div id="mirrors-select">Mirror: <b>{prioritized_links[0][1]}</b></div>'

        solve_another_html = render_button("Solve another CAPTCHA", "primary", {"onclick": "location.href='/captcha'"})
        back_button_html = render_button("Back", "secondary", {"onclick": "location.href='/'"})

        original_url = prioritized_links[0][0]
        bypass_section = render_bypass_section(original_url, package_id, title, password)

        content = render_centered_html(r'''
            <script type="text/javascript">
                var api_key = "''' + captcha_values()["api_key"] + r'''";
                var endpoint = '/' + window.location.pathname.split('/')[1] + '/' + api_key + '.html';
                var solveAnotherHtml = `<p>''' + solve_another_html + r'''</p><p>''' + back_button_html + r'''</p>`;
                var noMoreHtml = `<p><b>No more CAPTCHAs</b></p><p>''' + back_button_html + r'''</p>`;

                function handleToken(token) {
                    document.getElementById("puzzle-captcha").remove();
                    document.getElementById("mirrors-select").remove();
                    document.getElementById("delete-package-section").style.display = "none";
                    document.getElementById("back-button-section").style.display = "none";
                    document.getElementById("bypass-section").style.display = "none";

                    var packageTitle = document.getElementById("package-title");
                    packageTitle.style.maxWidth = "none";

                    document.getElementById("captcha-key").innerText = 'Using result "' + token + '" to decrypt links...';
                    var link = document.getElementById("link-hidden").value;
                    const fullPath = '/captcha/decrypt-filecrypt';

                    fetch(fullPath, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ 
                            token: token,
                            ''' + f'''package_id: '{package_id}',
                            title: '{js_single_quoted_string_safe(title)}',
                            link: link,
                            password: '{password}',
                            mirror: '{desired_mirror}',
                        ''' + '''})
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            document.getElementById("captcha-key").insertAdjacentHTML('afterend', 
                                '<p>Successful!</p>');
                        } else {
                            document.getElementById("captcha-key").insertAdjacentHTML('afterend', 
                                '<p>Failed. Check console for details!</p>');
                        }

                        var reloadSection = document.getElementById("reload-button");
                        if (data.has_more_captchas) {
                            reloadSection.innerHTML = solveAnotherHtml;
                        } else {
                            reloadSection.innerHTML = noMoreHtml;
                        }
                        reloadSection.style.display = "block";
                    });
                }
                ''' + captcha_js() + f'''</script>
                <div>
                    <h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                    <p id="package-title" style="max-width: 370px; word-wrap: break-word; overflow-wrap: break-word;"><b>Package:</b> {title}</p>
                    <div id="captcha-key"></div>
                    {link_select}<br><br>
                    <input type="hidden" id="link-hidden" value="{prioritized_links[0][0]}" />
                    <div class="captcha-container">
                        <div id="puzzle-captcha" aria-style="mobile">
                            <strong>Your adblocker prevents the captcha from loading. Disable it!</strong>
                        </div>
                    </div>
                    <div id="reload-button" style="display: none;">
                    </div>
            <br>
            <div id="delete-package-section">
            <p>
                {render_button("Delete Package", "secondary", {"onclick": f"location.href='/captcha/delete/{package_id}'"})}
            </p>
            </div>
            <div id="back-button-section">
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
            </p>
            </div>
            <div id="bypass-section">
                {bypass_section}
            </div>
                </div>
                </html>''')

        return content

    @app.get('/captcha/circle')
    def serve_circle():
        payload = decode_payload()

        if "error" in payload:
            return render_fail(payload["error"])

        package_id = payload.get("package_id")
        check_package_exists(package_id)
        session_id = payload.get("session")
        title = payload.get("title", "Unknown Package")
        password = payload.get("password", "")
        original_url = payload.get("original_url", "")
        url = payload.get("links")[0] if payload.get("links") else None

        if not url or not session_id or not package_id:
            return render_fail("Missing required parameters")

        bypass_url = original_url if original_url else url
        bypass_section = render_bypass_section(bypass_url, package_id, title, password)

        return render_centered_html(f"""
        <!DOCTYPE html>
        <html>
          <body>
            <h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
            <p><b>Package:</b> {title}</p>
            <h3>Solve CAPTCHA</h3>
            <form action="/captcha/decrypt-filecrypt-circle?url={url}&session_id={session_id}&package_id={package_id}" method="post">
              <input type="image" src="/captcha/circle.php?url={url}&session_id={session_id}" name="button" alt="Circle CAPTCHA">
            </form>
            <p>
                {render_button("Delete Package", "secondary", {"onclick": f"location.href='/captcha/delete/{package_id}'"})}
            </p>
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
            </p>
            {bypass_section}
          </body>
        </html>""")
