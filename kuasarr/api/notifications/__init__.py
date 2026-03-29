# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import html
import json
import re

from bottle import request, response, redirect

from kuasarr.providers.auth import require_api_key, require_csrf_token
from kuasarr.providers.ui.html_templates import render_form, render_button
from kuasarr.storage.config import Config
from kuasarr.storage.setup.notifications import (
    get_notification_settings_data,
    save_notification_settings,
    send_notification_test,
    refresh_notification_settings,
    _notification_toggle_key,
    NOTIFICATION_TYPES,
    NOTIFICATION_SETTINGS_TABLE,
)
from kuasarr.storage.sqlite_database import DataBase
from kuasarr.constants import NOTIFICATION_PROVIDERS


def setup_notifications_routes(app, shared_state):
    @app.get('/notifications')
    def notifications_ui():
        cfg = Config('Notifications')
        discord_set = bool(cfg.get('discord_webhook'))
        telegram_set = bool(cfg.get('telegram_token'))
        chat_id = html.escape(cfg.get('telegram_chat_id') or '')

        form_html = f'''
        <p>Configure Discord and Telegram notifications.</p>
        <form action="/api/notifications/save" method="post" id="notifForm">

            <div class="notif-section">
                <h3>Discord</h3>
                <label for="discord_webhook">Webhook URL</label>
                <div class="secret-row">
                    <input type="password" id="discord_webhook" name="discord_webhook"
                           placeholder="{'••••••••' if discord_set else 'https://discord.com/api/webhooks/...'}"
                           autocomplete="off">
                    <button type="button" class="btn-secondary btn-sm" onclick="toggleSecret('discord_webhook', this)">👁️</button>
                </div>
                <small>Leave empty to keep existing value.</small>
                <p>
                    <button type="button" class="btn-secondary btn-sm" onclick="testNotif('discord')">
                        🔔 Test Discord
                    </button>
                    <span id="discord_test_status" class="test-status"></span>
                </p>
            </div>

            <div class="notif-section">
                <h3>Telegram</h3>
                <label for="telegram_token">Bot Token</label>
                <div class="secret-row">
                    <input type="password" id="telegram_token" name="telegram_token"
                           placeholder="{'••••••••' if telegram_set else '123456:ABC-DEF...'}"
                           autocomplete="off">
                    <button type="button" class="btn-secondary btn-sm" onclick="toggleSecret('telegram_token', this)">👁️</button>
                </div>
                <small>Leave empty to keep existing value.</small>

                <label for="telegram_chat_id" style="margin-top: 1rem;">Chat ID</label>
                <input type="text" id="telegram_chat_id" name="telegram_chat_id"
                       value="{chat_id}" placeholder="-100123456789">
                <p>
                    <button type="button" class="btn-secondary btn-sm" onclick="testNotif('telegram')">
                        🔔 Test Telegram
                    </button>
                    <span id="telegram_test_status" class="test-status"></span>
                </p>
            </div>

            <div class="actions">
                {render_button("Save", "primary", {"type": "submit"})}
                {render_button("Back", "secondary", {"onclick": "location.href='/'"})}
            </div>
        </form>

        <style>
            .notif-section {{
                background: var(--card-bg, #fff);
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 1.2rem 1.5rem;
                margin-bottom: 1.2rem;
            }}
            .notif-section h3 {{
                margin-top: 0;
                margin-bottom: 1rem;
                border-bottom: 2px solid #eee;
                padding-bottom: 0.4rem;
            }}
            .notif-section label {{
                display: block;
                font-weight: 600;
                margin-bottom: 0.4rem;
            }}
            .notif-section input[type="text"],
            .notif-section input[type="password"] {{
                width: 100%;
                padding: 0.5rem;
                border: 1px solid #ccc;
                border-radius: 4px;
                box-sizing: border-box;
                margin-bottom: 0.25rem;
            }}
            .secret-row {{
                display: flex;
                gap: 0.5rem;
                align-items: center;
                margin-bottom: 0.25rem;
            }}
            .secret-row input {{
                flex: 1;
                margin-bottom: 0 !important;
            }}
            small {{
                color: #777;
                font-size: 0.8rem;
                display: block;
                margin-bottom: 0.5rem;
            }}
            .test-status {{
                margin-left: 0.5rem;
                font-size: 0.9rem;
            }}
            .actions {{
                margin-top: 1.5rem;
                display: flex;
                gap: 1rem;
                justify-content: center;
            }}
            body.dark .notif-section {{
                background: #2d3748;
                border-color: #4a5568;
            }}
            body.dark .notif-section h3 {{
                color: #edf2f7;
                border-bottom-color: #4a5568;
            }}
            body.dark .notif-section input {{
                background: #1a202c;
                color: white;
                border-color: #4a5568;
            }}
            body.dark small {{ color: #a0aec0; }}
        </style>
        '''

        js = '''
        <script>
        function toggleSecret(id, btn) {
            var el = document.getElementById(id);
            if (el.type === 'password') {
                el.type = 'text';
                btn.textContent = '🙈';
            } else {
                el.type = 'password';
                btn.textContent = '👁️';
            }
        }

        function testNotif(service) {
            var statusEl = document.getElementById(service + '_test_status');
            statusEl.textContent = 'Sending...';
            statusEl.style.color = '';
            kuasarrApiFetch('/api/notifications/test/' + service, {method: 'POST'})
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        statusEl.textContent = '✅ Sent!';
                        statusEl.style.color = 'var(--success-color, green)';
                    } else {
                        statusEl.textContent = '❌ ' + (data.error || 'Failed');
                        statusEl.style.color = 'var(--error-color, red)';
                    }
                })
                .catch(function(e) {
                    statusEl.textContent = '❌ Request failed';
                    statusEl.style.color = 'var(--error-color, red)';
                });
        }
        </script>
        '''

        return render_form("Notification Settings", form_html, js, active_page="/notifications")

    @app.post('/api/notifications/save')
    @require_api_key
    def notifications_save():
        cfg = Config('Notifications')

        discord_webhook = (request.forms.get('discord_webhook') or '').strip()
        telegram_token = (request.forms.get('telegram_token') or '').strip()
        telegram_chat_id = (request.forms.get('telegram_chat_id') or '').strip()

        if discord_webhook:
            if re.match(r'^https://discord\.com/api/webhooks/\d+/.+$', discord_webhook):
                cfg.save('discord_webhook', discord_webhook)
        if telegram_token:
            cfg.save('telegram_token', telegram_token)
        cfg.save('telegram_chat_id', telegram_chat_id)

        redirect('/notifications')

    @app.post('/api/notifications/test/discord')
    @require_api_key
    def notifications_test_discord():
        response.content_type = 'application/json'
        from kuasarr.providers.notifications import send_discord_message
        try:
            ok = send_discord_message(shared_state, 'Kuasarr Test', 'test')
            if ok:
                return json.dumps({'success': True})
            return json.dumps({'success': False, 'error': 'Webhook not configured or request failed'})
        except Exception:
            return json.dumps({'success': False, 'error': 'Notification dispatch failed'})

    @app.post('/api/notifications/test/telegram')
    @require_api_key
    def notifications_test_telegram():
        response.content_type = 'application/json'
        from kuasarr.providers.notifications import send_telegram_message
        try:
            ok = send_telegram_message(shared_state, 'Kuasarr Test', 'This is a test notification from Kuasarr.')
            if ok:
                return json.dumps({'success': True})
            return json.dumps({'success': False, 'error': 'Token/Chat ID not configured or request failed'})
        except Exception:
            return json.dumps({'success': False, 'error': 'Notification dispatch failed'})

    @app.get('/api/notifications')
    @require_api_key
    def get_notifications_api():
        """Return notification settings in the frontend-compatible format."""
        response.content_type = 'application/json'
        raw = get_notification_settings_data(shared_state).get('settings', {})
        configs = []
        if raw.get('discord_webhook'):
            toggles = raw.get('toggles', {}).get('discord', {})
            configs.append({
                'provider': 'discord',
                'enabled': True,
                'settings': {'webhook_url': raw['discord_webhook']},
                'events': [e for e, v in toggles.items() if v],
            })
        if raw.get('telegram_bot_token'):
            toggles = raw.get('toggles', {}).get('telegram', {})
            configs.append({
                'provider': 'telegram',
                'enabled': True,
                'settings': {
                    'bot_token': raw['telegram_bot_token'],
                    'chat_id': raw.get('telegram_chat_id', ''),
                },
                'events': [e for e, v in toggles.items() if v],
            })
        return json.dumps({'data': {
            'global_enabled': bool(configs),
            'configs': configs,
        }})

    @app.post('/api/notifications')
    @require_api_key
    @require_csrf_token
    def save_notifications_api():
        """Save notification settings from the frontend format."""
        response.content_type = 'application/json'
        try:
            data = json.loads(request.body.read().decode('utf-8'))
        except Exception:
            response.status = 400
            return json.dumps({'error': 'Invalid JSON'})

        configs = data.get('configs', [])
        # Build flat structure expected by the storage layer
        settings = {
            'discord_webhook': '',
            'telegram_bot_token': '',
            'telegram_chat_id': '',
            'toggles': {'discord': {}, 'telegram': {}},
            'silent': {'discord': {}, 'telegram': {}},
        }
        for cfg in configs:
            provider = cfg.get('provider', '')
            cfg_settings = cfg.get('settings', {})
            events = cfg.get('events', [])
            if provider == 'discord':
                settings['discord_webhook'] = cfg_settings.get('webhook_url', '')
                settings['toggles']['discord'] = {e: True for e in events}
            elif provider == 'telegram':
                settings['telegram_bot_token'] = cfg_settings.get('bot_token', '')
                settings['telegram_chat_id'] = cfg_settings.get('chat_id', '')
                settings['toggles']['telegram'] = {e: True for e in events}

        # Save credentials via Config and persist toggles via storage layer
        notification_cfg = Config('Notifications')
        notification_cfg.save('discord_webhook', settings['discord_webhook'])
        notification_cfg.save('telegram_token', settings['telegram_bot_token'])
        notification_cfg.save('telegram_chat_id', settings['telegram_chat_id'])

        notification_settings_db = DataBase(NOTIFICATION_SETTINGS_TABLE)
        for provider in NOTIFICATION_PROVIDERS:
            provider_toggles = settings['toggles'].get(provider, {})
            for notification_type in NOTIFICATION_TYPES:
                enabled_key = _notification_toggle_key(provider, notification_type)
                if notification_type.value in provider_toggles:
                    val = provider_toggles[notification_type.value]
                    notification_settings_db.update_store(
                        enabled_key, 'true' if val else 'false'
                    )

        refresh_notification_settings(shared_state)
        return json.dumps({'data': None})

    # New REST API endpoints for notification settings
    @app.get('/api/notifications/settings')
    @require_api_key
    def notifications_settings_get():
        """Get current notification settings."""
        response.content_type = 'application/json'
        result = get_notification_settings_data(shared_state)
        return result

    @app.post('/api/notifications/settings')
    @require_api_key
    def notifications_settings_post():
        """Save notification settings."""
        response.content_type = 'application/json'
        result = save_notification_settings(shared_state)
        if not result.get("success"):
            response.status = 400
        return result

    @app.post('/api/notifications/test')
    @require_api_key
    def notifications_test():
        """Send a test notification to configured providers."""
        response.content_type = 'application/json'
        result = send_notification_test(shared_state)
        if not result.get("success"):
            response.status = 400
        return result
