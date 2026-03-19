# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""Submission routes - bypass, quick-transfer, decrypt."""

import json
import re
import zlib
from base64 import urlsafe_b64decode
from urllib.parse import urljoin

import requests
from bottle import request, response

import kuasarr.providers.ui.html_images as images
from kuasarr.downloads.linkcrypters.filecrypt import get_filecrypt_links, DLC
from kuasarr.providers import shared_state
from kuasarr.providers.ui.html_templates import render_button, render_centered_html
from kuasarr.providers.log import info
from kuasarr.providers.statistics import StatsHelper

from .helpers import check_package_exists


def setup_submission_routes(app):
    """Register submission routes."""

    @app.post('/captcha/bypass-submit')
    def handle_bypass_submit():
        try:
            package_id = request.forms.get('package_id')
            check_package_exists(package_id)
            title = request.forms.get('title')
            password = request.forms.get('password', '')
            links_input = request.forms.get('links', '').strip()
            dlc_upload = request.files.get('dlc_file')

            if not package_id or not title:
                return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                <p><b>Error:</b> Missing package information.</p>
                <p>
                    {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
                </p>''')

            links = []
            if links_input:
                info(f"Processing direct links bypass for {title}")
                links = [link.strip() for link in links_input.split('\n') if link.strip()]
                info(f"Received {len(links)} direct download links")

            elif dlc_upload:
                info(f"Processing DLC file bypass for {title}")
                dlc_content = dlc_upload.file.read()
                try:
                    decrypted_links = DLC(shared_state, dlc_content).decrypt()
                    if decrypted_links:
                        links = decrypted_links
                        info(f"Decrypted {len(links)} links from DLC file")
                    else:
                        raise ValueError("DLC decryption returned no links")
                except Exception as e:
                    info(f"DLC decryption failed: {e}")
                    return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                    <p><b>Error:</b> Failed to decrypt DLC file: {str(e)}</p>
                    <p>
                        {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
                    </p>''')
            else:
                return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                <p><b>Error:</b> Please provide either links or a DLC file.</p>
                <p>
                    {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
                </p>''')

            if links:
                downloaded = shared_state.download_package(links, title, password, package_id)
                if downloaded:
                    StatsHelper(shared_state).increment_package_with_links(links)
                    StatsHelper(shared_state).increment_captcha_decryptions_manual()
                    shared_state.get_db("protected").delete(package_id)

                    remaining_protected = shared_state.get_db("protected").retrieve_all_titles()
                    has_more_captchas = bool(remaining_protected)

                    if has_more_captchas:
                        solve_button = render_button("Solve another CAPTCHA", "primary", {
                            "onclick": "location.href='/captcha'",
                        })
                    else:
                        solve_button = "<b>No more CAPTCHAs</b>"

                    return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                    <p><b>Success!</b> Package "{title}" bypassed and submitted to JDownloader.</p>
                    <p>{len(links)} link(s) processed.</p>
                    <p>
                        {solve_button}
                    </p>
                    <p>
                        {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
                    </p>''')
                else:
                    StatsHelper(shared_state).increment_failed_decryptions_manual()
                    return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                    <p><b>Error:</b> Failed to submit package to JDownloader.</p>
                    <p>
                        {render_button("Try Again", "secondary", {"onclick": "location.href='/captcha'"})}
                    </p>''')
            else:
                return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                <p><b>Error:</b> No valid links found.</p>
                <p>
                    {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
                </p>''')

        except Exception as e:
            info(f"Bypass submission error: {e}")
            return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
            <p><b>Error:</b> {str(e)}</p>
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
            </p>''')

    @app.get('/captcha/quick-transfer')
    def handle_quick_transfer():
        try:
            package_id = request.query.get('pkg_id')
            compressed_links = request.query.get('links', '')

            if not package_id or not compressed_links:
                return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                <p><b>Error:</b> Missing parameters</p>
                <p>
                    {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
                </p>''')

            check_package_exists(package_id)

            padding = 4 - (len(compressed_links) % 4)
            if padding != 4:
                compressed_links += '=' * padding

            try:
                decoded = urlsafe_b64decode(compressed_links)
            except Exception as e:
                info(f"Base64 decode error: {e}")
                return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                <p><b>Error:</b> Failed to decode data: {str(e)}</p>
                <p>
                    {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
                </p>''')

            try:
                decompressed = zlib.decompress(decoded, -15)
            except Exception as e:
                info(f"Decompression error: {e}, trying with header...")
                try:
                    decompressed = zlib.decompress(decoded)
                except Exception as e2:
                    info(f"Decompression also failed with header: {e2}")
                    return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                    <p><b>Error:</b> Failed to decompress data: {str(e)}</p>
                    <p>
                        {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
                    </p>''')

            links_text = decompressed.decode('utf-8')

            raw_links = [link.strip() for link in links_text.split('\n') if link.strip()]
            links = []
            for link in raw_links:
                if not link.startswith(('http://', 'https://')):
                    link = 'https://' + link
                links.append(link)

            info(f"Quick transfer received {len(links)} links for package {package_id}")

            raw_data = shared_state.get_db("protected").retrieve(package_id)
            data = json.loads(raw_data)
            title = data.get("title", "Unknown")
            password = data.get("password", "")

            downloaded = shared_state.download_package(links, title, password, package_id)

            if downloaded:
                StatsHelper(shared_state).increment_package_with_links(links)
                StatsHelper(shared_state).increment_captcha_decryptions_manual()
                shared_state.get_db("protected").delete(package_id)

                info(f"Quick transfer successful: {len(links)} links processed")

                remaining_protected = shared_state.get_db("protected").retrieve_all_titles()
                has_more_captchas = bool(remaining_protected)

                if has_more_captchas:
                    solve_button = render_button("Solve another CAPTCHA", "primary",
                                                {"onclick": "location.href='/captcha'"})
                else:
                    solve_button = "<b>No more CAPTCHAs</b>"

                return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                <p><b>✅ Quick Transfer Successful!</b></p>
                <p>Package "{title}" with {len(links)} link(s) submitted to JDownloader.</p>
                <p>
                    {solve_button}
                </p>
                <p>
                    {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
                </p>''')
            else:
                StatsHelper(shared_state).increment_failed_decryptions_manual()
                return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                <p><b>Error:</b> Failed to submit package to JDownloader</p>
                <p>
                    {render_button("Try Again", "secondary", {"onclick": "location.href='/captcha'"})}
                </p>''')

        except Exception as e:
            info(f"Quick transfer error: {e}")
            return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
            <p><b>Error:</b> {str(e)}</p>
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
            </p>''')

    @app.post('/captcha/decrypt-filecrypt')
    def submit_token():
        protected = shared_state.get_db("protected").retrieve_all_titles()
        if not protected:
            return {"success": False, "title": "No protected packages found! CAPTCHA not needed."}

        links = []
        title = "Unknown Package"
        try:
            data = request.json
            token = data.get('token')
            package_id = data.get('package_id')
            title = data.get('title')
            link = data.get('link')
            password = data.get('password')
            mirror = None if (mirror := data.get('mirror')) == "None" else mirror

            if token:
                info(f"Received token: {token}")
                info(f"Decrypting links for {title}")
                decrypted = get_filecrypt_links(shared_state, token, title, link, password=password, mirror=mirror)
                if decrypted:
                    if decrypted.get("status", "") == "replaced":
                        replace_url = decrypted.get("replace_url")
                        session = decrypted.get("session")
                        mirror = decrypted.get("mirror", "filecrypt")

                        links = [replace_url]

                        blob = json.dumps(
                            {
                                "title": title,
                                "links": [replace_url, mirror],
                                "size_mb": 0,
                                "password": password,
                                "mirror": mirror,
                                "session": session,
                                "original_url": link
                            })
                        shared_state.get_db("protected").update_store(package_id, blob)
                        info(f"Another CAPTCHA solution is required for {mirror} link: {replace_url}")

                    else:
                        links = decrypted.get("links", [])
                        info(f"Decrypted {len(links)} download links for {title}")
                        if not links:
                            raise ValueError("No download links found after decryption")
                        downloaded = shared_state.download_package(links, title, password, package_id)
                        if downloaded:
                            StatsHelper(shared_state).increment_package_with_links(links)
                            shared_state.get_db("protected").delete(package_id)
                        else:
                            links = []
                            raise RuntimeError("Submitting Download to JDownloader failed")
                else:
                    raise ValueError("No download links found")

        except Exception as e:
            info(f"Error decrypting: {e}")

        success = bool(links)
        if success:
            StatsHelper(shared_state).increment_captcha_decryptions_manual()
        else:
            StatsHelper(shared_state).increment_failed_decryptions_manual()

        remaining_protected = shared_state.get_db("protected").retrieve_all_titles()
        has_more_captchas = bool(remaining_protected)

        return {"success": success, "title": title, "has_more_captchas": has_more_captchas}

    @app.post('/captcha/decrypt-filecrypt-circle')
    def proxy_form_submit():
        url = request.query.get('url')
        session_id = request.query.get('session_id')
        package_id = request.query.get('package_id')
        success = False

        if not url or not session_id or not package_id:
            response.status = 400
            return "Missing required parameters"

        cookies = {'PHPSESSID': session_id}

        headers = {
            'User-Agent': shared_state.values["user_agent"],
            "Content-Type": "application/x-www-form-urlencoded"
        }

        raw_body = request.body.read()

        resp = requests.post(url, cookies=cookies, headers=headers, data=raw_body, verify=False)

        response.content_type = resp.headers.get('Content-Type', 'text/html')

        status = "You did not solve the CAPTCHA correctly. Please try again."
        
        if "<h2>Security Check</h2>" in resp.text or "click inside the open circle" in resp.text:
            status = "CAPTCHA verification failed. Please try again."
            info(status)

        match = re.search(
            r"top\.location\.href\s*=\s*['\"]([^'\"]*?/go\b[^'\"]*)['\"]",
            resp.text,
            re.IGNORECASE
        )
        if match:
            redirect_url = match.group(1)
            resolved_url = urljoin(url, redirect_url)
            info(f"Redirect URL: {resolved_url}")
            try:
                redirect_resp = requests.post(resolved_url, cookies=cookies, headers=headers, allow_redirects=True,
                                             timeout=10, verify=False)

                if "expired" in redirect_resp.text.lower():
                    status = f"The CAPTCHA session has expired. Deleting package: {package_id}"
                    info(status)
                    shared_state.get_db("protected").delete(package_id)
                else:
                    download_link = redirect_resp.url
                    if redirect_resp.ok:
                        status = "Successfully resolved download link!"
                        info(status)

                        raw_data = shared_state.get_db("protected").retrieve(package_id)
                        data = json.loads(raw_data)
                        title = data.get("title")
                        password = data.get("password", "")
                        links = [download_link]
                        downloaded = shared_state.download_package(links, title, password, package_id)
                        if downloaded:
                            StatsHelper(shared_state).increment_package_with_links(links)
                            success = True
                            shared_state.get_db("protected").delete(package_id)
                        else:
                            raise RuntimeError("Submitting Download to JDownloader failed")
                    else:
                        info(
                            f"Failed to reach redirect target. Status: {redirect_resp.status_code}, Solution: {status}")
            except Exception as e:
                info(f"Error while resolving download link: {e}")
        else:
            if resp.url.endswith("404.html"):
                info("Your IP has been blocked by Filecrypt. Please try again later.")
            else:
                info("You did not solve the CAPTCHA correctly. Please try again.")

        if success:
            StatsHelper(shared_state).increment_captcha_decryptions_manual()
        else:
            StatsHelper(shared_state).increment_failed_decryptions_manual()

        remaining_protected = shared_state.get_db("protected").retrieve_all_titles()
        has_more_captchas = bool(remaining_protected)

        if has_more_captchas:
            solve_button = render_button("Solve another CAPTCHA", "primary", {
                "onclick": "location.href='/captcha'",
            })
        else:
            solve_button = "<b>No more CAPTCHAs</b>"

        return render_centered_html(f"""
        <!DOCTYPE html>
        <html>
          <body>
            <h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
            <p>{status}</p>
            <p>
                {solve_button}
            </p>
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
            </p>
          </body>
        </html>""")
