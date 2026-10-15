# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

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

import uuid

from kuasarr.constants import (
    FILECRYPT_POW_DEADLINE_MS,
    FILECRYPT_POW_SOLVE_ATTEMPTS,
    FILECRYPT_POW_REQUEST_WAIT_SECONDS,
    FILECRYPT_POW_TAB_VERIFY_SECONDS,
    get_flaresolverr_pow_timeout,
)
from kuasarr.providers.network.origin_guard import same_origin_guard_for
from kuasarr.providers.network.cloudflare import (
    FlareSolverrResponse,
    is_cloudflare_challenge,
    ensure_session_cf_bypassed,
    flaresolverr_get,
    flaresolverr_request,
    flaresolverr_create_session,
    flaresolverr_destroy_session,
    flaresolverr_supports_next,
)
from kuasarr.providers.log import info, debug
from kuasarr.providers.captcha.circle_solver import solve_circle_captcha, fallback_random_coordinates


# ==============================================================================
# FILECRYPT PROOF-OF-WORK
# ==============================================================================

# FILECRYPT POW JAVASCRIPT INJECTED INTO THE FLARESOLVERR-NEXT BROWSER
#
# The proof-of-work is solved by Filecrypt's own JavaScript Web Worker running in a
# real browser. Kuasarr does not compute the hash itself - it only makes the
# automated browser behave like a trusted human session:
#
# - Filecrypt's anti-adblock overlay (#dontfoid) and any transparent/high z-index
#   cover are removed, because they would swallow the trusted pointer click.
#   A scripted .click() bypasses them, a real dispatched pointer cannot.
# - A focus event is dispatched every 80ms so the worker is not paused by the
#   window blur that happens in an automated browser.
# - The controller's own submitForm() call is hooked, so the final signed PoW
#   fields (pow_id/pow_nonce/pow_elapsed/pow_pauses/pow_data/pow_x) are captured
#   once the worker finished, and posted directly instead of navigating.
#
# __DEADLINE_MS__ in _POW_SOLVE_JS is a template placeholder replaced at call time.
#
# Ported from ghcr.io/rix1337/sponsors-helper (rix1337). Requires
# ghcr.io/rix1337/flaresolverr-next - standard FlareSolverr ignores executeJs,
# trustedClick and documentStartJs, so the PoW cannot be solved without it.

_POW_CLICKJACK_BLOCKER_JS = r"""(() => {
    'use strict';
    if (window.__filecryptHelperClickBlockerInstalled) return;
    window.__filecryptHelperClickBlockerInstalled = true;

    const ACTIVATION_EVENTS = new Set([
        'click',
        'dblclick',
        'auxclick',
        'mousedown',
        'mouseup',
        'pointerdown',
        'pointerup',
        'touchstart',
        'touchend',
    ]);
    const nativeWindowOpen = window.open.bind(window);
    const nativeAddEventListener = EventTarget.prototype.addEventListener;
    const wrappedActivationListeners = new WeakMap();

    const normalizeHost = host => String(host || '').replace(/^www[.]/i, '').toLowerCase();
    const isFileCryptInternalPopup = url => {
        try {
            const parsed = new URL(url || '', window.location.href);
            if (normalizeHost(parsed.hostname) !== normalizeHost(window.location.hostname)) return false;
            const path = parsed.pathname.toLowerCase();
            return path.startsWith('/link/') || path.startsWith('/dlc/');
        } catch (e) {
            return false;
        }
    };
    const isSelfPopup = url => {
        try {
            return new URL(url || '', window.location.href).href === window.location.href;
        } catch (e) {
            return false;
        }
    };
    const isGlobalActivationTarget = target => {
        return target === window ||
            target === document ||
            target === document.documentElement ||
            target === document.body;
    };
    const listenerSource = listener => {
        try {
            if (typeof listener === 'function') return Function.prototype.toString.call(listener);
            if (listener && typeof listener.handleEvent === 'function') {
                return Function.prototype.toString.call(listener.handleEvent);
            }
        } catch (e) {}
        return '';
    };
    const isClickjackerListener = listener => {
        const source = listenerSource(listener);
        if (!source) return false;
        const compact = source
            .replaceAll(' ', '')
            .replaceAll('\n', '')
            .replaceAll('\r', '')
            .replaceAll('\t', '');
        const lower = compact.toLowerCase();
        const opensPopup = lower.includes('.open(');
        const navigatesTop = lower.includes('top.location=') ||
            lower.includes('top.location.href=') ||
            lower.includes('window.location=') ||
            lower.includes('window.location.href=') ||
            lower.includes('location.location=') ||
            lower.includes('location.location.href=');
        const forcesClick = lower.includes('preventdefault()') &&
            (lower.includes('stoppropagation()') || lower.includes('stopimmediatepropagation()'));
        const linkRedirect = lower.includes('/link/');
        const selfPopup = lower.includes('.open(top.location.href') ||
            lower.includes('.open(location.href');
        return (opensPopup && navigatesTop && linkRedirect) || (selfPopup && forcesClick);
    };
    const getWrappedActivationListener = listener => {
        if (typeof listener !== 'function' && (!listener || typeof listener.handleEvent !== 'function')) {
            return listener;
        }
        if (!isClickjackerListener(listener)) {
            return listener;
        }
        let wrapped = wrappedActivationListeners.get(listener);
        if (wrapped) return wrapped;

        wrapped = function (event) {
            console.log('[FileCrypt-Helper] 🚫 Blocked page delegated activation handler:', event.type);
            return undefined;
        };
        wrappedActivationListeners.set(listener, wrapped);
        return wrapped;
    };

    EventTarget.prototype.addEventListener = function (type, listener, options) {
        if (ACTIVATION_EVENTS.has(String(type).toLowerCase()) && isGlobalActivationTarget(this)) {
            return nativeAddEventListener.call(this, type, getWrappedActivationListener(listener), options);
        }

        return nativeAddEventListener.call(this, type, listener, options);
    };

    window.open = function (...args) {
        const url = args[0];
        if (isFileCryptInternalPopup(url)) {
            return nativeWindowOpen(...args);
        }

        if (isSelfPopup(url)) {
            console.log('[FileCrypt-Helper] 🚫 Blocked page self-popup clickjacker:', url || '[current page]');
            return null;
        }

        console.log('[FileCrypt-Helper] 🚫 Blocked page window.open:', url || '[no url]');
        return null;
    };
})();"""

_POW_SOLVE_JS = r"""
var DEADLINE_MS = __DEADLINE_MS__;
var el = document.getElementById('pow-captcha');
if (!el) { window.__FRS_AWAIT = Promise.resolve(JSON.stringify({ status: 'no-pow' })); return JSON.stringify({ error: 'no-pow' }); }
var box = el.querySelector('.pow-captcha__box') || el;
var form = (box.closest && box.closest('form')) || document.getElementById('cform');
var done = false;
var _resolve;
window.__FRS_AWAIT = new Promise(function (r) { _resolve = r; });

function finish(payload) {
    if (done) return;
    done = true;
    _resolve(JSON.stringify(payload));
}

// Hook the controller's own submit call: by the time submitForm() invokes
// requestSubmit()/submit(), pow_id/pow_nonce/pow_elapsed/pow_pauses/pow_data/
// pow_x are all final (and pow_x now carries the trusted 2.1 signature).
function capture() {
    if (!form) { finish({ status: 'error', error: 'no form' }); return; }
    var body = new URLSearchParams();
    new FormData(form).forEach(function (v, k) { body.append(k, v); });
    fetch(form.getAttribute('action') || location.href, {
        method: 'POST', body: body,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        credentials: 'include'
    }).then(function (r) {
        return r.text().then(function (txt) { return { code: r.status, url: r.url, text: txt }; });
    }).then(function (o) {
        finish({
            status: 'ok', code: o.code, url: o.url,
            haspow: o.text.indexOf('pow-captcha') >= 0, html: o.text
        });
    }).catch(function (e) {
        finish({ status: 'error', error: String(e) });
    });
}

if (form) {
    // Suppress any native navigation that might slip in ahead of our hook.
    form.addEventListener('submit', function (e) {
        e.preventDefault(); e.stopImmediatePropagation();
        capture();
    }, true);
    form.requestSubmit = function () { capture(); };
    form.submit = function () { capture(); };
}

var start = Date.now();
var iv = setInterval(function () {
    // The controller pauses the worker on window blur; nudge focus so it does
    // not stay paused in an automated browser window.
    try { window.dispatchEvent(new Event('focus')); } catch (e) {}
    if (done) { clearInterval(iv); return; }
    var st = el.getAttribute('data-state');
    if (st === 'fail') { clearInterval(iv); finish({ status: 'timeout', state: st }); return; }
    if (Date.now() - start > DEADLINE_MS) { clearInterval(iv); finish({ status: 'timeout', state: st }); }
}, 80);

// Remove Filecrypt's anti-adblock overlay (#dontfoid) and any wide/transparent
// max-z-index cover: without ads loaded the overlay paints over the captcha and
// would swallow the trusted pointer click (a JS .click() bypasses it, a real
// pointer cannot).
try { var _ov = document.getElementById('dontfoid'); if (_ov) _ov.remove(); } catch (e) {}
try {
    document.querySelectorAll('div').forEach(function (div) {
        var s = getComputedStyle(div); var z = parseInt(s.zIndex, 10);
        if ((s.position === 'fixed' || s.position === 'absolute') && z > 999999 &&
            (s.backgroundColor === 'transparent' || s.opacity === '0' ||
             div.offsetWidth > window.innerWidth * 0.8)) {
            div.remove();
        }
    });
} catch (e) {}
// Report the click target (viewport CSS px, whole pixels) for the trusted gesture.
try { box.scrollIntoView({ block: 'center' }); } catch (e) {}
var rect = box.getBoundingClientRect();
return JSON.stringify({ trustedClick: { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) } });
"""


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


def detect_filecrypt_captcha_type(html):
    """
    Determine which gate a Filecrypt page currently puts in front of the download.

    Returns one of: 'none', 'pow', 'circle_captcha', 'cutcaptcha',
    'imagecaptcha', 'recaptcha', 'password' or 'unknown'.
    """
    if not html:
        return 'unknown'

    soup = BeautifulSoup(html, 'html.parser')

    # Order matters: the PoW gate is checked first because it is unambiguous, then
    # cnlform - the definitive "container reached" marker - so that stray recaptcha
    # markup on an already solved page cannot push it back into the captcha path.
    if soup.find(id='pow-captcha') or soup.find('div', {'class': 'pow-captcha'}):
        return 'pow'
    if soup.find('form', {'class': 'cnlform'}):
        return 'none'
    if soup.find('div', {'class': 'circle_captcha'}):
        return 'circle_captcha'
    if soup.find('input', {'id': 'p4assw0rt'}):
        return 'password'
    if soup.find('div', {'class': 'g-recaptcha'}):
        return 'recaptcha'
    if soup.find('input', {'name': 'captcha_response'}):
        return 'imagecaptcha'
    if soup.find('div', {'class': 'cutcaptcha'}) or 'cutcaptcha' in html.lower():
        return 'cutcaptcha'

    return 'unknown'


def _filecrypt_cookie_dict(session, url):
    """Export a requests session as the cookie list FlareSolverr expects."""
    domain = urlparse(url).netloc
    return [
        {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain or domain,
            "path": cookie.path or "/",
        }
        for cookie in session.cookies
    ]


def _parse_pow_result(execute_js_result):
    """
    Decode the payload the injected PoW script resolved with.

    With trustedClick, FlareSolverr-next awaits window.__FRS_AWAIT and returns
    the resolved value as executeJsResult. The arm script resolves it with
    JSON.stringify(), so the value arrives as a JSON string. In-page failures
    arrive as an "EXECUTE_JS_ERROR: ..." string instead, which is not a dict.
    """
    if not execute_js_result:
        return None

    payload = execute_js_result
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, json.JSONDecodeError):
            return None

    return payload if isinstance(payload, dict) else None


def _cookie_applies_to(cookie, host):
    """Whether a cookie's domain covers ``host``, with or without a leading dot."""
    domain = (cookie.domain or '').lstrip('.').lower()
    return bool(domain) and (domain == host or host.endswith(f'.{domain}'))


def get_filecrypt_phpsessid(session, url=None):
    """
    Read the container session out of a jar that may hold more than one PHPSESSID.

    ``requests`` raises ``CookieConflictError`` as soon as two cookies share a name
    and no domain or path narrows the lookup down, so a bare ``jar.get('PHPSESSID')``
    turns an ambiguity into an aborted link extraction. Pick the cookie that
    actually applies to the container origin instead, and never raise.
    """
    candidates = [cookie for cookie in session.cookies if cookie.name == 'PHPSESSID']
    if not candidates:
        return None

    if url:
        host = (urlparse(url).hostname or '').lower()
        matching = [cookie for cookie in candidates if _cookie_applies_to(cookie, host)]
        # Of several applicable cookies the last one wins: it is the most recently
        # set, which is the session the browser last handed us.
        if matching:
            return matching[-1].value

    return candidates[-1].value


def _apply_pow_result(session, response):
    """
    Carry the browser session's cookies back into the requests session.

    They replace rather than merge: this browser is the one that cleared the PoW,
    so its PHPSESSID is the session FileCrypt will honour from here on. Merging
    left the pre-PoW cookie in the jar next to it - requests reports the solved
    domain as ".filecrypt.cc" where it had stored "filecrypt.cc", so the two never
    replaced each other. Every later read then raised CookieConflictError and every
    later request carried an ambiguous session, which FileCrypt answered with an
    anonymous page: no Click'n'Load form and a DLC endpoint without a payload.
    Nothing is lost by replacing - the browser was seeded with the whole jar.
    """
    if not response.cookies:
        # Nothing came back, so there is no better session to switch to; clearing
        # would only leave the container with no session at all.
        debug("Filecrypt PoW returned no cookies, keeping the current session.")
        return

    session.cookies.clear()
    for cookie in response.cookies:
        try:
            session.cookies.set(
                cookie.get("name"),
                cookie.get("value"),
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )
        except Exception as e:
            debug(f"Could not apply FlareSolverr cookie: {e}")


def _submit_pow_challenge(shared_state, session, url, headers):
    """
    Solve a Filecrypt proof-of-work in a real flaresolverr-next browser.

    The PoW itself is computed by Filecrypt's own Web Worker - this only drives
    the browser so the worker produces a result Filecrypt accepts, and returns
    the solved response, or None when the PoW could not be cleared.
    """
    solve_js = _POW_SOLVE_JS.replace('__DEADLINE_MS__', str(FILECRYPT_POW_DEADLINE_MS))
    timeout = get_flaresolverr_pow_timeout()
    cookies = _filecrypt_cookie_dict(session, url)
    browser_headers = {'User-Agent': shared_state.values["user_agent"]}

    if not flaresolverr_supports_next(shared_state):
        info("Filecrypt proof-of-work requires ghcr.io/rix1337/flaresolverr-next. "
             "Standard FlareSolverr ignores executeJs/trustedClick, so it cannot be solved.")
        return None

    browser_session = f"kuasarr-pow-{uuid.uuid4().hex[:12]}"
    if not flaresolverr_create_session(shared_state, browser_session):
        info("Could not create flaresolverr-next session for the Filecrypt PoW solve!")
        return None

    try:
        for attempt in range(1, FILECRYPT_POW_SOLVE_ATTEMPTS + 1):
            info(f"Solving Filecrypt proof-of-work in browser "
                 f"(attempt {attempt}/{FILECRYPT_POW_SOLVE_ATTEMPTS})...")

            # One request does all three phases inside FlareSolverr: the arm script
            # installs the hooks and reports the click target, FlareSolverr dispatches
            # the trusted pointer gesture, then it awaits window.__FRS_AWAIT and hands
            # us the POST result. Splitting this into two requests would reload the
            # page in between and destroy the worker state the click is meant to start.
            try:
                response = flaresolverr_request(
                    shared_state,
                    url,
                    cmd="request.get",
                    timeout=timeout,
                    session_id=browser_session,
                    cookies=cookies,
                    wait=FILECRYPT_POW_REQUEST_WAIT_SECONDS,
                    tabs_till_verify=FILECRYPT_POW_TAB_VERIFY_SECONDS,
                    execute_js=solve_js,
                    trusted_click=True,
                    document_start_js=_POW_CLICKJACK_BLOCKER_JS,
                    headers=browser_headers,
                )
            except Exception as e:
                info(f"Filecrypt PoW executeJs error (attempt {attempt}): {e}")
                continue

            result = _parse_pow_result(response.execute_js_result)
            if not result:
                info(f"Filecrypt PoW returned unparseable result (attempt {attempt}): "
                     f"{str(response.execute_js_result)[:200]}")
                continue

            if result.get('error'):
                info(f"Filecrypt PoW in-page error (attempt {attempt}): {result['error']}")
                continue

            if result.get('status') == 'timeout':
                info(f"Filecrypt PoW timed out (attempt {attempt}), state={result.get('state')}")
                continue

            if result.get('haspow'):
                info(f"Filecrypt PoW submission rejected (attempt {attempt}), "
                     f"HTTP {result.get('code')}")
                continue

            html = result.get('html') or ""
            if not html:
                info(f"Filecrypt PoW returned no page (attempt {attempt}).")
                continue

            _apply_pow_result(session, response)

            solved = FlareSolverrResponse(
                url=result.get('url') or response.url,
                status_code=int(result.get('code') or 200),
                headers=response.headers,
                text=html,
            )
            info("Filecrypt proof-of-work solved.")
            return solved

        info(f"Filecrypt proof-of-work not solved after {FILECRYPT_POW_SOLVE_ATTEMPTS} attempts.")
        return None
    finally:
        flaresolverr_destroy_session(shared_state, browser_session)


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

    # The password and the captcha token are posted to this session below, and
    # requests follows 302 by default while carrying the body along. Pin the
    # session to the container's own origin so neither can be redirected away.
    session = same_origin_guard_for(session, output.url)

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

    captcha_type = detect_filecrypt_captcha_type(output.text)
    info(f"Filecrypt captcha type: {captcha_type}")

    if captcha_type == 'pow':
        # Proof-of-work: solved inside a real browser, because Filecrypt requires a
        # trusted pointer event that only FlareSolverr-next can dispatch.
        pow_output = _submit_pow_challenge(shared_state, session, url, headers)
        if pow_output is None:
            info("Filecrypt proof-of-work could not be solved. Check that FlareSolverr runs "
                 "ghcr.io/rix1337/flaresolverr-next.")
            return False

        url = pow_output.url
        output = pow_output
        soup = BeautifulSoup(output.text, 'html.parser')

        # The browser already carried us past the gate, so the cap_token is spent.
        captcha_type = detect_filecrypt_captcha_type(output.text)
        if captcha_type == 'pow':
            info("Filecrypt still shows the proof-of-work after solving.")
            return False

    elif captcha_type == 'none':
        info("No CAPTCHA present. Skipping token!")

    else:
        if captcha_type not in ('circle_captcha',):
            info(f"Unhandled Filecrypt captcha type '{captcha_type}' - trying the "
                 f"cap_token fallback.")

        circle_captcha = bool(soup.find_all("div", {"class": "circle_captcha"}))
        i = 0
        while circle_captcha and i < 3:
            # Try to solve using computer vision, fallback to random
            domain = urlparse(url).netloc
            solution = solve_circle_captcha(session, domain)
            if solution:
                click_x, click_y = solution
                info(f"Circle captcha solved at ({click_x}, {click_y})")
            else:
                click_x, click_y = fallback_random_coordinates()
                info(f"Using fallback coordinates ({click_x}, {click_y})")

            output = session.post(url, data=f"buttonx.x={click_x}&buttonx.y={click_y}",
                                  headers={'User-Agent': shared_state.values["user_agent"],
                                           'Content-Type': 'application/x-www-form-urlencoded'})
            if output.status_code == 403:
                info("Got 403 on circle_captcha POST. Retrying via FlareSolverr...")
                try:
                    output = flaresolverr_get(shared_state, url)
                except RuntimeError as e:
                    info(f"FlareSolverr fallback failed on circle_captcha: {e}")
                    return False
            url = output.url
            soup = BeautifulSoup(output.text, 'html.parser')
            circle_captcha = bool(soup.find_all("div", {"class": "circle_captcha"}))

        output = session.post(url, data="cap_token=" + token, headers={'User-Agent': shared_state.values["user_agent"],
                                                                       'Content-Type': 'application/x-www-form-urlencoded'})
        if output.status_code == 403:
            info("Got 403 on cap_token POST. Retrying via FlareSolverr...")
            try:
                output = flaresolverr_get(shared_state, url)
            except RuntimeError as e:
                info(f"FlareSolverr fallback failed on cap_token POST: {e}")
                return False
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
                if output.status_code == 403:
                    info(f"Got 403 on mirror GET. Retrying via FlareSolverr: {mirror}")
                    try:
                        output = flaresolverr_get(shared_state, mirror)
                    except RuntimeError as e:
                        info(f"FlareSolverr fallback failed on mirror GET: {e}")
                        continue
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
                    phpsessid = get_filecrypt_phpsessid(session, url)
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
