# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import base64
import json
import random
import re
import xml.dom.minidom
from urllib.parse import urlparse

import dukpy
import requests
from Cryptodome.Cipher import AES
from bs4 import BeautifulSoup

from kuasarr.providers.network.cloudflare import is_cloudflare_challenge, ensure_session_cf_bypassed
from kuasarr.providers.log import info, debug


class CNL:
    def __init__(self, crypted_data):
        self.crypted_data = crypted_data

    def jk_eval(self, f_def):
        js_code = f"""
        {f_def}
        f();
        """

        result = dukpy.evaljs(js_code).strip()

        return result

    def aes_decrypt(self, data, key):
        try:
            encrypted_data = base64.b64decode(data)
        except Exception as e:
            raise ValueError("Failed to decode base64 data") from e

        try:
            key_bytes = bytes.fromhex(key)
        except Exception as e:
            raise ValueError("Failed to convert key to bytes") from e

        iv = key_bytes
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)

        try:
            decrypted_data = cipher.decrypt(encrypted_data)
        except ValueError as e:
            raise ValueError("Decryption failed") from e

        try:
            return decrypted_data.decode('utf-8').replace('\x00', '').replace('\x08', '')
        except UnicodeDecodeError as e:
            raise ValueError("Failed to decode decrypted data") from e

    def decrypt(self):
        crypted = self.crypted_data[2]
        jk = "function f(){ return \'" + self.crypted_data[1] + "';}"
        key = self.jk_eval(jk)
        uncrypted = self.aes_decrypt(crypted, key)
        urls = [result for result in uncrypted.split("\r\n") if len(result) > 0]

        return urls


class DLC:
    def __init__(self, shared_state, dlc_file):
        self.shared_state = shared_state
        self.data = dlc_file
        self.KEY = b"cb99b5cbc24db398"
        self.IV = b"9bc24cb995cb8db3"
        self.API_URL = "http://service.jdownloader.org/dlcrypt/service.php?srcType=dlc&destType=pylo&data="

    def parse_packages(self, start_node):
        return [
            (
                base64.b64decode(node.getAttribute("name")).decode("utf-8"),
                self.parse_links(node)
            )
            for node in start_node.getElementsByTagName("package")
        ]

    def parse_links(self, start_node):
        return [
            base64.b64decode(node.getElementsByTagName("url")[0].firstChild.data).decode("utf-8")
            for node in start_node.getElementsByTagName("file")
        ]

    def decrypt(self):
        if not isinstance(self.data, bytes):
            raise TypeError("data must be bytes.")

        all_urls = []

        try:
            data = self.data.strip()

            data += b"=" * (-len(data) % 4)

            dlc_key = data[-88:].decode("utf-8")
            dlc_data = base64.b64decode(data[:-88])

            headers = {'User-Agent': self.shared_state.values["user_agent"]}

            dlc_content = requests.get(self.API_URL + dlc_key, headers=headers, timeout=10).content.decode("utf-8")

            rc = base64.b64decode(re.search(r"<rc>(.+)</rc>", dlc_content, re.S).group(1))[:16]

            cipher = AES.new(self.KEY, AES.MODE_CBC, self.IV)
            key = iv = cipher.decrypt(rc)

            cipher = AES.new(key, AES.MODE_CBC, iv)
            xml_data = base64.b64decode(cipher.decrypt(dlc_data)).decode("utf-8")

            root = xml.dom.minidom.parseString(xml_data).documentElement
            content_node = root.getElementsByTagName("content")[0]

            packages = self.parse_packages(content_node)

            for package in packages:
                urls = package[1]
                all_urls.extend(urls)

        except Exception as e:
            info("DLC Error: " + str(e))
            return None

        return all_urls


def get_filecrypt_links(shared_state, token, title, url, password=None, mirror=None):
    """
    Robust Filecrypt fetch:
    - Always check & bypass Cloudflare with FlareSolverr when necessary.
    - Detect password input more reliably.
    - Use session consistently and update user-agent cleanly.
    """

    info("Attempting to decrypt Filecrypt link: " + url)
    session = requests.Session()
    headers = {'User-Agent': shared_state.values["user_agent"]}

    # Ensure we are not blocked by Cloudflare before parsing or posting
    session, headers, output = ensure_session_cf_bypassed(info, shared_state, session, url, headers)
    if not session or not output:
        return False

    soup = BeautifulSoup(output.text, 'html.parser')

    password_field = None
    try:
        # Search for input elements that look like password fields:
        input_elem = soup.find('input', attrs={'type': 'password'})
        if not input_elem:
            input_elem = soup.find('input', placeholder=lambda v: v and 'password' in v.lower())
        if not input_elem:
            # fallback: name contains 'pass' or 'password'
            input_elem = soup.find('input',
                                   attrs={'name': lambda v: v and ('pass' in v.lower() or 'password' in v.lower())})
        if input_elem and input_elem.has_attr('name'):
            password_field = input_elem['name']
            info("Password field name identified: " + password_field)
    except Exception as e:
        # narrow catch so real errors bubble up elsewhere
        info(f"Password-field detection error: {e}")

    # If we have a password to submit and a field to submit to, post it.
    if password and password_field:
        info("Using Password: " + password)
        post_headers = {'User-Agent': shared_state.values["user_agent"],
                        'Content-Type': 'application/x-www-form-urlencoded'}
        data = {password_field: password}
        try:
            output = session.post(output.url, data=data, headers=post_headers, timeout=30)
        except requests.RequestException as e:
            info(f"POSTing password failed: {e}")
            return False

        # After posting, Cloudflare could reappear; ensure still bypassed
        if output.status_code == 403 or is_cloudflare_challenge(output.text):
            info("Encountered Cloudflare after password POST. Re-running FlareSolverr...")
            session, headers, output = ensure_session_cf_bypassed(info, shared_state, session, output.url, headers)
            if not session or not output:
                return False

    else:
        pass

    url = output.url
    soup = BeautifulSoup(output.text, 'html.parser')
    # Helper to apply a password and refresh soup/output (with optional CF-bypass re-check)
    def _apply_password(pwd, current_output):
        try:
            post_headers = {
                'User-Agent': shared_state.values["user_agent"],
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            new_output = session.post(current_output.url, data={password_field: pwd}, headers=post_headers, timeout=30)
        except requests.RequestException as e:
            info(f"POSTing password failed: {e}")
            return None, None

        # After posting, Cloudflare could reappear; ensure still bypassed
        if new_output.status_code == 403 or is_cloudflare_challenge(new_output.text):
            info("Encountered Cloudflare after password POST. Re-running FlareSolverr...")
            new_session, new_headers, new_output = ensure_session_cf_bypassed(info, shared_state, session, new_output.url,
                                                                              headers)
            if not new_session or not new_output:
                return None, None
        new_soup = BeautifulSoup(new_output.text, 'html.parser')
        return new_output, new_soup

    if bool(soup.find_all("input", {"id": "p4assw0rt"})):
        info(f"Password was wrong or missing for {title}. Trying fallbacks...")

        # Determine fallback passwords (serienfans.org default, funxd via custom logo)
        fallback_pw = "serienfans.org"
        try:
            img = soup.find("img", {"id": "customlogo"})
            if img and img.get("src") and "/css/custom/f38ed.png" in img.get("src"):
                fallback_pw = "funxd"
        except Exception as e:
            debug(f"Password logo detection failed: {e}")

        tried_pw = []

        if password_field:
            for pwd in [password or "", fallback_pw]:
                if not pwd or pwd in tried_pw:
                    continue
                tried_pw.append(pwd)
                info(f"Trying fallback password: {pwd}")
                output, soup = _apply_password(pwd, output)
                if output and soup and not bool(soup.find_all("input", {"id": "p4assw0rt"})):
                    break

        if not output or not soup or bool(soup.find_all("input", {"id": "p4assw0rt"})):
            info(f"Password could not be applied for {title}")
            return False

    no_captcha_present = bool(soup.find("form", {"class": "cnlform"}))
    if no_captcha_present:
        info("No CAPTCHA present. Skipping token!")
    else:
        circle_captcha = bool(soup.find_all("div", {"class": "circle_captcha"}))
        i = 0
        while circle_captcha and i < 3:
            random_x = str(random.randint(100, 200))
            random_y = str(random.randint(100, 200))
            output = session.post(url, data="buttonx.x=" + random_x + "&buttonx.y=" + random_y,
                                  headers={'User-Agent': shared_state.values["user_agent"],
                                           'Content-Type': 'application/x-www-form-urlencoded'})
            url = output.url
            soup = BeautifulSoup(output.text, 'html.parser')
            circle_captcha = bool(soup.find_all("div", {"class": "circle_captcha"}))

        output = session.post(url, data="cap_token=" + token, headers={'User-Agent': shared_state.values["user_agent"],
                                                                       'Content-Type': 'application/x-www-form-urlencoded'})
    url = output.url

    if "/404.html" in url:
        info("Filecrypt returned 404 - current IP is likely banned or the link is offline.")
        return False

    soup = BeautifulSoup(output.text, 'html.parser')

    solved = bool(soup.find_all("div", {"class": "container"}))
    if not solved:
        info("Token rejected by Filecrypt! Try another CAPTCHA to proceed...")
        return False
    else:
        season_number = ""
        episode_number = ""
        episode_in_title = re.findall(r'.*\.s(\d{1,3})e(\d{1,3})\..*', title, re.IGNORECASE)
        season_in_title = re.findall(r'.*\.s(\d{1,3})\..*', title, re.IGNORECASE)
        if episode_in_title:
            try:
                season_number = str(int(episode_in_title[0][0]))
                episode_number = str(int(episode_in_title[0][1]))
            except:
                pass
        elif season_in_title:
            try:
                season_number = str(int(season_in_title[0]))
            except:
                pass

        season = ""
        episode = ""
        tv_show_selector = soup.find("div", {"class": "dlpart"})
        if tv_show_selector:

            season = "season="
            episode = "episode="

            season_selection = soup.find("div", {"id": "selbox_season"})
            try:
                if season_selection:
                    season += str(season_number)
            except:
                pass

            episode_selection = soup.find("div", {"id": "selbox_episode"})
            try:
                if episode_selection:
                    episode += str(episode_number)
            except:
                pass

        if episode_number and not episode:
            info(f"Missing select for episode number {episode_number}! Expect undesired links in the output.")

        links = []

        mirrors = []
        mirrors_available = soup.select("a[href*=mirror]")
        if not mirror and mirrors_available:
            for mirror in mirrors_available:
                try:
                    mirror_query = mirror.get("href").split("?")[1]
                    base_url = url.split("?")[0] if "mirror" in url else url
                    mirrors.append(f"{base_url}?{mirror_query}")
                except IndexError:
                    continue
        else:
            mirrors = [url]

        for mirror in mirrors:
            if not len(mirrors) == 1:
                output = session.get(mirror, headers=headers)
                url = output.url
                soup = BeautifulSoup(output.text, 'html.parser')

            try:
                crypted_payload = soup.find("form", {"class": "cnlform"}).get('onsubmit')
                crypted_data = re.findall(r"'(.*?)'", crypted_payload)
                if not title:
                    title = crypted_data[3]
                crypted_data = [
                    crypted_data[0],
                    crypted_data[1],
                    crypted_data[2],
                    title
                ]
                if episode and season:
                    domain = urlparse(url).netloc
                    filtered_cnl_secret = soup.find("input", {"name": "hidden_cnl_id"}).attrs["value"]
                    filtered_cnl_link = f"https://{domain}/_CNL/{filtered_cnl_secret}.html?{season}&{episode}"
                    filtered_cnl_result = session.post(filtered_cnl_link,
                                                       headers=headers)
                    if filtered_cnl_result.status_code == 200:
                        filtered_cnl_data = json.loads(filtered_cnl_result.text)
                        if filtered_cnl_data["success"]:
                            crypted_data = [
                                crypted_data[0],
                                filtered_cnl_data["data"][0],
                                filtered_cnl_data["data"][1],
                                title
                            ]
                links.extend(CNL(crypted_data).decrypt())
            except:
                if "The owner of this folder has deactivated all hosts in this container in their settings." in soup.text:
                    info(f"Mirror deactivated by the owner: {mirror}")
                    continue

                info("Click'n'Load not found! Falling back to DLC...")
                try:
                    crypted_payload = soup.find("button", {"class": "dlcdownload"}).get("onclick")
                    crypted_data = re.findall(r"'(.*?)'", crypted_payload)
                    dlc_secret = crypted_data[0]
                    domain = urlparse(url).netloc
                    if episode and season:
                        dlc_link = f"https://{domain}/DLC/{dlc_secret}.dlc?{episode}&{season}"
                    else:
                        dlc_link = f"https://{domain}/DLC/{dlc_secret}.dlc"
                    dlc_file = session.get(dlc_link, headers=headers).content
                    links.extend(DLC(shared_state, dlc_file).decrypt())
                except:
                    info("DLC not found! Falling back to first available download Button...")

                    base_url = urlparse(url).netloc
                    phpsessid = session.cookies.get('PHPSESSID')
                    if not phpsessid:
                        info("PHPSESSID cookie not found! Cannot proceed with download links extraction.")
                        return False

                    results = []

                    for button in soup.find_all('button'):
                        # Find the correct data-* attribute (only one expected)
                        data_attrs = [v for k, v in button.attrs.items() if k.startswith('data-') and k != 'data-i18n']
                        if not data_attrs:
                            continue

                        link_id = data_attrs[0]
                        row = button.find_parent('tr')
                        mirror_tag = row.find('a', class_='external_link') if row else None
                        mirror_name = mirror_tag.get_text(strip=True) if mirror_tag else 'unknown'
                        full_url = f"http://{base_url}/Link/{link_id}.html"
                        results.append((full_url, mirror_name))

                    sorted_results = sorted(results, key=lambda x: 0 if 'rapidgator' in x[1].lower() else 1)

                    for result_url, mirror in sorted_results:
                        info("You must solve circlecaptcha separately!")
                        debug(f'Session "{phpsessid}" for {result_url} will not live long. Submit new CAPTCHA quickly!')
                        return {
                            "status": "replaced",
                            "replace_url": result_url,
                            "mirror": mirror,
                            "session": phpsessid
                        }

    if not links:
        info("No links found in Filecrypt response!")
        return False

    return {
        "status": "success",
        "links": links
    }
