# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import json

from bottle import request, response

from kuasarr.providers import shared_state
from kuasarr.providers.hosters import SUPPORTED_HOSTERS
from kuasarr.providers.ui.html_templates import render_centered_html, render_button
from kuasarr.storage.config import Config


def setup_hosters_routes(app):
    """Setup routes for hoster management."""

    @app.get('/hosters')
    def hosters_page():
        """Render the hoster blocking UI."""
        blocked = _get_blocked_list()
        
        hoster_cards = ""
        for hoster_id, hoster_info in sorted(SUPPORTED_HOSTERS.items(), key=lambda x: x[1]["name"]):
            is_blocked = hoster_id in blocked
            status_class = "blocked" if is_blocked else "allowed"
            status_text = "Blocked" if is_blocked else "Allowed"
            button_text = "Unblock" if is_blocked else "Block"
            button_class = "btn-primary" if is_blocked else "btn-danger"
            
            hoster_cards += f"""
            <div class="hoster-card {status_class}" data-hoster="{hoster_id}">
                <div class="hoster-info">
                    <span class="hoster-name">{hoster_info['name']}</span>
                    <span class="hoster-domain">{hoster_info['domain']}</span>
                </div>
                <div class="hoster-status">
                    <span class="status-badge {status_class}">{status_text}</span>
                    <button class="{button_class} small toggle-btn" 
                            onclick="toggleHoster('{hoster_id}', {str(is_blocked).lower()})">
                        {button_text}
                    </button>
                </div>
            </div>
            """
        
        html = f"""
        <h1>File Hoster Management</h1>
        <p>Block specific file hosters to prevent downloads from them.</p>
        
        <div class="hoster-actions">
            <button class="btn-secondary" onclick="blockAll()">Block All</button>
            <button class="btn-secondary" onclick="unblockAll()">Unblock All</button>
        </div>
        
        <div class="hoster-list">
            {hoster_cards}
        </div>
        
        <p style="margin-top: 20px;">
            {render_button("Back to Home", "secondary", {"onclick": "location.href='/'"})}
        </p>
        
        <style>
            .hoster-actions {{
                margin: 20px 0;
                display: flex;
                gap: 10px;
            }}
            .hoster-list {{
                display: flex;
                flex-direction: column;
                gap: 10px;
                max-width: 600px;
            }}
            .hoster-card {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px;
                border-radius: 8px;
                background: #f8f9fa;
                border: 1px solid #dee2e6;
            }}
            .hoster-card.blocked {{
                background: #fff5f5;
                border-color: #f5c6cb;
            }}
            .hoster-card.allowed {{
                background: #f0fff4;
                border-color: #c3e6cb;
            }}
            .hoster-info {{
                display: flex;
                flex-direction: column;
            }}
            .hoster-name {{
                font-weight: 600;
                font-size: 1.1em;
            }}
            .hoster-domain {{
                color: #6c757d;
                font-size: 0.9em;
            }}
            .hoster-status {{
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .status-badge {{
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 0.85em;
                font-weight: 500;
            }}
            .status-badge.blocked {{
                background: #dc3545;
                color: white;
            }}
            .status-badge.allowed {{
                background: #28a745;
                color: white;
            }}
            .btn-danger {{
                background: #dc3545;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
            }}
            .btn-danger:hover {{
                background: #c82333;
            }}
        </style>
        
        <script>
            async function toggleHoster(hosterId, currentlyBlocked) {{
                const action = currentlyBlocked ? 'unblock' : 'block';
                try {{
                    const response = await fetch('/api/hosters/' + action, {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{hoster_id: hosterId}})
                    }});
                    if (response.ok) {{
                        location.reload();
                    }} else {{
                        alert('Error: ' + (await response.text()));
                    }}
                }} catch (e) {{
                    alert('Error: ' + e.message);
                }}
            }}
            
            async function blockAll() {{
                if (!confirm('Block all hosters?')) return;
                try {{
                    const response = await fetch('/api/hosters/block-all', {{method: 'POST'}});
                    if (response.ok) location.reload();
                }} catch (e) {{
                    alert('Error: ' + e.message);
                }}
            }}
            
            async function unblockAll() {{
                if (!confirm('Unblock all hosters?')) return;
                try {{
                    const response = await fetch('/api/hosters/unblock-all', {{method: 'POST'}});
                    if (response.ok) location.reload();
                }} catch (e) {{
                    alert('Error: ' + e.message);
                }}
            }}
        </script>
        """
        return render_centered_html(html)

    @app.get('/api/hosters')
    def get_hosters():
        """Get all hosters with their block status."""
        response.content_type = 'application/json'
        blocked = _get_blocked_list()
        
        result = []
        for hoster_id, hoster_info in SUPPORTED_HOSTERS.items():
            result.append({
                "id": hoster_id,
                "name": hoster_info["name"],
                "domain": hoster_info["domain"],
                "blocked": hoster_id in blocked
            })
        
        return json.dumps(sorted(result, key=lambda x: x["name"]))

    @app.post('/api/hosters/block')
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
