# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import json
import os

import requests

from kuasarr.providers.imdb_metadata import get_imdb_id_from_title
from kuasarr.providers.imdb_metadata import get_poster_link
from kuasarr.providers.log import info

# Discord message flag for suppressing notifications
SUPPRESS_NOTIFICATIONS = 1 << 12  # 4096

silent = False
if os.getenv('SILENT'):
    silent = True


def send_telegram_message(shared_state, title, description):
    """
    Sends a Telegram message to the bot provided in the config.
    """
    from kuasarr.storage.config import Config
    
    token = Config('Notifications').get('telegram_token')
    chat_id = Config('Notifications').get('telegram_chat_id')
    
    if not token or not chat_id:
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    text = f"<b>{title}</b>\n\n{description}"
    
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, data=data, timeout=10)
        if response.status_code != 200:
            info(f"Failed to send message to Telegram. Status code: {response.status_code}")
            return False
        return True
    except Exception as e:
        info(f"Error sending Telegram message: {e}")
        return False


def send_discord_message(shared_state, title, case, imdb_id=None, details=None, source=None):
    """
    Sends a Discord message to the webhook provided in the shared state or config, based on the specified case.
    """
    from kuasarr.storage.config import Config
    
    discord_url = shared_state.values.get("discord")
    if not discord_url:
        discord_url = Config('Notifications').get('discord_webhook')
        
    if not discord_url:
        return False

    poster_object = None
    if case == "unprotected" or case == "captcha":
        if not imdb_id and " " not in title:  # this should prevent imdb_search for ebooks and magazines
            imdb_id = get_imdb_id_from_title(shared_state, title)
        if imdb_id:
            poster_link = get_poster_link(shared_state, imdb_id)
            if poster_link:
                poster_object = {
                    'url': poster_link
                }

    # Decide the embed content based on the case
    if case == "unprotected":
        description = 'No CAPTCHA required. Links were added directly!'
        fields = None
    elif case == "solved":
        description = 'CAPTCHA solved by CaptchaHelper!'
        fields = None
    elif case == "failed":
        description = 'CaptchaHelper failed to solve the CAPTCHA! Package marked as failed.'
        fields = None
    elif case == "captcha":
        description = 'Download will proceed, once the CAPTCHA has been solved.'
        fields = [
            {
                'name': 'Solve CAPTCHA',
                'value': f"Open [this link]({shared_state.values['external_address']}/captcha) to solve the CAPTCHA.",
            }
        ]
        if not shared_state.values.get("helper_active"):
            fields.append({
                'name': 'CaptchaHelper',
                'value': 'Aktiviere den integrierten CaptchaHelper, um CAPTCHAs automatisch zu lösen.',
            })
    elif case == "kuasarr_update":
        description = f'Please update to {details["version"]} as soon as possible!'
        if details:
            fields = [
                {
                    'name': 'Release notes at: ',
                    'value': f'[GitHub.com: rix1337/kuasarr/{details["version"]}]({details["link"]})',
                }
            ]
        else:
            fields = None
    else:
        info(f"Unknown notification case: {case}")
        return False

    data = {
        'username': 'kuasarr',
        'avatar_url': 'https://raw.githubusercontent.com/rix1337/kuasarr/main/kuasarr.png',
        'embeds': [{
            'title': title,
            'description': description,
        }]
    }

    if source and source.startswith("http"):
        if not fields:
            fields = []
        fields.append({
            'name': 'Source',
            'value': f'[View release details here]({source})',
        })

    if fields:
        data['embeds'][0]['fields'] = fields

    if poster_object:
        data['embeds'][0]['thumbnail'] = poster_object
        data['embeds'][0]['image'] = poster_object
    elif case == "kuasarr_update":
        data['embeds'][0]['thumbnail'] = {
            'url': "https://raw.githubusercontent.com/rix1337/kuasarr/main/kuasarr.png"
        }

    if silent and case not in ["failed", "kuasarr_update"]:
        data['flags'] = SUPPRESS_NOTIFICATIONS

    # Send to Telegram as well if configured
    send_telegram_message(shared_state, title, description)

    response = requests.post(discord_url, data=json.dumps(data),
                             headers={"Content-Type": "application/json"})
    if response.status_code != 204:
        info(f"Failed to send message to Discord webhook. Status code: {response.status_code}")
        return False

    return True



