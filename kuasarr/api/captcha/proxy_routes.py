# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""Proxy routes for external CAPTCHA resources."""

import re

import requests
from bottle import request, response

from kuasarr.providers import shared_state
from kuasarr.providers.obfuscated import captcha_values


def setup_proxy_routes(app):
    """Register proxy routes for external resources."""

    @app.post('/captcha/<captcha_id>.html')
    def proxy_html(captcha_id):
        target_url = f"{captcha_values()['url']}/captcha/{captcha_id}.html"

        headers = {key: value for key, value in request.headers.items() if key != 'Host'}
        data = request.body.read()
        resp = requests.post(target_url, headers=headers, data=data, verify=False)

        content = resp.text
        content = re.sub(
            r'''<script\s+src="/(jquery(?:-ui|\.ui\.touch-punch\.min)?\.js)(?:\?[^"]*)?"></script>''',
            r'''<script src="/captcha/js/\1"></script>''',
            content
        )

        response.content_type = 'text/html'
        return content

    @app.post('/captcha/<captcha_id>.json')
    def proxy_json(captcha_id):
        target_url = f"{captcha_values()['url']}/captcha/{captcha_id}.json"

        headers = {key: value for key, value in request.headers.items() if key != 'Host'}
        data = request.body.read()
        resp = requests.post(target_url, headers=headers, data=data, verify=False)

        response.content_type = resp.headers.get('Content-Type')
        return resp.content

    @app.get('/captcha/js/<filename>')
    def serve_local_js(filename):
        upstream = f"{captcha_values()['url']}/{filename}"
        try:
            upstream_resp = requests.get(upstream, verify=False, stream=True)
            upstream_resp.raise_for_status()
        except requests.RequestException as e:
            response.status = 502
            return f"/* Error proxying {filename}: {e} */"

        response.content_type = 'application/javascript'
        return upstream_resp.iter_content(chunk_size=8192)

    @app.get('/captcha/<captcha_id>/<uuid>/<filename>')
    def proxy_pngs(captcha_id, uuid, filename):
        new_url = f"{captcha_values()['url']}/captcha/{captcha_id}/{uuid}/{filename}"

        try:
            external_response = requests.get(new_url, stream=True, verify=False)
            external_response.raise_for_status()
            response.content_type = 'image/png'
            response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
            return external_response.iter_content(chunk_size=8192)

        except requests.RequestException as e:
            response.status = 502
            return f"Error fetching resource: {e}"

    @app.post('/captcha/<captcha_id>/check')
    def proxy_check(captcha_id):
        new_url = f"{captcha_values()['url']}/captcha/{captcha_id}/check"
        headers = {key: value for key, value in request.headers.items()}

        data = request.body.read()
        resp = requests.post(new_url, headers=headers, data=data, verify=False)

        response.status = resp.status_code
        for header in resp.headers:
            if header.lower() not in ['content-encoding', 'transfer-encoding', 'content-length', 'connection']:
                response.set_header(header, resp.headers[header])
        return resp.content

    @app.get('/captcha/circle.php')
    def proxy_circle_php():
        target_url = "https://filecrypt.cc/captcha/circle.php"

        url = request.query.get('url')
        session_id = request.query.get('session_id')
        if not url or not session_id:
            response.status = 400
            return "Missing required parameters"

        headers = {'User-Agent': shared_state.values["user_agent"]}
        cookies = {'PHPSESSID': session_id}

        resp = requests.get(target_url, headers=headers, cookies=cookies, verify=False)

        response.content_type = resp.headers.get('Content-Type', 'application/octet-stream')
        return resp.content
