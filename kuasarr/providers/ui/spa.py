# -*- coding: utf-8 -*-
import os

from bottle import response

from kuasarr.storage.config import Config

WEBUI_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'webui', 'dist')
)


def try_serve_spa():
    """Return React SPA HTML with injected API key if the build exists, else None."""
    index = os.path.join(WEBUI_DIST, 'index.html')
    if not os.path.exists(index):
        return None
    api_key = (Config('API').get('key') or '').replace('"', '').replace('<', '').replace('>', '')
    with open(index, 'r', encoding='utf-8') as f:
        html = f.read()
    script = f'<script>window.KUASARR_API_KEY="{api_key}";</script>'
    response.content_type = 'text/html; charset=UTF-8'
    return html.replace('</head>', script + '</head>', 1)
