# -*- coding: utf-8 -*-
import os

from bottle import response

WEBUI_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'webui', 'dist')
)

_spa_cache: dict = {}  # {path: (mtime, content)}


def try_serve_spa():
    """Return React SPA HTML if the build exists, else None.

    The API key is intentionally NOT embedded in the HTML.
    The React app fetches it from GET /api/key after authentication.
    Content is cached in memory and invalidated when the file mtime changes.
    """
    index = os.path.join(WEBUI_DIST, 'index.html')
    try:
        mtime = os.path.getmtime(index)
    except OSError:
        return None

    cached = _spa_cache.get(index)
    if cached is None or cached[0] != mtime:
        with open(index, 'r', encoding='utf-8') as f:
            content = f.read()
        _spa_cache[index] = (mtime, content)
    else:
        content = cached[1]

    response.content_type = 'text/html; charset=UTF-8'
    return content
