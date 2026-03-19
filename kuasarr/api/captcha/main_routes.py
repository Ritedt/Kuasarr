# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""Main CAPTCHA routes - entry point and delete."""

import json
from base64 import urlsafe_b64encode
from urllib.parse import quote

from bottle import redirect

import kuasarr.providers.ui.html_images as images
from kuasarr.downloads.packages import delete_package
from kuasarr.providers import shared_state
from kuasarr.providers.log import info
from kuasarr.providers.ui.html_templates import render_button, render_centered_html, render_fail, render_success

from .helpers import is_junkies_link, is_keeplinks_link, is_tolink_link, is_hide_link
from kuasarr.providers.hoster import filter_blocked_hosters
from kuasarr.downloads import fail


def setup_main_routes(app):
    """Register main CAPTCHA routes."""

    @app.get('/captcha/')
    def captcha_trailing_slash():
        redirect('/captcha')

    @app.get('/captcha')
    def check_captcha():
        try:
            device = shared_state.values["device"]
        except KeyError:
            device = None
        if not device:
            return render_fail("JDownloader connection not established.")

        protected = shared_state.get_db("protected").retrieve_all_titles()
        if not protected:
            return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
            <p>No protected packages found! CAPTCHA not needed.</p>
            <p>
                {render_button("Confirm", "primary", {"onclick": "location.href='/'"})}
            </p>''')
        else:
            package = protected[0]
            package_id = package[0]
            data = json.loads(package[1])
            title = data["title"]
            links = data["links"]
            password = data["password"]
            try:
                desired_mirror = data["mirror"]
            except KeyError:
                desired_mirror = None

            filecrypt_session = data.get("session", None)

            # Filter blocked hosters first
            filtered_links = filter_blocked_hosters(links)

            if not filtered_links and links:
                # All links were blocked - mark as failed and skip
                info(f"Package '{title}' has only blocked hosters - marking as failed")
                fail(title, package_id, shared_state,
                     reason=f"All hosters blocked by user configuration")
                shared_state.get_db("protected").delete(package_id)
                return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
                <p><b>Package skipped:</b> All links in "{title}" are from blocked hosters.</p>
                <p>Package has been moved to failed downloads.</p>
                <p>
                    {render_button("Back to CAPTCHA Queue", "primary", {"onclick": "location.href='/captcha'"})}
                </p>''')

            rapid = [ln for ln in filtered_links if "rapidgator" in ln[1].lower()]
            others = [ln for ln in filtered_links if "rapidgator" not in ln[1].lower()]
            prioritized_links = rapid + others

            original_url = data.get("original_url", "")

            payload = {
                "package_id": package_id,
                "title": title,
                "password": password,
                "mirror": desired_mirror,
                "session": filecrypt_session,
                "links": prioritized_links,
                "original_url": original_url
            }

            encoded_payload = urlsafe_b64encode(json.dumps(payload).encode()).decode()

            has_junkies_links = any(is_junkies_link(l) for l in prioritized_links)
            has_keeplinks_links = any(is_keeplinks_link(l) for l in prioritized_links)
            has_tolink_links = any(is_tolink_link(l) for l in prioritized_links)
            has_hide_links = any(is_hide_link(l) for l in prioritized_links)

            if has_hide_links:
                redirect(f"/captcha/hide?data={quote(encoded_payload)}")
            elif has_junkies_links:
                redirect(f"/captcha/junkies?data={quote(encoded_payload)}")
            elif has_keeplinks_links:
                redirect(f"/captcha/keeplinks?data={quote(encoded_payload)}")
            elif has_tolink_links:
                redirect(f"/captcha/tolink?data={quote(encoded_payload)}")
            elif filecrypt_session:
                redirect(f"/captcha/circle?data={quote(encoded_payload)}")
            else:
                redirect(f"/captcha/cutcaptcha?data={quote(encoded_payload)}")

            return render_centered_html(f'''<h1><img src="{images.logo}" type="image/png" alt="Kuasarr logo" class="logo"/>Kuasarr</h1>
            <p>Unexpected Error!</p>
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
            </p>''')

    @app.get('/captcha/delete/<package_id>')
    def delete_captcha_package(package_id):
        success = delete_package(shared_state, package_id)

        remaining_protected = shared_state.get_db("protected").retrieve_all_titles()
        has_more_captchas = bool(remaining_protected)

        if has_more_captchas:
            solve_button = render_button("Solve another CAPTCHA", "primary", {
                "onclick": "location.href='/captcha'",
            })
        else:
            solve_button = "<b>No more CAPTCHAs</b>"

        if success:
            return render_success("Package successfully deleted!", timeout=0, optional_text="<p>Package successfully deleted!</p>")
        else:
            return render_fail("Failed to delete package!")
