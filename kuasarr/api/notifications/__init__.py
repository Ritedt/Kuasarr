# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import html
import json

from bottle import request, response

from kuasarr.providers.ui.html_templates import render_form, render_button
from kuasarr.storage.config import Config


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
            fetch('/api/notifications/test/' + service, {method: 'POST'})
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

        return render_form("Notification Settings", form_html, js)

    @app.post('/api/notifications/save')
    def notifications_save():
        from bottle import redirect
        cfg = Config('Notifications')

        discord_webhook = (request.forms.get('discord_webhook') or '').strip()
        telegram_token = (request.forms.get('telegram_token') or '').strip()
        telegram_chat_id = (request.forms.get('telegram_chat_id') or '').strip()

        if discord_webhook:
            cfg.save('discord_webhook', discord_webhook)
        if telegram_token:
            cfg.save('telegram_token', telegram_token)
        cfg.save('telegram_chat_id', telegram_chat_id)

        redirect('/notifications')

    @app.post('/api/notifications/test/discord')
    def notifications_test_discord():
        response.content_type = 'application/json'
        from kuasarr.providers.notifications import send_discord_message
        try:
            ok = send_discord_message(shared_state, 'Kuasarr Test', 'test')
            if ok:
                return json.dumps({'success': True})
            return json.dumps({'success': False, 'error': 'Webhook not configured or request failed'})
        except Exception as e:
            return json.dumps({'success': False, 'error': str(e)})

    @app.post('/api/notifications/test/telegram')
    def notifications_test_telegram():
        response.content_type = 'application/json'
        from kuasarr.providers.notifications import send_telegram_message
        try:
            ok = send_telegram_message(shared_state, 'Kuasarr Test', 'This is a test notification from Kuasarr.')
            if ok:
                return json.dumps({'success': True})
            return json.dumps({'success': False, 'error': 'Token/Chat ID not configured or request failed'})
        except Exception as e:
            return json.dumps({'success': False, 'error': str(e)})
