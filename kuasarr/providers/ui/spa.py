# -*- coding: utf-8 -*-
import os

from bottle import response

WEBUI_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'webui', 'dist')
)


def try_serve_spa():
    """Return React SPA HTML if the build exists, else None.

    The API key is intentionally NOT embedded in the HTML.
    The React app fetches it from GET /api/key after authentication.
    """
    index = os.path.join(WEBUI_DIST, 'index.html')
    if not os.path.exists(index):
        return None
    with open(index, 'r', encoding='utf-8') as f:
        html = f.read()
    response.content_type = 'text/html; charset=UTF-8'
    return html
