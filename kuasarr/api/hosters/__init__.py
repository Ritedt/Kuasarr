# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import json

from bottle import request, response

from kuasarr.providers import shared_state
from kuasarr.providers.auth import require_api_key
from kuasarr.providers.hosters import SUPPORTED_HOSTERS
from kuasarr.storage.config import Config


def setup_hosters_routes(app):
    """Setup routes for hoster management."""

    @app.get('/api/hosters')
    @require_api_key
    def get_hosters():
        """Get all hosters with their block status."""
        response.content_type = 'application/json'
        blocked = _get_blocked_list()

        result = []
        for hoster_id, hoster_info in SUPPORTED_HOSTERS.items():
            is_blocked = hoster_id in blocked
            result.append({
                "id": hoster_id,
                "name": hoster_info["name"],
                "url": hoster_info["domain"],
                "blocked": is_blocked,
                "enabled": not is_blocked,
                "priority": 0,
                "status": "unknown",
            })

        return json.dumps({"data": sorted(result, key=lambda x: x["name"])})

    @app.post('/api/hosters/block')
    @require_api_key
    def block_hoster():
        """Block a specific hoster."""
        response.content_type = 'application/json'
        try:
            data = request.json or {}
            hoster_id = data.get('hoster_id')
            
            if not hoster_id or hoster_id not in SUPPORTED_HOSTERS:
                response.status = 400
                return json.dumps({"error": "Invalid hoster_id"})
            
            blocked = _get_blocked_list()
            if hoster_id not in blocked:
                blocked.append(hoster_id)
                _save_blocked_list(blocked)
            
            return json.dumps({"success": True, "blocked": blocked})
        except Exception as e:
            response.status = 500
            return json.dumps({"error": str(e)})

    @app.post('/api/hosters/unblock')
    @require_api_key
    def unblock_hoster():
        """Unblock a specific hoster."""
        response.content_type = 'application/json'
        try:
            data = request.json or {}
            hoster_id = data.get('hoster_id')
            
            if not hoster_id or hoster_id not in SUPPORTED_HOSTERS:
                response.status = 400
                return json.dumps({"error": "Invalid hoster_id"})
            
            blocked = _get_blocked_list()
            if hoster_id in blocked:
                blocked.remove(hoster_id)
                _save_blocked_list(blocked)
            
            return json.dumps({"success": True, "blocked": blocked})
        except Exception as e:
            response.status = 500
            return json.dumps({"error": str(e)})

    @app.post('/api/hosters/block-all')
    @require_api_key
    def block_all_hosters():
        """Block all hosters."""
        response.content_type = 'application/json'
        try:
            blocked = list(SUPPORTED_HOSTERS.keys())
            _save_blocked_list(blocked)
            return json.dumps({"success": True, "blocked": blocked})
        except Exception as e:
            response.status = 500
            return json.dumps({"error": str(e)})

    @app.post('/api/hosters/unblock-all')
    @require_api_key
    def unblock_all_hosters():
        """Unblock all hosters."""
        response.content_type = 'application/json'
        try:
            _save_blocked_list([])
            return json.dumps({"success": True, "blocked": []})
        except Exception as e:
            response.status = 500
            return json.dumps({"error": str(e)})


def _get_blocked_list():
    """Get list of blocked hoster IDs."""
    try:
        blocked_str = Config('BlockedHosters').get('hosters')
        if blocked_str:
            return [h.strip() for h in blocked_str.split(',') if h.strip()]
    except Exception:
        pass
    return []


def _save_blocked_list(blocked):
    """Save list of blocked hoster IDs."""
    Config('BlockedHosters').save('hosters', ','.join(blocked))
