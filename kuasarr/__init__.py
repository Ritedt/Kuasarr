# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import json
from pathlib import Path

def _read_version():
    for p in [
        Path(__file__).parent.parent / "version.json",
        Path(__file__).parent / "version.json",
    ]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")).get("version", "0.0.0")
            except Exception:
                pass
    return "0.0.0"

__version__ = _read_version()

import argparse
import multiprocessing
import os
import re
import socket
import sys
import tempfile
import time
from urllib.parse import urlparse, urljoin, parse_qs

import requests
import dukpy

from kuasarr.api import get_api
from kuasarr.providers import shared_state, version
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher
from kuasarr.providers.log import info, debug
from kuasarr.providers.notifications import send_discord_message
from kuasarr.storage.config import Config, get_clean_hostnames
from kuasarr.storage.setup import (
    path_config,
    connection_config,
    hostnames_config,
    hostname_credentials_config,
    flaresolverr_config,
    jdownloader_config,
    dbc_credentials_config,
)
from kuasarr.storage.sqlite_database import DataBase
from kuasarr.providers.pwa_installer import should_prompt_pwa_install, mark_pwa_prompted, open_pwa_install_page


def run():
    with multiprocessing.Manager() as manager:
        shared_state_dict = manager.dict()
        shared_state_lock = manager.Lock()
        shared_state.set_state(shared_state_dict, shared_state_lock)

        parser = argparse.ArgumentParser()
        parser.add_argument("--port", help="Desired Port, defaults to 9999")
        parser.add_argument("--internal_address", help="Must be provided when running in Docker")
        parser.add_argument("--external_address", help="External address for CAPTCHA notifications")
        parser.add_argument("--discord", help="Discord Webhook URL")
        parser.add_argument("--hostnames", help="Public HTTP(s) Link that contains hostnames definition.")
        parser.add_argument("--debug", help="Enable debug logging", action="store_true")
        arguments = parser.parse_args()

        if arguments.debug:
            os.environ['DEBUG'] = '1'

        if sys.stdout is not None:
            sys.stdout = Unbuffered(sys.stdout)

        banner_lines = [
            f"Kuasarr {version.get_version()} by weedo078 (fork of RiX1337/kuasarr)",
            "https://github.com/weedo078/kuasarr",
        ]
        banner_width = max(len(line) for line in banner_lines) + 4
        top_border = "+" + "-" * (banner_width - 2) + "+"
        bottom_border = top_border
        formatted_lines = [f"| {line.ljust(banner_width - 4)} |" for line in banner_lines]
        print("\n".join([top_border, *formatted_lines, bottom_border]))
       
        print("\n===== Startup Info =====")
        port = int('9999')
        config_path = ""
        
        # Port aus CLI-Argument übernehmen (gilt für Docker und Non-Docker)
        if arguments.port:
            port = int(arguments.port)
        
        if os.environ.get('DOCKER'):
            config_path = "/config"
            if not arguments.internal_address:
                print(
                    f"You must set the INTERNAL_ADDRESS variable to a locally reachable URL, e.g. http://192.168.1.1:{port}")
                print("The local URL will be used by Radarr/Sonarr to connect to kuasarr")
                print("Stopping kuasarr...")
                sys.exit(1)
        else:
            internal_address = f'http://{check_ip()}:{port}'

        if arguments.internal_address:
            internal_address = arguments.internal_address
        if arguments.external_address:
            external_address = arguments.external_address
        else:
            external_address = internal_address

        validate_address(internal_address, "--internal_address")
        validate_address(external_address, "--external_address")

        shared_state.set_connection_info(internal_address, external_address, port)

        if not config_path:
            config_path_file = "kuasarr.conf"
            if not os.path.exists(config_path_file):
                path_config(shared_state)
            with open(config_path_file, "r") as f:
                config_path = f.readline().strip()

        os.makedirs(config_path, exist_ok=True)

        try:
            temp_file = tempfile.TemporaryFile(dir=config_path)
            temp_file.close()
        except Exception as e:
            print(f'Could not access "{config_path}": {e}"'
                  f'Stopping kuasarr...')
            sys.exit(1)

        shared_state.set_files(config_path)
        shared_state.update("config", Config)
        shared_state.update("database", DataBase)
        supported_hostnames = extract_allowed_keys(Config._DEFAULT_CONFIG, 'Hostnames')
        shared_state.update("sites", [key.upper() for key in supported_hostnames])
        shared_state.update("user_agent",
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
        shared_state.update("helper_active", False)

        # Captcha Config (supports DBC and 2Captcha)
        captcha_config = Config('Captcha')

        def _to_bool(value, default=False):
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "on"}

        def _to_positive_int(value, default):
            try:
                return max(1, int(str(value).strip()))
            except (TypeError, ValueError, AttributeError):
                return default

        # Captcha service selection
        captcha_service = (captcha_config.get('service') or 'dbc').lower().strip()
        shared_state.update("captcha_service", captcha_service)

        # DBC Credentials: Config > ENV (Token only)
        dbc_authtoken_config = captcha_config.get('dbc_authtoken') or ""
        dbc_authtoken = os.getenv("DBC_AUTHTOKEN", dbc_authtoken_config).strip()
        
        # 2Captcha API Key
        twocaptcha_api_key = captcha_config.get('twocaptcha_api_key') or ""
        twocaptcha_api_key = os.getenv("TWOCAPTCHA_API_KEY", twocaptcha_api_key).strip()
        shared_state.update("twocaptcha_api_key", twocaptcha_api_key)
        
        # Captcha Settings
        captcha_timeout = _to_positive_int(os.getenv("CAPTCHA_TIMEOUT", captcha_config.get('timeout')), 120)
        captcha_max_retries = _to_positive_int(os.getenv("CAPTCHA_MAX_RETRIES", captcha_config.get('max_retries')), 3)
        captcha_retry_backoff = _to_positive_int(os.getenv("CAPTCHA_RETRY_BACKOFF", captcha_config.get('retry_backoff')), 5)
        dbc_max_concurrent = _to_positive_int(os.getenv("DBC_MAX_CONCURRENT", "1"), 1)
        
        # Store DBC config in shared state (Token based only)
        dbc_config_dict = {
            "username": "",
            "password": "",
            "authtoken": dbc_authtoken,
            "timeout": captcha_timeout,
            "max_retries": captcha_max_retries,
            "retry_backoff": captcha_retry_backoff,
        }
        shared_state.update("dbc_config", dbc_config_dict)
        shared_state.update("dbc_max_concurrent", dbc_max_concurrent)
        shared_state.update("dbc_retry_backoff", captcha_retry_backoff)
        
        # Check if captcha service is configured
        if captcha_service == '2captcha':
            dbc_enabled = bool(twocaptcha_api_key)
        else:
            dbc_enabled = bool(dbc_authtoken)
        shared_state.update("dbc_enabled", dbc_enabled)
        
        if dbc_enabled:
            if captcha_service == '2captcha':
                info(f"Captcha: 2Captcha configured (Timeout={captcha_timeout}s, Max-Retries={captcha_max_retries})")
            else:
                info(f"Captcha: DBC configured (Timeout={captcha_timeout}s, Max-Retries={captcha_max_retries})")
        else:
            info("Captcha: Not configured (no credentials found)")
            dbc_credentials_config(shared_state)
            
            # Re-read config after setup
            captcha_config = Config('Captcha')
            captcha_service = (captcha_config.get('service') or 'dbc').lower().strip()
            dbc_authtoken = captcha_config.get('dbc_authtoken') or ""
            twocaptcha_api_key = captcha_config.get('twocaptcha_api_key') or ""
            
            if captcha_service == '2captcha':
                dbc_enabled = bool(twocaptcha_api_key)
            else:
                dbc_enabled = bool(dbc_authtoken) # Simplified for token-based auth
            
            shared_state.update("captcha_service", captcha_service)
            shared_state.update("dbc_enabled", dbc_enabled)
            shared_state.update("twocaptcha_api_key", twocaptcha_api_key)
            
            # Update dbc_config_dict for shared_state
            dbc_config_dict["authtoken"] = dbc_authtoken
            shared_state.update("dbc_config", dbc_config_dict)

        print(f'Config path: "{config_path}"')

        try:
            if arguments.hostnames:
                hostnames_link = arguments.hostnames

                if is_valid_url(hostnames_link):
                    if "pastebin.com" in hostnames_link:
                        hostnames_link = make_raw_pastebin_link(hostnames_link)

                    print(f"Extracting hostnames from {hostnames_link}...")
                    allowed_keys = supported_hostnames
                    max_keys = len(allowed_keys)
                    shorthand_list = ', '.join(
                        [f'"{key}"' for key in allowed_keys[:-1]]) + ' and ' + f'"{allowed_keys[-1]}"'
                    print(f'There are up to {max_keys} hostnames currently supported: {shorthand_list}')
                    
                    if "/ini.html" in hostnames_link:
                        data = build_ini_from_ini_html(hostnames_link)
                    else:
                        data = requests.get(hostnames_link).text
                    
                    results = extract_kv_pairs(data, allowed_keys)

                    extracted_hostnames = 0

                    if results:
                        hostnames = Config('Hostnames')
                        for shorthand, hostname in results.items():
                            domain_check = shared_state.extract_valid_hostname(hostname, shorthand)
                            valid_domain = domain_check.get('domain', None)
                            if valid_domain:
                                hostnames.save(shorthand, hostname)
                                extracted_hostnames += 1
                                print(f'Hostname for "{shorthand}" successfully set to "{hostname}"')
                            else:
                                print(f'Skipping invalid hostname for "{shorthand}" ("{hostname}")')
                        if extracted_hostnames == max_keys:
                            print(f'All {max_keys} hostnames successfully extracted!')
                            print('You can now remove the hostnames link from the command line / environment variable.')
                    else:
                        print(f'No Hostnames found at "{hostnames_link}". '
                              'Ensure to pass a plain hostnames list, not html or json!')
                else:
                    print(f'Invalid hostnames URL: "{hostnames_link}"')
        except Exception as e:
            print(f'Error parsing hostnames link: "{e}"')

        print("\n===== Configuration =====")
        api_key = Config('API').get('key')
        if not api_key:
            api_key = shared_state.generate_api_key()

        hostnames = get_clean_hostnames(shared_state)
        if not hostnames:
            hostnames_config(shared_state)
            hostnames = get_clean_hostnames(shared_state)
        print(f"You have [{len(hostnames)} of {len(Config._DEFAULT_CONFIG['Hostnames'])}] supported hostnames set up")
        print(f"For efficiency it is recommended to set up as few hostnames as needed.")

        flaresolverr_url = Config('FlareSolverr').get('url')

        ad = Config('Hostnames').get('ad')
        if ad:
            if not flaresolverr_url:
                flaresolverr_config(shared_state)
                flaresolverr_url = Config('FlareSolverr').get('url')
            else:
                print(f'Using Flaresolverr URL: "{flaresolverr_url}"')
            # AD requires no login, only FlareSolverr for Cloudflare bypass

        al = Config('Hostnames').get('al')
        if al:
            if not flaresolverr_url:
                flaresolverr_config(shared_state)
                flaresolverr_url = Config('FlareSolverr').get('url')
            else:
                print(f'Using Flaresolverr URL: "{flaresolverr_url}"')
            user = Config('AL').get('user')
            password = Config('AL').get('password')
            if not user or not password:
                hostname_credentials_config(shared_state, "AL", al)

        dd = Config('Hostnames').get('dd')
        if dd:
            user = Config('DD').get('user')
            password = Config('DD').get('password')
            if not user or not password:
                hostname_credentials_config(shared_state, "DD", dd)

        dl = Config('Hostnames').get('dl')
        if dl:
            user = Config('DL').get('user')
            password = Config('DL').get('password')
            if not user or not password:
                hostname_credentials_config(shared_state, "DL", dl)

        nx = Config('Hostnames').get('nx')
        if nx:
            user = Config('NX').get('user')
            password = Config('NX').get('password')
            if not user or not password:
                hostname_credentials_config(shared_state, "NX", nx)

        config = Config('JDownloader')
        user = config.get('user')
        password = config.get('password')
        device = config.get('device')

        if not user or not password or not device:
            jdownloader_config(shared_state)

        print("\n===== Notifications =====")
        discord_url = ""
        if arguments.discord:
            discord_webhook_pattern = r'^https://discord\.com/api/webhooks/\d+/[\w-]+$'
            if re.match(discord_webhook_pattern, arguments.discord):
                shared_state.update("webhook", arguments.discord)
                print(f"Using Discord Webhook URL for notifications.")
                discord_url = arguments.discord
            else:
                print(f"Invalid Discord Webhook URL provided: {arguments.discord}")
        else:
            print("No Discord Webhook URL provided")
        shared_state.update("discord", discord_url)

        print("\n===== API Information =====")
        print('Setup instructions: "https://github.com/rix1337/kuasarr?tab=readme-ov-file#instructions"')
        print(f"URL: \"{shared_state.values['internal_address']}\"")
        print(f'API key: "{api_key}" (without quotes)')

        if external_address != internal_address:
            print(f"External URL: \"{shared_state.values['external_address']}\"")

        # PWA installation prompt for Windows EXE on first run
        if should_prompt_pwa_install(Config):
            info("First run detected - opening PWA installation page in browser...")
            open_pwa_install_page(internal_address, delay=5)
            mark_pwa_prompted(Config)

        print("\n===== kuasarr Info Log =====")
        if os.getenv('DEBUG'):
            print("=====    / Debug Log   =====")

        protected = shared_state.get_db("protected").retrieve_all_titles()
        if protected:
            package_count = len(protected)
            info(
                f"CAPTCHA-Solution required for {package_count} package{'s' if package_count > 1 else ''} at: "
                f"\"{shared_state.values['external_address']}/captcha\"!"
            )

        jdownloader = multiprocessing.Process(
            target=jdownloader_connection,
            args=(shared_state_dict, shared_state_lock)
        )
        jdownloader.start()

        updater = multiprocessing.Process(
            target=update_checker,
            args=(shared_state_dict, shared_state_lock)
        )
        updater.start()

        # Start DeathByCaptcha Dispatcher if configured
        dbc_dispatcher = None
        if shared_state.values.get("dbc_enabled"):
            dbc_dispatcher = DBCDispatcher(state_module=shared_state)
            dbc_dispatcher.start()
            info("DBC Dispatcher started")
        else:
            info("DBC not configured - captcha solving disabled")

        try:
            get_api(shared_state_dict, shared_state_lock)
        except Exception as e:
            if not isinstance(e, KeyboardInterrupt):
                info(f"Kuasarr encountered a critical error: {e}")
        finally:
            info("Stopping all background processes...")
            if dbc_dispatcher:
                dbc_dispatcher.stop()
            if 'jdownloader' in locals() and jdownloader.is_alive():
                jdownloader.terminate()
                jdownloader.join(timeout=2)
            if 'updater' in locals() and updater.is_alive():
                updater.terminate()
                updater.join(timeout=2)
            info("Kuasarr stopped.")
            sys.exit(0)


def update_checker(shared_state_dict, shared_state_lock):
    try:
        shared_state.set_state(shared_state_dict, shared_state_lock)

        message = "!!! UPDATE AVAILABLE !!!"
        link = version.LATEST_RELEASE_LINK

        shared_state.update("last_checked_version", f"v.{version.get_version()}")

        while True:
            try:
                update_available = version.newer_version_available()
                link = version.LATEST_RELEASE_LINK
            except (BrokenPipeError, EOFError, ConnectionResetError):
                debug("Update Checker: Shared state manager disconnected. Stopping...")
                break
            except Exception as e:
                info(f"Error getting latest version: {e}")
                info(f'Please manually check: "{link}" for more information!')
                update_available = None

            if update_available and shared_state.values.get("last_checked_version") != update_available:
                shared_state.update("last_checked_version", update_available)
                info(message)
                info(f"Please update to {update_available} as soon as possible!")
                info(f'Release notes at: "{link}"')
                update_available = {
                    "version": update_available,
                    "link": link
                }
                send_discord_message(shared_state, message, "kuasarr_update", details=update_available)

            # wait one hour before next check
            time.sleep(60 * 60)
    except (BrokenPipeError, EOFError, ConnectionResetError):
        debug("Update Checker: Shared state manager disconnected. Stopping...")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        info(f"Update Checker encountered an unexpected error: {e}")


def jdownloader_connection(shared_state_dict, shared_state_lock):
    try:
        shared_state.set_state(shared_state_dict, shared_state_lock)

        shared_state.set_device_from_config()

        connection_established = shared_state.get_device() and shared_state.get_device().name
        if not connection_established:
            i = 0
            while i < 10:
                i += 1
                info(f'Connection {i} to JDownloader failed. Device name: "{shared_state.values.get("device")}"')
                time.sleep(60)
                shared_state.set_device_from_config()
                connection_established = shared_state.get_device() and shared_state.get_device().name
                if connection_established:
                    break

        try:
            info(f'Connection to JDownloader successful. Device name: "{shared_state.get_device().name}"')
        except Exception as e:
            info(f'Error connecting to JDownloader: {e}! Stopping kuasarr!')
            sys.exit(1)

        try:
            shared_state.set_device_settings()
        except Exception as e:
            print(f"Error checking settings: {e}")

        try:
            shared_state.update_jdownloader()
        except Exception as e:
            print(f"Error updating JDownloader: {e}")

        try:
            shared_state.start_downloads()
        except Exception as e:
            print(f"Error starting downloads: {e}")

    except (BrokenPipeError, EOFError, ConnectionResetError):
        debug("JDownloader Connection: Shared state manager disconnected. Stopping...")
    except KeyboardInterrupt:
        pass


class Unbuffered(object):
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()

    def writelines(self, datas):
        self.stream.writelines(datas)
        self.stream.flush()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)


def check_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 0))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def build_ini_from_ini_html(url: str) -> str:
    def get(u: str) -> str:
        r = requests.get(u, timeout=10)
        r.raise_for_status()
        return r.text

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    data_js = get(urljoin(f"{parsed.scheme}://{parsed.netloc}", "data.js"))

    hostnames = dukpy.evaljs("""
    var window = {};
    %s
    window.HOSTNAMES;
    """ % data_js)

    excluded = set()
    if "exclude" in params:
        excluded = set(params["exclude"][0].split(","))

    lines = []
    for h in hostnames:
        if h["key"] not in excluded:
            lines.append(f"{h['key']} = {h['name']}")

    return "\n".join(lines) + "\n"


def make_raw_pastebin_link(url):
    """
    Takes a Pastebin URL and ensures it is a raw link.
    If it's not a Pastebin URL, it returns the URL unchanged.
    """
    # Check if the URL is already a raw Pastebin link
    if re.match(r"https?://(?:www\.)?pastebin\.com/raw/\w+", url):
        return url  # Already raw, return as is

    # Check if the URL is a standard Pastebin link
    pastebin_pattern = r"https?://(?:www\.)?pastebin\.com/(\w+)"
    match = re.match(pastebin_pattern, url)

    if match:
        paste_id = match.group(1)
        print(f"The link you provided is not a raw Pastebin link. Attempting to convert it to a raw link from {url}...")
        return f"https://pastebin.com/raw/{paste_id}"

    return url  # Not a Pastebin link, return unchanged


def is_valid_url(url):
    if "https://pastebin.com/raw/eX4Mpl3" in url:
        print("Example URL detected. Please provide a valid URL found on pastebin or another public site!")
        return False

    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_address(address, name):
    if not address.startswith("http"):
        sys.exit(f"Error: {name} '{address}' is invalid. It must start with 'http'.")

    colon_count = address.count(":")
    if colon_count < 1 or colon_count > 2:
        sys.exit(
            f"Error: {name} '{address}' is invalid. It must contain 1 or 2 colons, but it has {colon_count}.")


def extract_allowed_keys(config, section):
    """
    Extracts allowed keys from the specified section in the configuration.

    :param config: The configuration dictionary.
    :param section: The section from which to extract keys.
    :return: A list of allowed keys.
    """
    if section not in config:
        raise ValueError(f"Section '{section}' not found in configuration.")
    return [key for key, *_ in config[section]]


def extract_kv_pairs(input_text, allowed_keys):
    """
    Extracts key-value pairs from the given text where keys match allowed_keys.

    :param input_text: The input text containing key-value pairs.
    :param allowed_keys: A list of allowed two-letter shorthand keys.
    :return: A dictionary of extracted key-value pairs.
    """
    kv_pattern = re.compile(rf"^({'|'.join(map(re.escape, allowed_keys))})\s*=\s*(.*)$")
    kv_pairs = {}

    for line in input_text.splitlines():
        match = kv_pattern.match(line.strip())
        if match:
            key, value = match.groups()
            kv_pairs[key] = value
        else:
            print(f"Skipping line because it does not contain any supported hostname: {line}")

    return kv_pairs



