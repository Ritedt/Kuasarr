# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import base64
import configparser
import os
import re
import string

from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes
from Cryptodome.Util.Padding import pad

from kuasarr.providers import shared_state
from kuasarr.storage.sqlite_database import DataBase


class Config(object):
    _DEFAULT_CONFIG = {
        'API': [
            ("key", "secret", ""),
        ],
        'WebUI': [
            ("user", "secret", ""),
            ("password", "secret", ""),
        ],
        'JDownloader': [
            ("user", "secret", ""),
            ("password", "secret", ""),
            ("device", "str", ""),
        ],
        'Hostnames': [
            ("ad", "secret", ""),
            ("al", "secret", ""),
            ("by", "secret", ""),
            ("dd", "secret", ""),
            ("dl", "secret", ""),
            ("dt", "secret", ""),
            ("dw", "secret", ""),
            ("fx", "secret", ""),
            ("he", "secret", ""),
            ("mb", "secret", ""),
            ("nk", "secret", ""),
            ("nx", "secret", ""),
            ("sf", "secret", ""),
            ("sl", "secret", ""),
            ("wd", "secret", ""),
            ("wx", "secret", ""),
            ("sj", "secret", ""),
            ("dj", "secret", "")
        ],
        'FlareSolverr': [
            ("url", "str", ""),
        ],
        'Captcha': [
            ("service", "str", "dbc"),  # "dbc" oder "2captcha"
            ("dbc_authtoken", "secret", ""),
            ("twocaptcha_api_key", "secret", ""),
            ("timeout", "str", "120"),
            ("max_retries", "str", "3"),
            ("retry_backoff", "str", "5"),
        ],
                'AD': [
            ("user", "secret", ""),
            ("password", "secret", "")
        ],
        'DL': [
            ("user", "secret", ""),
            ("password", "secret", "")
        ],
        'AL': [
            ("user", "secret", ""),
            ("password", "secret", "")
        ],
        'DD': [
            ("user", "secret", ""),
            ("password", "secret", "")
        ],
        'NX': [
            ("user", "secret", ""),
            ("password", "secret", "")
        ],
        'Sonarr': [
            ("url", "str", ""),
            ("api_key", "secret", "")
        ],
        'Radarr': [
            ("url", "str", ""),
            ("api_key", "secret", "")
        ],
        'Notifications': [
            ("discord_webhook", "secret", ""),
            ("telegram_token", "secret", ""),
            ("telegram_chat_id", "str", ""),
        ],
        'PostProcessing': [
            ("flatten_nested_folders", "bool", "true"),
            ("trigger_rescan", "bool", "true")
        ],
        'BlockedHosters': [
            ("hosters", "secret", "")  # Komma-separierte Liste von Hoster-IDs (verschlüsselt)
        ],
        'HideCX': [
            ("api_key", "secret", "")  # hide.cx API Key (kostenlos unter Settings > Account > Application API Keys)
        ],
        'Connection': [
            ("internal_address", "str", ""),
            ("external_address", "str", "")
        ],
        'PWA': [
            ("install_prompted", "bool", "false")  # Track if PWA install was prompted on Windows EXE
        ]
    }
    __config__ = []

    def __init__(self, section):
        self._configfile = shared_state.values["configfile"]
        self._section = section
        self._config = configparser.RawConfigParser()
        try:
            # Lese existierende Config (falls vorhanden)
            if os.path.exists(self._configfile):
                self._config.read(self._configfile)
            
            # Füge fehlende Sektion hinzu (ohne andere zu löschen)
            if not self._config.has_section(self._section):
                self._set_default_config(self._section)
            
            self.__config__ = self._read_config(self._section)
        except configparser.DuplicateSectionError:
            print('Duplicate Section in Config File')
            raise
        except Exception as e:
            print(f'Unknown error while reading config file: {e}')
            raise

    def _set_default_config(self, section):
        """
        Stellt sicher, dass eine Sektion und alle erwarteten Keys existieren,
        ohne vorhandene Werte zu überschreiben.
        """
        existing_config = configparser.RawConfigParser()
        if os.path.exists(self._configfile):
            existing_config.read(self._configfile)

        if not existing_config.has_section(section):
            existing_config.add_section(section)

        # Ergänze fehlende Keys mit Default-Werten
        for (key, key_type, value) in self._DEFAULT_CONFIG[section]:
            if not existing_config.has_option(section, key):
                existing_config.set(section, key, value)

        with open(self._configfile, 'w') as configfile:
            existing_config.write(configfile)

        self._config = existing_config

    def _get_encryption_params(self):
        crypt_key = DataBase('secrets').retrieve("key")
        crypt_iv = DataBase('secrets').retrieve("iv")
        if crypt_iv and crypt_key:
            return base64.b64decode(crypt_key), base64.b64decode(crypt_iv)
        else:
            crypt_key = get_random_bytes(32)
            crypt_iv = get_random_bytes(16)
            DataBase('secrets').update_store("key", base64.b64encode(crypt_key).decode())
            DataBase('secrets').update_store("iv", base64.b64encode(crypt_iv).decode())
            return crypt_key, crypt_iv

    def _set_to_config(self, section, key, value):
        default_value_type = [param[1] for param in self._DEFAULT_CONFIG[section] if param[0] == key]
        if default_value_type and default_value_type[0] == 'secret' and len(value):
            crypt_key, crypt_iv = self._get_encryption_params()
            cipher = AES.new(crypt_key, AES.MODE_CBC, crypt_iv)
            value = base64.b64encode(cipher.encrypt(pad(value.encode(), AES.block_size)))
            value = 'secret|' + value.decode()
        
        # Lade Config neu vor dem Schreiben um Race-Conditions zu vermeiden
        fresh_config = configparser.RawConfigParser()
        if os.path.exists(self._configfile):
            fresh_config.read(self._configfile)
        
        if not fresh_config.has_section(section):
            fresh_config.add_section(section)
        
        fresh_config.set(section, key, value)
        with open(self._configfile, 'w') as configfile:
            fresh_config.write(configfile)
        
        # Aktualisiere interne Config
        self._config = fresh_config

    def _read_config(self, section):
        return [(key, '', self._config.get(section, key)) for key in self._config.options(section)]

    def _get_from_config(self, scope, key):
        res = [param[2] for param in scope if param[0] == key]
        if not res:
            res = [param[2]
                   for param in self._DEFAULT_CONFIG[self._section] if param[0] == key]
        if [param for param in self._DEFAULT_CONFIG[self._section] if param[0] == key and param[1] == 'secret']:
            value = res[0].strip('\'"')
            if value.startswith("secret|"):
                crypt_key, crypt_iv = self._get_encryption_params()
                cipher = AES.new(crypt_key, AES.MODE_CBC, crypt_iv)
                decrypted_payload = cipher.decrypt(base64.b64decode(value[7:])).decode("utf-8").strip()
                final_payload = "".join(filter(lambda c: c in string.printable, decrypted_payload))
                return final_payload
            else:  ## Loaded value is not encrypted, return as is
                if len(value) > 0:
                    self.save(key, value)
                return value
        elif [param for param in self._DEFAULT_CONFIG[self._section] if param[0] == key and param[1] == 'bool']:
            return True if len(res) and res[0].strip('\'"').lower() == 'true' else False
        else:
            return res[0].strip('\'"') if len(res) > 0 else False

    def save(self, key, value):
        self._set_to_config(self._section, key, value)
        return

    def get(self, key, default=None):
        res = self._get_from_config(self.__config__, key)
        if res is False and default is not None:
            return default
        return res


def get_clean_hostnames(shared_state):
    hostnames = Config('Hostnames')
    set_hostnames = {}

    def clean_up_hostname(host, strg, hostnames):
        if strg and '/' in strg:
            strg = strg.replace('https://', '').replace('http://', '')
            strg = re.findall(r'([a-z-.]*\.[a-z]*)', strg)[0]
            hostnames.save(host, strg)
        if strg and re.match(r'.*[A-Z].*', strg):
            hostnames.save(host, strg.lower())
        if strg:
            print(f'Using "{strg}" as hostname for "{host}"')
        return strg

    for name in shared_state.values["sites"]:
        name = name.lower()
        hostname = clean_up_hostname(name, hostnames.get(name), hostnames)
        if hostname:
            set_hostnames[name] = hostname

    return set_hostnames



