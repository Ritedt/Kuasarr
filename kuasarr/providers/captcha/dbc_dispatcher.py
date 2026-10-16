# -*- coding: utf-8 -*-
"""Background dispatcher for DeathByCaptcha captcha solving.

This dispatcher handles captcha solving via the DeathByCaptcha API
and integrates with the existing Filecrypt decryption logic.
"""

from __future__ import annotations

import base64
import json
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.parse import urlencode, urljoin, urlparse
from uuid import uuid4

import requests
from bs4 import BeautifulSoup

from kuasarr.providers import shared_state
from kuasarr.downloads.linkcrypters.filecrypt import (
    detect_filecrypt_captcha_type,
    _submit_pow_challenge,
)
from kuasarr.providers.captcha import push_jobs
from kuasarr.providers.captcha.math_captcha import solve_math_captcha
from kuasarr.providers.network.origin_guard import (
    origin_of as _origin_of,
    same_origin_guard_for as _same_origin_guard_for,
)
from kuasarr.providers.network.cloudflare import (
    flaresolverr_create_session,
    flaresolverr_destroy_session,
    flaresolverr_request,
    is_cloudflare_challenge,
    ensure_session_cf_bypassed,
)
from kuasarr.providers.captcha import create_captcha_client
from kuasarr.providers.captcha.base_client import (
    CaptchaResult,
    CaptchaStatus,
    CaptchaClientError,
    CaptchaInsufficientCredits,
    CaptchaServiceOverload,
)
from kuasarr.providers.captcha.dbc_client import (
    DeathByCaptchaClient,
    DBCError,
    DBCInsufficientCredits,
    DBCServiceOverload,
    create_dbc_client,
    DBC_AFFILIATE_LINK,
)
from kuasarr.providers.log import info, debug
from kuasarr.providers.notifications import send_discord_message
from kuasarr.providers.statistics import StatsHelper
from kuasarr.providers.hosters import filter_blocked_hosters
from kuasarr.downloads import fail
from kuasarr.downloads.linkcrypters.filecrypt import (
    CNL,
    DLC,
    get_filecrypt_phpsessid,
    narrow_cnl_payload,
)
from kuasarr.downloads.linkcrypters.hide import unhide_links
from kuasarr.constants import HTTP_DEFAULT_TIMEOUT_SECONDS, get_timeout

DEFAULT_DISPATCH_INTERVAL_SECONDS = 10
MAX_BACKOFF_MULTIPLIER = 8
PROCESSING_STATUS = "processing"  # job is actively being worked on this tick

# Keeplinks serves two different image captchas from the same container page.
# "Cool" is a distorted alphanumeric image, "Simple" is a plain 4 character word.
# Both are served from their own endpoint and each has its own form field name.
KEEPLINKS_CAPTCHA_ENDPOINTS = {
    "cool": "https://www.keeplinks.org/coolcaptcha/captcha.php",
    "simple": "https://www.keeplinks.org/simplecaptcha/captcha.php",
}
# Field the solved answer has to be posted back in. Keeplinks uses a different
# name per variant, which is why the answer cannot simply be written into
# whatever input happens to be called "captcha".
KEEPLINKS_ANSWER_FIELDS = {
    "cool": "captcha_cool",
    "simple": "norobot",
}
KEEPLINKS_ANSWER_LENGTH = 4

# ToLink renders its "text" captcha as ASCII art and then runs OCR over it.
# Digit/letter glyphs get confused for each other constantly, so the raw solver
# output is post-corrected before it goes back into the form.
TOLINK_NUMBER_SUBSTITUTIONS = (
    ("5", "S"), ("0", "O"), ("9", "O"), ("1", "I"),
    ("8", "B"), ("6", "G"), ("2", "Z"), ("7", "!"),
)
TOLINK_LETTER_SUBSTITUTIONS = (("T", "I"), ("l", "I"))
TOLINK_SUBMIT_LABEL = "Weiter zu den Links"

# he.to wraps its captcha form in a Content Protector overlay. FlareSolverr has
# to run inside the browser to read the form state and the captcha image, because
# the plain HTML does not carry a usable image source for every page variant.
HE_FORM_SNAPSHOT_JS = """
return (async () => {
  const form = document.querySelector(
    'form[id^="content-protector-access-form"]'
  );
  if (!form) return '';

  let imageBase64 = '';
  const image = form.querySelector('img[src]');
  if (image) {
    const response = await fetch(new URL(image.src, location.href), {
      credentials: 'include'
    });
    const bytes = new Uint8Array(await response.arrayBuffer());
    let binary = '';
    for (const byte of bytes) binary += String.fromCharCode(byte);
    imageBase64 = btoa(binary);
  }

  return JSON.stringify({
    action: form.action || location.href,
    fields: Array.from(new FormData(form).entries()),
    captchaId: form.querySelector('[name="captcha_id"]')?.value || '',
    imageBase64
  });
})()
"""

# Hoster URL shapes that identify a real download link. Shared by the per-site
# extractors so a new site does not need its own copy of the list.
DOWNLOAD_LINK_PATTERNS = (
    r'rapidgator\.net/file/',
    r'rg\.to/file/',
    r'ddownload\.com/[a-z0-9]+/',
    r'uploaded\.net/file/',
    r'uploaded\.to/file/',
    r'ul\.to/[a-z0-9]+',
    r'nitroflare\.com/view/',
    r'turbobit\.net/[a-z0-9]+/',
    r'1fichier\.com/\?[a-z0-9]+',
    r'katfile\.com/[a-z0-9]+/',
    r'mexashare\.com/[a-z0-9]+/',
    r'depositfiles\.com/files/',
    r'filefactory\.com/file/',
)


class PermanentLinkFailure(Exception):
    """Raised when a link permanently fails (e.g., offline) and should not be retried."""
    pass


def _he_post_unavailable(target: str, payload: List[Tuple[str, str]]) -> Optional[str]:
    """Stand-in for ``post_fn`` when no browser session could be obtained."""
    debug(f"he: no browser session available, cannot submit to {target}")
    return None


def _filecrypt_page_richness(soup: BeautifulSoup) -> int:
    """Rank a Filecrypt document by how much link-bearing content it carries.

    Used to decide whether a fetched mirror page is worth preferring over the
    page we already hold. The signals are exactly the ones the link extraction
    branches below rely on, so a document that scores zero here cannot produce
    links in any of them.

    The payload-carrying form dominates the score: it is the only element that
    yields links without a second request, and a document without it cannot be
    decrypted at all. The proof-of-work gate keeps the page chrome and the
    hoster-row markup around while dropping that form, so a page can look
    plausible in the DOM and still be worthless - counting the surrounding
    markup equally is what let a gate page replace a solved one.
    """
    cnl_form = soup.find("form", {"class": "cnlform"})
    if cnl_form and "CNLPOP(" in (cnl_form.get("onsubmit") or ""):
        # 1000 outweighs every other signal, so a page that can be decrypted
        # always wins over one that only looks like it.
        return 1000

    score = 0
    if cnl_form:
        score += 1
    if soup.find("button", {"class": "dlcdownload"}):
        score += 1
    score += len(soup.find_all("a", {"class": "external_link"}))
    return score


class DBCDispatcher:
    """Background thread for DeathByCaptcha captcha solving.
    
    Processes protected packages from the database, solves captchas via DBC,
    and forwards download links to JDownloader.
    """

    def __init__(
        self,
        state_module=shared_state,
        interval_seconds: Optional[int] = None,
    ) -> None:
        self.shared_state = state_module
        configured_interval = interval_seconds or int(
            self.shared_state.values.get("dbc_dispatch_interval", DEFAULT_DISPATCH_INTERVAL_SECONDS)
        )
        self.interval_seconds = max(1, configured_interval)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._failure_streak = 0
        self._backoff_until = 0.0
        self._client: Optional[DeathByCaptchaClient] = None

    def start(self) -> None:
        """Start the dispatcher background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="dbc-dispatcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the dispatcher background thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run_loop(self) -> None:
        """Main dispatcher loop."""
        while not self._stop_event.is_set():
            try:
                self._run_once()
            except (BrokenPipeError, EOFError, ConnectionResetError):
                # This happens if the multiprocessing Manager is shut down
                info("DBC Dispatcher: Shared state manager disconnected. Stopping dispatcher thread...")
                self._stop_event.set()
                break
            except Exception as exc:
                info(f"DBC Dispatcher error: {exc}")
            finally:
                if not self._stop_event.is_set():
                    self._stop_event.wait(self.interval_seconds)

    def _run_once(self) -> None:
        """Single dispatch iteration."""
        dbc_enabled = self.shared_state.values.get("dbc_enabled", False)
        if not dbc_enabled:
            return

        now = time.time()
        if self._backoff_until and now < self._backoff_until:
            debug(f"DBC Dispatcher paused for {self._backoff_until - now:.1f}s")
            return

        # Create or reuse client (supports both DBC and 2Captcha)
        if not self._client:
            self._client = create_captcha_client(self.shared_state)
        
        if not self._client:
            debug("Captcha Dispatcher skipped - no client available")
            return

        # Cleanup expired jobs
        push_jobs.cleanup_expired_jobs()
        current_jobs = push_jobs.list_jobs()
        
        # Reset stale "processing" jobs (stuck for more than 2 minutes)
        stale_threshold = now - 120  # 2 minutes
        for job_id, job in current_jobs.items():
            if job.get("status") == PROCESSING_STATUS:
                updated_at = job.get("updated_at", 0)
                if updated_at < stale_threshold:
                    info(f"Resetting stale job {job_id} (stuck for >{int(now - updated_at)}s)")
                    push_jobs.update_job_status(job_id, "pending")
        
        # Refresh job list after cleanup
        current_jobs = push_jobs.list_jobs()
        
        # Only in-flight jobs count against the concurrency limit.
        # "pending" jobs (waiting for the next retry tick) must not block themselves
        # from being picked up — they are NOT yet occupying a worker slot.
        active_jobs = sum(1 for job in current_jobs.values() if job.get("status") == PROCESSING_STATUS)
        max_concurrent = int(self.shared_state.values.get("dbc_max_concurrent", 1))

        if active_jobs >= max_concurrent:
            debug(f"DBC Dispatcher: Max concurrent jobs reached ({active_jobs}/{max_concurrent})")
            return

        # Packages whose job is actively being processed are off-limits for new dispatch.
        # Packages in "pending" state are eligible candidates — they need to be retried.
        assigned_packages = {
            (job.get("payload") or {}).get("package_id") or job_id
            for job_id, job in current_jobs.items()
            if job.get("status") == PROCESSING_STATUS
        }

        # Select candidates
        candidates = list(self._select_candidates(assigned_packages, limit=max_concurrent - active_jobs))
        
        if not candidates:
            return

        # Process candidates
        dispatched = 0
        for package_id, data, prioritized_links in candidates:
            try:
                success = self._process_package(package_id, data, prioritized_links)
                if success:
                    dispatched += 1
                    self._failure_streak = 0
                    self._backoff_until = 0.0
            except (DBCInsufficientCredits, CaptchaInsufficientCredits):
                info(f"⚠️ Captcha credits exhausted!")
                self._record_failure()
                break
            except (DBCServiceOverload, CaptchaServiceOverload):
                info("Captcha service overloaded, pausing...")
                self._record_failure()
                break
            except (DBCError, CaptchaClientError) as exc:
                info(f"Captcha error for package {package_id}: {exc}")
                self._record_failure()
                continue

        if dispatched:
            debug(f"DBC Dispatcher processed {dispatched} packages")

    def _select_candidates(
        self,
        assigned_packages: Iterable[str],
        limit: int,
    ) -> Iterable[Tuple[str, Dict[str, Any], list]]:
        """Select packages for processing."""
        protected_entries = self.shared_state.get_db("protected").retrieve_all_titles() or []
        assigned = set(filter(None, assigned_packages))
        picked = 0
        
        for package_id, raw_data in protected_entries:
            if package_id in assigned:
                continue
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                continue
            
            # Skip packages with active sessions (being processed)
            if data.get("session"):
                continue

            title = data.get("title", package_id)
            prioritized_links = self._filter_and_prioritize_links(data.get("links", []), package_id, title)
            if not prioritized_links:
                # Links were either empty or all blocked - package was already marked as failed
                continue
            
            yield package_id, data, prioritized_links
            picked += 1
            if picked >= limit:
                break

    def _filter_and_prioritize_links(self, links: Any, package_id: str, title: str) -> list:
        """Filter blocked hosters and prioritize links, preferring rapidgator."""
        if not isinstance(links, list):
            return []

        # First filter out blocked hosters
        filtered = filter_blocked_hosters(links)

        if not filtered and links:
            # All links were blocked - mark package as failed immediately
            info(f"Package '{title}' has only blocked hosters - skipping captcha solving")
            self._mark_as_failed(package_id, title, "All hosters blocked by user configuration")
            return []

        # Prioritize: rapidgator first, then others
        rapid = [ln for ln in filtered if isinstance(ln, list) and len(ln) > 1 and "rapidgator" in ln[1].lower()]
        others = [ln for ln in filtered if isinstance(ln, list) and len(ln) > 1 and "rapidgator" not in ln[1].lower()]
        return rapid + others

    def _process_package(
        self,
        package_id: str,
        data: Dict[str, Any],
        links: list,
    ) -> bool:
        """Process a single protected package."""
        title = data.get("title", package_id)
        password = data.get("password", "")
        max_attempts = int(data.get("max_attempts", 3))
        
        existing_job = push_jobs.get_job(package_id)
        attempt = int(existing_job.get("attempt", 0) + 1) if existing_job else 1
        
        if attempt > max_attempts:
            info(f"Package {title} reached max attempts ({max_attempts})")
            self._mark_as_failed(package_id, title, "Max attempts reached")
            return False
        
        push_jobs.upsert_job(
            package_id,
            {
                "status": "processing",
                "attempt": attempt,
                "payload": {"package_id": package_id, "title": title},
            },
        )
        
        info(f"DBC processing package: {title} (attempt {attempt}/{max_attempts}, {len(links)} links)")
        
        # Try each link
        link_index = 0
        for link_entry in links:
            link_index += 1
            if len(link_entry) < 2:
                continue
            
            link_url = link_entry[0] if isinstance(link_entry[0], str) else link_entry[1]
            mirror = link_entry[1] if len(link_entry) > 1 else ""
            
            try:
                result = self._solve_link(title, link_url, mirror, password)
                
                if result and result.get("status") == "success":
                    download_links = result.get("links", [])
                    if download_links:
                        # Check if all links would be filtered by hoster filter
                        filtered_links = filter_blocked_hosters(download_links)
                        if not filtered_links:
                            info(f"All links blocked by hoster filter for {title}")
                            self._mark_as_failed(package_id, title, "All hosters blocked by filter")
                            return False

                        downloaded = self.shared_state.download_package(
                            download_links, title, password, package_id
                        )

                        if downloaded:
                            StatsHelper(self.shared_state).increment_package_with_links(download_links)
                            StatsHelper(self.shared_state).increment_captcha_decryptions_automatic()
                            self.shared_state.get_db("protected").delete(package_id)
                            push_jobs.remove_job(package_id)
                            send_discord_message(self.shared_state, title=title, case="solved")
                            info(f"Download successfully started for {title}")
                            return True
                        else:
                            # Check if download failed because all links were filtered
                            filtered_check = filter_blocked_hosters(download_links)
                            if not filtered_check:
                                info(f"All links blocked by hoster filter for {title}")
                                self._mark_as_failed(package_id, title, "All hosters blocked by filter")
                                return False
                            info(f"Download failed for {title}")
                
                elif result and result.get("status") == "replaced":
                    # Circle-Captcha fallback - needs separate handling
                    replace_url = result.get("replace_url")
                    session_id = result.get("session")
                    mirror_name = result.get("mirror")
                    
                    if replace_url and session_id:
                        circle_result = self._solve_circle_captcha(
                            title, replace_url, session_id, password
                        )
                        if circle_result:
                            # Check if all links would be filtered by hoster filter
                            filtered_links = filter_blocked_hosters(circle_result)
                            if not filtered_links:
                                info(f"All links blocked by hoster filter for {title} (Circle-Captcha)")
                                self._mark_as_failed(package_id, title, "All hosters blocked by filter")
                                return False

                            downloaded = self.shared_state.download_package(
                                circle_result, title, password, package_id
                            )
                            if downloaded:
                                StatsHelper(self.shared_state).increment_package_with_links(circle_result)
                                StatsHelper(self.shared_state).increment_captcha_decryptions_automatic()
                                self.shared_state.get_db("protected").delete(package_id)
                                push_jobs.remove_job(package_id)
                                send_discord_message(self.shared_state, title=title, case="solved")
                                info(f"Download successfully started for {title} (Circle-Captcha)")
                                return True
                            else:
                                # Check if download failed because all links were filtered
                                filtered_check = filter_blocked_hosters(circle_result)
                                if not filtered_check:
                                    info(f"All links blocked by hoster filter for {title} (Circle-Captcha)")
                                    self._mark_as_failed(package_id, title, "All hosters blocked by filter")
                                    return False
                                info(f"Download failed for {title} (Circle-Captcha)")
                        
            except (DBCInsufficientCredits, CaptchaInsufficientCredits,
                    DBCServiceOverload, CaptchaServiceOverload):
                # Muss hier ebenfalls durchgereicht werden: die Overload-
                # Klassen sind Geschwister der Credits-Klassen, keine
                # Unterklassen. Ohne diesen Zweig faellt der Fehler in den
                # `except (DBCError, CaptchaClientError)` darunter, `_run_once`
                # sieht ihn nie und der Backoff greift nicht - obwohl der
                # Dienst genau dann gerade nicht verfuegbar ist.
                raise
            except PermanentLinkFailure as exc:
                info(f"Permanent failure for {link_url}: {exc}")
                self._mark_as_failed(package_id, title, str(exc))
                return False
            except (DBCError, CaptchaClientError) as exc:
                info(f"Captcha error for link {link_url}: {exc}")
                continue
            except Exception as exc:
                info(f"Error processing {link_url}: {exc}")
                continue
        
        # All links failed
        push_jobs.update_job_status(package_id, "pending", attempt=attempt)
        
        if attempt >= max_attempts:
            self._mark_as_failed(package_id, title, "All links failed")
            return False
        
        info(f"Package {title} will be retried (attempt {attempt}/{max_attempts})")
        return False

    def _solve_link(
        self,
        title: str,
        link_url: str,
        mirror: str,
        password: str,
    ) -> Optional[Dict[str, Any]]:
        """Solve captcha for a link using the appropriate method."""
        info(f"Processing link: {link_url[:80]}... (Mirror: {mirror})")
        
        if "hide.cx" in link_url.lower():
            return self._solve_hide_cx(title, link_url, password, mirror)
        elif "filecrypt" in link_url.lower() or "filecrypt" in mirror.lower():
            return self._solve_filecrypt_with_dbc(title, link_url, password, mirror)
        elif "keeplinks" in link_url.lower() or "keeplinks" in mirror.lower():
            # Handles both the 'cool' and the 'simple' Keeplinks captcha.
            return self._solve_keeplinks_with_dbc(title, link_url, password, mirror)
        elif "tolink" in link_url.lower() or "tolink" in mirror.lower():
            # Handles the image captcha, the ASCII text captcha and reCAPTCHA.
            return self._solve_tolink_with_dbc(title, link_url, password, mirror)
        elif self._is_he_container(link_url):
            return self._solve_he_with_dbc(title, link_url, password, mirror)
        else:
            # For other link types, try generic approach
            return self._solve_generic_link(title, link_url, password)

    @staticmethod
    def _is_he_container(url: str) -> bool:
        """Whether *url* points at an he.to / hit-parade container page.

        Checked against the hostname on purpose: a plain substring test for
        "he.to" also matches unrelated hosts such as "cache.tool".
        """
        host = urlparse(url).hostname or ''
        return host == 'he.to' or host.endswith('.he.to') or host == 'www.he.to'

    def _solve_filecrypt_with_dbc(
        self,
        title: str,
        url: str,
        password: str,
        mirror: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Solve Filecrypt using DBC for captcha solving.
        
        This integrates with the existing Filecrypt logic but uses DBC
        for CutCaptcha, reCAPTCHA, and Circle-Captcha.
        """
        info(f"Attempting to decrypt Filecrypt link: {url}")
        debug(f"DBC Dispatcher: Starting Filecrypt decryption for {title}")
        session = requests.Session()
        headers = {'User-Agent': self.shared_state.values["user_agent"]}

        # Ensure we are not blocked by Cloudflare
        session, headers, output = ensure_session_cf_bypassed(info, self.shared_state, session, url, headers)
        if not session or not output:
            info(f"Failed to bypass Cloudflare for {url}")
            return None
        
        info(f"Filecrypt page loaded successfully (status={output.status_code}, {len(output.text)} bytes)")

        # Everything below posts the container password and the captcha token.
        # requests follows 302 by default and carries the body along, so a
        # container that redirects the POST would hand both to a host of its
        # choosing. Pin the session to the container's own origin first.
        session = self._same_origin_guard_for(session, output.url)

        soup = BeautifulSoup(output.text, 'html.parser')

        # Handle password field
        password_field = None
        try:
            input_elem = soup.find('input', attrs={'type': 'password'})
            if not input_elem:
                input_elem = soup.find('input', placeholder=lambda v: v and 'password' in v.lower())
            if not input_elem:
                input_elem = soup.find('input',
                                       attrs={'name': lambda v: v and ('pass' in v.lower() or 'password' in v.lower())})
            if input_elem and input_elem.has_attr('name'):
                password_field = input_elem['name']
                info(f"Password field name identified: {password_field}")
        except Exception as e:
            info(f"Password-field detection error: {e}")

        # Submit password if needed
        if password and password_field:
            info(f"Using Password: {password}")
            post_headers = {'User-Agent': self.shared_state.values["user_agent"],
                            'Content-Type': 'application/x-www-form-urlencoded'}
            data = {password_field: password}
            try:
                output = session.post(output.url, data=data, headers=post_headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
            except requests.RequestException as e:
                info(f"POSTing password failed: {e}")
                return None

            if output.status_code == 403 or is_cloudflare_challenge(output.text):
                info("Encountered Cloudflare after password POST. Re-running FlareSolverr...")
                session, headers, output = ensure_session_cf_bypassed(info, self.shared_state, session, output.url, headers)
                if not session or not output:
                    return None

        url = output.url
        soup = BeautifulSoup(output.text, 'html.parser')
        
        if bool(soup.find_all("input", {"id": "p4assw0rt"})):
            info(f"Password was wrong or missing. Could not get links for {title}")
            return None

        # Which gate is Filecrypt putting in front of this container? It serves a
        # proof-of-work instead of the image captchas, and no captcha service can
        # ever produce a token for that - only a real browser can clear it. Asking
        # a service anyway guarantees a failure that then reads as a rejected token.
        captcha_type = detect_filecrypt_captcha_type(output.text)
        info(f"Filecrypt captcha type: {captcha_type}")

        if captcha_type == 'pow':
            pow_output = _submit_pow_challenge(self.shared_state, session, url, headers)
            if pow_output is None:
                info("Filecrypt proof-of-work could not be solved. Check that FlareSolverr "
                     "runs ghcr.io/rix1337/flaresolverr-next.")
                return None

            url = pow_output.url
            output = pow_output
            soup = BeautifulSoup(output.text, 'html.parser')

            # The browser already carried us past the gate, so nothing is left to
            # solve. Seeing the PoW again means the submission did not go through.
            if detect_filecrypt_captcha_type(output.text) == 'pow':
                info("Filecrypt still shows the proof-of-work after solving.")
                return None

        # Check if captcha is needed
        no_captcha_present = bool(soup.find("form", {"class": "cnlform"}))
        info(f"Captcha check: CNL form present={no_captcha_present}")

        if not no_captcha_present:
            # Circle-Captcha: filecrypt now uses an image captcha where the user has
            # to click inside an open circle. We send the image to DBC
            # (solve_coordinates_captcha), which returns the (x, y) of the open circle
            # — then submit those exact coordinates instead of random ones.
            #
            # Detection is strict: the page must have BOTH a <div class="circle_captcha">
            # AND an <input type="image" src="/captcha/circle.php name="button">. The
            # CSS class alone is not enough because filecrypt's main captcha UI also
            # contains the substring "circle_captcha" in inline styles (false positive).
            circle_captcha_img = soup.find(
                "input",
                {"type": "image", "src": re.compile(r"/captcha/circle\.php")},
            )
            if circle_captcha_img and self._client:
                info("Circle-Captcha detected, solving via DBC image solver...")
                # The captcha image is served at /captcha/circle.php relative to the
                # page origin. Fetch it with the same session so the PHPSESSID cookie
                # binds the answer to this page load.
                origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                img_src = circle_captcha_img.get("src", "")
                if img_src.startswith("/"):
                    img_url = origin + img_src
                elif img_src.startswith("http"):
                    img_url = img_src
                else:
                    img_url = f"{origin}/captcha/circle.php"
                img_resp = session.get(
                    img_url,
                    headers={
                        **headers,
                        "Referer": url,
                        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
                    },
                    timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS),
                )
                img_resp.raise_for_status()
                info(f"Circle-Captcha image fetched ({len(img_resp.content)} bytes)")



            # Now solve the main captcha (CutCaptcha or reCAPTCHA) via DBC
            info(f"Attempting to solve Filecrypt captcha '{captcha_type}' via captcha service...")
            token = self._get_captcha_token(url, soup, captcha_type)
            info(f"Captcha token received: {bool(token)}")

            if token:
                # filecrypt uses different field names for different captcha
                # types. Detect from the page which field name to send the
                # captcha response back as.
                recaptcha_field = soup.find("textarea", {"name": "g-recaptcha-response"})
                field_name = recaptcha_field.get("name") if recaptcha_field else "cap_token"
                info(f"Filecrypt: posting captcha response as field '{field_name}'")
                output = session.post(
                    url,
                    data={field_name: token},
                    headers={
                        **self._build_post_headers(url),
                        "Origin": urlparse(url).scheme + "://" + urlparse(url).netloc,
                        "Referer": url,
                    },
                    # Without a timeout this POST blocks forever. The dispatcher
                    # runs single-threaded (max_concurrent = 1), so one hanging
                    # POST freezes the whole queue - hence the explicit bound.
                    timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS),
                )
                url = output.url
            else:
                info("No captcha token received, trying to continue without token...")
        else:
            info("No CAPTCHA present. Skipping token!")

        if "/404.html" in url:
            info("Filecrypt returned 404 - current IP is likely banned or the link is offline.")
            return None

        soup = BeautifulSoup(output.text, 'html.parser')

        solved = bool(soup.find_all("div", {"class": "container"}))
        info(f"Filecrypt solved check: container div present={solved}")
        if not solved:
            info("Token rejected by Filecrypt! Try another CAPTCHA to proceed...")
            return None

        # Extract links using existing logic
        return self._extract_filecrypt_links(session, soup, url, title, headers)

    def _build_post_headers(self, url):
        """Build default POST headers for captcha submission."""
        return {
            'User-Agent': self.shared_state.values["user_agent"],
            'Content-Type': 'application/x-www-form-urlencoded',
        }

    def _get_captcha_token(self, url: str, soup: BeautifulSoup,
                           captcha_type: str = 'unknown') -> Optional[str]:
        """Get captcha token by solving via DBC."""
        
        debug(f"DBC: Checking for captcha types on {url}")

        # filecrypt.cc now uses a Proof-of-Work captcha (pow-captcha) that requires
        # browser-side JS execution + fingerprinting (s.js/m.js signals). It cannot
        # be solved by DBC/2Captcha (no image/reCAPTCHA). Detect it explicitly so the
        # failure reason is clear instead of the misleading "no captcha found" path.
        if soup.find("div", {"class": "pow-captcha"}):
            info("Filecrypt PoW-captcha detected — requires browser-based solving, not solvable via DBC/2Captcha")
            return None

        # Check for CutCaptcha
        cutcaptcha_div = soup.find("div", {"class": "cutcaptcha"})
        if cutcaptcha_div or "SAs61IAI" in str(soup):
            info("CutCaptcha detected, solving via DBC...")
            debug(f"DBC: CutCaptcha div found: {bool(cutcaptcha_div)}, SAs61IAI in page: {'SAs61IAI' in str(soup)}")
            api_key = "SAs61IAI"  # Default Filecrypt key
            misery_key = self._extract_misery_key(api_key, str(soup))
            
            try:
                result = self._client.solve_cutcaptcha(
                    api_key=api_key,
                    page_url=url,
                    misery_key=misery_key,
                )
                if result.is_solved:
                    info(f"CutCaptcha solved successfully")
                    return result.text
                else:
                    info(f"CutCaptcha solving failed: {result.status}")
            except (DBCError, CaptchaClientError) as e:
                info(f"CutCaptcha error: {e}")
        
        # Check for reCAPTCHA
        recaptcha_div = soup.find("div", {"class": "g-recaptcha"})
        debug(f"DBC: reCAPTCHA div found: {bool(recaptcha_div)}")
        if recaptcha_div:
            token = self._solve_recaptcha_token(url, soup)
            if token:
                return token

        # Check for image captcha
        captcha_img = soup.find("img", {"id": "captcha_img"})
        debug(f"DBC: Image captcha found: {bool(captcha_img)}")
        if captcha_img:
            img_src = captcha_img.get("src", "")
            if img_src:
                info("Image captcha detected, solving via DBC...")
                debug(f"DBC: Image captcha src: {img_src[:80]}...")
                try:
                    img_src = self._same_origin_asset_url(url, img_src)
                    if not img_src:
                        info("Image captcha src is not on the container origin - refusing to fetch")
                        return None
                    img_response = requests.get(img_src, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                    result = self._client.solve_captcha(img_response.content)
                    if result.is_solved:
                        return result.text
                except Exception as e:
                    info(f"Image captcha error: {e}")

        # Say so out loud. Returning None here used to look identical to a captcha
        # service that was asked and had no answer, which sent the diagnosis down
        # the wrong path entirely.
        info(f"No captcha type recognised on this Filecrypt page (type='{captcha_type}') "
             f"- no captcha service was called")
        return None

    def _solve_recaptcha_token(self, url: str, soup: BeautifulSoup) -> Optional[str]:
        """Solve a reCAPTCHA v2 challenge on *url* and return its token.

        Shared by every site that layers reCAPTCHA on top of its own captcha, so
        the site key extraction and the error handling only exist once.
        """
        recaptcha_div = soup.find("div", {"class": "g-recaptcha"})
        if not recaptcha_div:
            return None

        site_key = recaptcha_div.get("data-sitekey", "")
        if not site_key or not self._client:
            return None

        info("reCAPTCHA detected, solving via captcha service...")
        debug(f"DBC: reCAPTCHA sitekey: {site_key[:30]}...")
        try:
            result = self._client.solve_recaptcha_v2(
                site_key=site_key,
                page_url=url,
            )
            if result.is_solved:
                return result.text
            info(f"reCAPTCHA solving failed: {result.status}")
        except (DBCError, CaptchaClientError) as e:
            info(f"reCAPTCHA error: {e}")

        return None

    def _extract_filecrypt_links(
        self,
        session: requests.Session,
        soup: BeautifulSoup,
        url: str,
        title: str,
        headers: dict,
    ) -> Optional[Dict[str, Any]]:
        """Extract download links from solved Filecrypt page."""
        debug(f"DBC: Extracting links from Filecrypt page: {url}")
        
        # Parse season/episode from title
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

        links = []

        # Collect mirrors
        mirrors = []
        mirrors_available = soup.select("a[href*=mirror]")
        if mirrors_available:
            for mirror in mirrors_available:
                try:
                    mirror_query = mirror.get("href").split("?")[1]
                    base_url = url.split("?")[0] if "mirror" in url else url
                    mirrors.append(f"{base_url}?{mirror_query}")
                except IndexError:
                    continue
        else:
            mirrors = [url]

        # The page we already hold carries the payload; the mirrors are fetched
        # only to see whether one of them carries more. None of them does in
        # practice - a mirror GET is answered by the proof-of-work gate again,
        # without the payload form - and taking such a page made every
        # container with mirror links report "Click'n'Load not found!" and fall
        # through to DLC and then into the Circle-Captcha fallback.
        candidates = []
        if len(mirrors) > 1:
            current_richness = _filecrypt_page_richness(soup)
            for mirror_url in mirrors:
                mirror_output = session.get(mirror_url, headers=headers,
                                           timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                mirror_soup = BeautifulSoup(mirror_output.text, 'html.parser')
                if _filecrypt_page_richness(mirror_soup) > current_richness:
                    debug(f"DBC: Mirror {mirror_url} liefert eine bessere Seite.")
                    current_richness = _filecrypt_page_richness(mirror_soup)
                    candidates.append((mirror_output, mirror_output.url, mirror_soup))
                else:
                    debug(f"DBC: Mirror {mirror_url} liefert keine nutzbare Seite "
                          f"(kein CNL-Payload), gelöste Seite behalten.")

        # The solved page goes last, so it is the one parsed when no mirror is
        # better. Without it the loop body would run only for useless mirrors
        # and no link would ever be decrypted.
        candidates.append((None, url, soup))

        for page_output, page_url, page_soup in candidates:

            try:
                # Try CNL (Click'n'Load)
                crypted_payload = page_soup.find("form", {"class": "cnlform"}).get('onsubmit')
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
                    # Optional filter only - see narrow_cnl_payload. A failed
                    # filter must leave the payload that is already in the page
                    # alone instead of aborting the CNL branch.
                    cnl_secret_el = page_soup.find("input", {"name": "hidden_cnl_id"})
                    crypted_data = narrow_cnl_payload(
                        session, page_url, headers,
                        cnl_secret_el.get("value") if cnl_secret_el else None,
                        season, episode, crypted_data, title,
                    )
                links.extend(CNL(crypted_data).decrypt())
                break
            except:
                if "The owner of this folder has deactivated all hosts in this container in their settings." in page_soup.text:
                    info(f"Mirror deactivated by the owner: {mirror_url}")
                    continue

                info("Click'n'Load not found! Falling back to DLC...")
                try:
                    # Try DLC
                    crypted_payload = page_soup.find("button", {"class": "dlcdownload"}).get("onclick")
                    crypted_data = re.findall(r"'(.*?)'", crypted_payload)
                    dlc_secret = crypted_data[0]
                    domain = urlparse(page_url).netloc
                    if episode and season:
                        dlc_link = f"https://{domain}/DLC/{dlc_secret}.dlc?{episode}&{season}"
                    else:
                        dlc_link = f"https://{domain}/DLC/{dlc_secret}.dlc"
                    # Timeout wie bei allen anderen Aufrufen in diesem Pfad:
                    # der Dispatcher laeuft single-threaded, ein haengender GET
                    # wuerde die komplette Queue einfrieren.
                    dlc_file = session.get(dlc_link, headers=headers,
                                           timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS)).content
                    links.extend(DLC(self.shared_state, dlc_file).decrypt())
                    break
                except:
                    info("DLC not found! Falling back to Circle-Captcha buttons...")
                    
                    # Return replacement info for Circle-Captcha handling
                    parsed_url = urlparse(page_url)
                    base_url = parsed_url.netloc
                    # Keep the scheme the container itself was served with. Building
                    # an "http://" URL out of the bare netloc pinned the
                    # Circle-Captcha step to an origin the container never answers
                    # on: FileCrypt redirects it to the same host over https, the
                    # origin guard reads that as leaving the pinned origin, and
                    # every attempt gets refused.
                    base_scheme = parsed_url.scheme or "https"
                    phpsessid = get_filecrypt_phpsessid(session, page_url)
                    if not phpsessid:
                        info("PHPSESSID cookie not found!")
                        return None

                    results = []
                    for button in page_soup.find_all('button'):
                        data_attrs = [v for k, v in button.attrs.items() if k.startswith('data-') and k != 'data-i18n']
                        if not data_attrs:
                            continue
                        link_id = data_attrs[0]
                        row = button.find_parent('tr')
                        mirror_tag = row.find('a', class_='external_link') if row else None
                        mirror_name = mirror_tag.get_text(strip=True) if mirror_tag else 'unknown'
                        full_url = f"{base_scheme}://{base_url}/Link/{link_id}.html"
                        results.append((full_url, mirror_name))

                    sorted_results = sorted(results, key=lambda x: 0 if 'rapidgator' in x[1].lower() else 1)

                    for result_url, mirror_name in sorted_results:
                        info(f"Circle-Captcha required for {result_url}")
                        return {
                            "status": "replaced",
                            "replace_url": result_url,
                            "mirror": mirror_name,
                            "session": phpsessid
                        }

        if not links:
            info("No links found in Filecrypt response!")
            return None

        debug(f"DBC: Extracted {len(links)} download links")
        return {
            "status": "success",
            "links": links
        }

    def _solve_circle_captcha(
        self,
        title: str,
        url: str,
        phpsessid: str,
        password: str,
    ) -> Optional[list]:
        """Solve Circle-Captcha via DBC and extract final download link."""
        info(f"Solving Circle-Captcha for {url} via DBC...")
        debug(f"DBC: Circle-Captcha session: PHPSESSID={phpsessid[:10]}...")
        
        session = self._same_origin_guard_for(requests.Session(), url)
        session.cookies.set('PHPSESSID', phpsessid)
        headers = {'User-Agent': self.shared_state.values["user_agent"]}
        
        for attempt in range(3):
            try:
                # Fetch the circle captcha page
                response = session.get(url, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find circle captcha image
                circle_div = soup.find("div", {"class": "circle_captcha"})
                if not circle_div:
                    # No circle captcha, check if we have a direct link
                    match = re.search(r"top\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", response.text)
                    if match:
                        redirect_url = self._same_origin_asset_url(url, match.group(1))
                        if redirect_url:
                            redirect_resp = session.get(redirect_url, allow_redirects=True, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                            if redirect_resp.ok and "expired" not in redirect_resp.text.lower():
                                return [redirect_resp.url]
                    continue
                
                # Find the captcha image
                captcha_img = circle_div.find("img")
                if not captcha_img:
                    # Try to find any image in the form
                    captcha_img = soup.find("img", src=lambda s: s and "captcha" in s.lower())
                
                if captcha_img:
                    img_src = captcha_img.get("src", "")
                    if img_src:
                        img_src = self._same_origin_asset_url(url, img_src)
                        if not img_src:
                            info("Coordinates captcha src is not on the container origin - refusing to fetch")
                            return None

                        # Download captcha image
                        img_response = session.get(img_src, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                        
                        # Solve via DBC (coordinates captcha)
                        debug(f"DBC: Solving coordinates captcha ({len(img_response.content)} bytes)")
                        coords = self._client.solve_coordinates_captcha(img_response.content)
                        
                        if coords:
                            x, y = coords
                            debug(f"DBC: Circle-Captcha coordinates: x={x}, y={y}")
                            # Submit solution
                            data = {"buttonx.x": str(x), "buttonx.y": str(y)}
                            submit_response = session.post(url, data=data, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                            
                            if submit_response.url.endswith("404.html"):
                                info("IP blocked by Filecrypt")
                                return None
                            
                            # Check for redirect to final link
                            match = re.search(r"top\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", submit_response.text)
                            if match:
                                redirect_url = self._same_origin_asset_url(url, match.group(1))
                                if redirect_url:
                                    redirect_resp = session.get(redirect_url, allow_redirects=True, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                                    if redirect_resp.ok and "expired" not in redirect_resp.text.lower():
                                        info(f"Circle-Captcha successfully solved: {redirect_resp.url}")
                                        return [redirect_resp.url]
                
                time.sleep(2)
                
            except (DBCInsufficientCredits, CaptchaInsufficientCredits,
                    DBCServiceOverload, CaptchaServiceOverload):
                # Beide Klassen erben von DBCError/CaptchaClientError und damit von
                # RuntimeError. Ein Broad-Except schluckte sie hier - _run_once
                # erkennt sie nicht mehr und der Backoff bleibt aus. Erst _run_once
                # entscheidet, was bei leeren Credits oder Überlastung zu tun ist.
                raise
            except (DBCError, CaptchaClientError, requests.RequestException) as e:
                info(f"Circle-Captcha attempt {attempt + 1} failed: {e}")
                time.sleep(2)
        
        info("Circle-Captcha could not be solved")
        return None

    def _solve_keeplinks_with_dbc(
        self,
        title: str,
        url: str,
        password: str,
        mirror: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Solve Keeplinks.org using DBC for image captcha solving.

        Keeplinks serves one of two image captchas from the same container page
        (coolcaptcha or simplecaptcha); both are solved by DBC and handled by
        :meth:`_solve_keeplinks_captcha`.

        Flow:
        1. GET the page
        2. POST to proceed past "Click To Proceed"
        3. Extract links if they are already visible
        4. Otherwise solve and submit the CAPTCHA
        """
        info(f"Attempting to decrypt Keeplinks: {url}")

        session = self._same_origin_guard_for(requests.Session(), url)
        headers = {
            'User-Agent': self.shared_state.values["user_agent"],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': url,
        }
        
        try:
            # Step 1: Initial GET request
            debug(f"Keeplinks: Initial GET request")
            response = session.get(url, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
            
            if response.status_code != 200:
                info(f"Keeplinks: Initial request failed with status {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Step 2: Check for "Click To Proceed" page and submit
            proceed_form = soup.find('form', {'name': 'frmprotect'})
            if proceed_form:
                # Check for showpageval or a submit button with "proceed", "klick", "continue" text
                is_proceed_page = False
                showpageval_input = proceed_form.find('input', {'name': 'showpageval'})
                if showpageval_input and showpageval_input.get('value') == '1':
                    is_proceed_page = True
                
                if not is_proceed_page:
                    # Look for submit input or button
                    submit_btn = proceed_form.find(['input', 'button'], {'type': 'submit'}) or proceed_form.find('button')
                    if submit_btn:
                        btn_text = (submit_btn.get('value') or submit_btn.text or "").lower()
                        if any(x in btn_text for x in ['proceed', 'klick', 'continue', 'proceed', 'fortfahren']):
                            is_proceed_page = True
                
                if is_proceed_page:
                    debug("Keeplinks: Submitting 'Click To Proceed' form")
                    # Keeplinks will hier ausschliesslich showpageval=1. Das
                    # Weiterreichen des kompletten Formulars schickt ein leeres
                    # captcha_cool zusammen mit hiddencaptcha=1 und captchatype
                    # mit, was den Captcha-Zustand der Session verfaelscht.
                    response = session.post(url, data={'showpageval': '1'}, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                    
                    if response.status_code != 200:
                        info(f"Keeplinks: Proceed POST failed with status {response.status_code}")
                        return None
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
            
            # Step 3: Check for download links FIRST (they are visible on the CAPTCHA page!)
            links = self._extract_keeplinks_download_links(soup)
            if links:
                info(f"Keeplinks: Found {len(links)} links (no CAPTCHA solving needed)")
                return {"status": "success", "links": links}
            
            # Step 4: If no links found, solve the CAPTCHA (cool or simple)
            return self._solve_keeplinks_captcha(session, soup, url, headers, password, mirror)

        except requests.RequestException as e:
            info(f"Keeplinks: Request error - {e}")
            return None
        except Exception as e:
            info(f"Keeplinks: Unexpected error - {e}")
            return None

    @staticmethod
    def _detect_keeplinks_captcha(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
        """Identify which Keeplinks captcha is on the page.

        Two signals are consulted: the hidden ``captchatype`` input and the
        endpoint the captcha image is loaded from. Cool wins when both appear,
        because that is the variant Keeplinks advertises on the container page.

        Returns:
            ``(variant, captcha_image_url)``, or ``(None, None)`` when the page
            carries no captcha at all.
        """
        hidden_type_input = soup.find('input', {'name': 'captchatype'})
        captchatype_val = ''
        if hidden_type_input:
            try:
                captchatype_val = (hidden_type_input.get('value') or '').strip()
            except Exception as exc:
                debug(f"Keeplinks: could not read captchatype: {exc}")

        simple_img = soup.find('img', src=re.compile(r'simplecaptcha/captcha\.php'))
        cool_img = soup.find('img', src=re.compile(r'coolcaptcha/captcha\.php'))

        if cool_img or captchatype_val == 'Cool':
            return 'cool', KEEPLINKS_CAPTCHA_ENDPOINTS['cool']
        if simple_img or captchatype_val == 'Simple':
            return 'simple', KEEPLINKS_CAPTCHA_ENDPOINTS['simple']

        return None, None

    @staticmethod
    def _normalize_keeplinks_answer(variant: str, solved_text: str) -> str:
        """Clean the raw solver output into the shape Keeplinks expects.

        Cool is a distorted alphanumeric image, so every non-letter is noise.
        Simple is a 4 character word and the solver tends to repeat glyphs
        ("aabb" for "ab"), which is collapsed here.
        """
        if variant == 'cool':
            return re.sub(r'[^A-Za-z]', '', solved_text or '')

        cleaned = (solved_text or '').strip()
        if not cleaned:
            return ''

        deduped = cleaned[0]
        for char in cleaned[1:]:
            if char != deduped[-1]:
                deduped += char

        if len(deduped) >= KEEPLINKS_ANSWER_LENGTH:
            return deduped[:KEEPLINKS_ANSWER_LENGTH]
        return deduped

    @staticmethod
    def _same_origin_asset_url(base_url: str, asset_url: str) -> Optional[str]:
        """Resolve a captcha/asset URL and keep it on the container's origin.

        The container HTML is attacker-influenceable, so an absolute ``src``
        such as ``http://169.254.169.254/x.png`` would otherwise be fetched
        verbatim. Relative paths are resolved against the container page.
        Returns None when the resolved URL leaves the container's origin.
        """
        if not asset_url:
            return None
        stripped = asset_url.strip()
        if not stripped:
            return None
        # An empty/blank src resolves to base_url itself (urljoin(base, "") == base),
        # which would re-fetch the container page instead of a captcha image.
        # A resolved URL equal to base_url is otherwise legitimate - a form
        # action that posts back to the page itself is normal.
        resolved = urljoin(base_url, stripped)
        base_origin = DBCDispatcher._origin_of(base_url)
        if base_origin is None:
            return None
        if DBCDispatcher._origin_of(resolved) != base_origin:
            return None
        return resolved

    @staticmethod
    def _origin_of(url: str) -> Optional[tuple]:
        """Deprecated alias for :func:`kuasarr.providers.network.origin_guard.origin_of`."""
        return _origin_of(url)

    @staticmethod
    def _same_origin_guard_for(session: requests.Session, base_url: str) -> requests.Session:
        """Deprecated alias for :func:`...origin_guard.same_origin_guard_for`."""
        return _same_origin_guard_for(session, base_url)

    def _solve_keeplinks_captcha(
        self,
        session: requests.Session,
        soup: BeautifulSoup,
        url: str,
        headers: dict,
        password: str,
        mirror: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Solve the Keeplinks image captcha (cool or simple) and submit it."""
        variant, captcha_url = self._detect_keeplinks_captcha(soup)
        if not variant:
            info("Keeplinks: No CAPTCHA image and no links found")
            return None

        info(f"Keeplinks: {variant} captcha detected")

        if not self._client:
            info("Keeplinks: DBC client not initialized")
            return None

        debug(f"Keeplinks: CAPTCHA image URL: {captcha_url}")
        captcha_url = self._same_origin_asset_url(url, captcha_url)
        if not captcha_url:
            info("Keeplinks: CAPTCHA image URL is not on the container origin - refusing to fetch")
            return None
        captcha_response = session.get(
            captcha_url, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS)
        )
        if captcha_response.status_code != 200:
            info("Keeplinks: Failed to download CAPTCHA image")
            return None

        debug(f"Keeplinks: Solving image CAPTCHA ({len(captcha_response.content)} bytes)")
        captcha_result = self._client.solve_captcha(captcha_response.content)

        if not captcha_result or not captcha_result.text:
            info("Keeplinks: DBC failed to solve CAPTCHA")
            return None

        solved_text = captcha_result.text
        # Die Referenzimplementierung postet die Solver-Antwort unveraendert.
        # Die Normalisierung bleibt als Plausibilitaetspruefung: ein Ergebnis,
        # das nach dem Aufraeumen leer ist, war schon immer unbrauchbar und
        # geht nicht als Antwort an Keeplinks.
        normalized = self._normalize_keeplinks_answer(variant, solved_text)
        info(f"Keeplinks: CAPTCHA solved: '{solved_text}' (normalized '{normalized}')")

        if not normalized:
            info(f"Keeplinks: Unusable solver response '{solved_text}'")
            self._report_incorrect(captcha_result.captcha_id)
            return None

        answer = solved_text

        # Keeplinks wants the full hidden field set next to the answer - posting
        # only the answer field gets the container rejected.
        hiddenpwd_input = soup.find('input', {'name': 'hiddenpwd'})
        hiddenpwd_val = (hiddenpwd_input.get('value', '') if hiddenpwd_input else '') or ''
        password_field_exists = soup.find('input', {'id': 'password'}) is not None

        post_data = {
            'myhiddenpwd': hiddenpwd_val,
            'hiddenaction': 'Q2hlY2tJbmZv',
            'captchatype': 'Cool' if variant == 'cool' else 'Simple',
            'hiddencaptcha': '1',
            'hiddenpwd': hiddenpwd_val,
            KEEPLINKS_ANSWER_FIELDS[variant]: answer,
        }
        if password_field_exists and password:
            post_data['password'] = password

        debug(f"Keeplinks: Submitting {variant} CAPTCHA solution")
        response = session.post(
            url, data=post_data, headers=headers,
            allow_redirects=True,
            timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS),
        )

        if response.status_code != 200:
            info(f"Keeplinks: CAPTCHA POST failed with status {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # A rejection is signalled by the same captcha image coming back, which is
        # more reliable than scraping the localized error text.
        if soup.find('img', src=re.compile(re.escape(captcha_url))):
            info(f"Keeplinks: Rejected solution '{answer}'")
            self._report_incorrect(captcha_result.captcha_id)
            return None

        error_msg = soup.find('div', {'class': 'msg-error'})
        if error_msg:
            info(f"Keeplinks: Error message: {error_msg.get_text(strip=True)}")
            return None

        links = self._extract_keeplinks_download_links(soup)
        if not links:
            info("Keeplinks: No download links found after CAPTCHA submission")
            return None

        # Filter by mirror if specified
        if mirror:
            mirror_lower = mirror.lower()
            filtered_links = [link for link in links if mirror_lower in link.lower()]
            if filtered_links:
                links = filtered_links

        info(f"Keeplinks: Successfully extracted {len(links)} download links")
        return {"status": "success", "links": links}

    def _report_incorrect(self, captcha_id: Optional[int]) -> None:
        """Tell the captcha service the answer was wrong, so we get a refund."""
        if not captcha_id or not self._client:
            return
        try:
            self._client.report_incorrect(captcha_id)
            debug(f"Reported incorrect CAPTCHA {captcha_id} to solver")
        except (DBCError, CaptchaClientError) as exc:
            info(f"Could not report incorrect CAPTCHA {captcha_id}: {exc}")

    def _extract_keeplinks_download_links(self, soup: BeautifulSoup) -> list:
        """Extract download links from a Keeplinks page.
        
        Links are in <label class="form_box_title"> with <a class="selecttext live">
        Filters out ads/affiliate links.
        """
        links = []
        
        # Patterns for valid download links (must have file path)
        hoster_patterns = [
            r'rapidgator\.net/file/',
            r'rg\.to/file/',
            r'ddownload\.com/[a-z0-9]+/',
            r'uploaded\.net/file/',
            r'uploaded\.to/file/',
            r'ul\.to/[a-z0-9]+',
            r'nitroflare\.com/view/',
            r'turbobit\.net/[a-z0-9]+/',
            r'1fichier\.com/\?[a-z0-9]+',
            r'katfile\.com/[a-z0-9]+/',
            r'mexashare\.com/[a-z0-9]+/',
            r'depositfiles\.com/files/',
            r'filefactory\.com/file/',
        ]
        
        combined_pattern = '|'.join(hoster_patterns)
        
        # First try: Look for links in form_box_title (Keeplinks specific)
        form_boxes = soup.find_all('label', class_='form_box_title')
        for box in form_boxes:
            for link in box.find_all('a', href=True):
                href = link.get('href', '').strip()
                if re.search(combined_pattern, href, re.IGNORECASE):
                    if href not in links:
                        links.append(href)
                        debug(f"Keeplinks: Found download link: {href[:60]}...")
        
        # Fallback: Look for links with class "selecttext"
        if not links:
            for link in soup.find_all('a', class_='selecttext'):
                href = link.get('href', '').strip()
                if re.search(combined_pattern, href, re.IGNORECASE):
                    if href not in links:
                        links.append(href)
                        debug(f"Keeplinks: Found download link (selecttext): {href[:60]}...")
        
        # Final fallback: Any matching link without image and not affiliate
        if not links:
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').strip()
                
                # Skip links with images (ads/banners)
                if link.find('img'):
                    continue
                
                # Skip affiliate/free links
                if '/free' in href.lower() or 'affiliate' in href.lower():
                    continue
                
                if re.search(combined_pattern, href, re.IGNORECASE):
                    if href not in links:
                        links.append(href)
                        debug(f"Keeplinks: Found download link (fallback): {href[:60]}...")
        
        return links

    def _solve_tolink_with_dbc(
        self,
        title: str,
        url: str,
        password: str,
        mirror: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Solve ToLink using DBC for image captcha solving.
        
        ToLink uses a simple image captcha similar to Keeplinks.
        
        Flow:
        1. GET the page
        2. Find and solve CAPTCHA image via DBC
        3. POST CAPTCHA solution
        4. Extract download links
        """
        info(f"Attempting to decrypt ToLink: {url}")
        
        session = self._same_origin_guard_for(requests.Session(), url)
        headers = {
            'User-Agent': self.shared_state.values["user_agent"],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': url,
        }
        
        try:
            # Step 1: Initial GET request
            debug(f"ToLink: Initial GET request")
            response = session.get(url, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
            
            if response.status_code != 200:
                info(f"ToLink: Initial request failed with status {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Step 2: Check for download links first (might be visible without captcha)
            links = self._extract_tolink_download_links(soup)
            if links:
                info(f"ToLink: Found {len(links)} links (no CAPTCHA solving needed)")
                return {"status": "success", "links": links}
            
            # Step 3: Find and solve CAPTCHA
            captcha_img = soup.find('img', src=re.compile(r'captcha', re.IGNORECASE))
            if not captcha_img:
                # Try alternative captcha image patterns
                captcha_img = soup.find('img', {'id': re.compile(r'captcha', re.IGNORECASE)})
            if not captcha_img:
                captcha_img = soup.find('img', {'class': re.compile(r'captcha', re.IGNORECASE)})
            
            if not captcha_img:
                # ToLink also serves an ASCII "text" captcha instead of a PNG.
                if soup.find('form', {'id': 'challange'}):
                    info("ToLink: No image CAPTCHA - trying ASCII text captcha")
                    return self._solve_tolink_text_captcha(session, soup, url, headers, password, mirror)
                info("ToLink: No CAPTCHA image found and no links available")
                return None

            captcha_url = captcha_img.get('src', '')
            captcha_url = self._same_origin_asset_url(url, captcha_url)
            if not captcha_url:
                info("ToLink: CAPTCHA image URL is not on the container origin - refusing to fetch")
                return None

            debug(f"ToLink: CAPTCHA image URL: {captcha_url}")
            
            # Download CAPTCHA image
            captcha_response = session.get(captcha_url, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
            if captcha_response.status_code != 200:
                info(f"ToLink: Failed to download CAPTCHA image")
                return None
            
            # Step 4: Solve CAPTCHA via DBC
            if not self._client:
                info("ToLink: DBC client not initialized")
                return None
            
            debug(f"ToLink: Solving image CAPTCHA ({len(captcha_response.content)} bytes)")
            captcha_result = self._client.solve_captcha(captcha_response.content)
            
            if not captcha_result or not captcha_result.text:
                info("ToLink: DBC failed to solve CAPTCHA")
                return None
            
            captcha_token = captcha_result.text
            info(f"ToLink: CAPTCHA solved: {captcha_token}")
            
            # Step 5: Find form and submit CAPTCHA solution
            captcha_form = soup.find('form')
            if not captcha_form:
                info("ToLink: Could not find form")
                return None
            
            # Build POST data
            post_data = {}
            for input_elem in captcha_form.find_all('input'):
                name = input_elem.get('name')
                value = input_elem.get('value', '')
                if name:
                    # Common captcha field names
                    if name.lower() in ['captcha', 'captcha_code', 'code', 'security_code']:
                        post_data[name] = captcha_token
                    else:
                        post_data[name] = value
            
            # If no captcha field found, try common names
            if not any(k.lower() in ['captcha', 'captcha_code', 'code', 'security_code'] for k in post_data.keys()):
                post_data['captcha'] = captcha_token
            
            debug(f"ToLink: Submitting CAPTCHA solution")
            form_action = captcha_form.get('action', '')
            if form_action:
                form_action = urljoin(url, form_action.strip())
                # The action comes from container HTML we do not control, and
                # post_data carries the form's hidden fields (myhiddenpwd, i.e.
                # the release password hash). Only ever post that to the
                # container's own origin.
                submit_url = self._same_origin_asset_url(url, form_action)
                if not submit_url:
                    info("ToLink: form action is not on the container origin - refusing to POST")
                    return None
            else:
                submit_url = url

            response = session.post(submit_url, data=post_data, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
            
            if response.status_code != 200:
                info(f"ToLink: CAPTCHA POST failed with status {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check for error messages
            error_msg = soup.find(text=re.compile(r'wrong|invalid|incorrect|error', re.IGNORECASE))
            if error_msg and 'captcha' in str(error_msg).lower():
                info(f"ToLink: CAPTCHA was rejected")
                return None
            
            # Step 6: Extract download links
            links = self._extract_tolink_download_links(soup)
            
            if not links:
                info("ToLink: No download links found after CAPTCHA submission")
                return None
            
            # Filter by mirror if specified
            if mirror:
                mirror_lower = mirror.lower()
                filtered_links = [link for link in links if mirror_lower in link.lower()]
                if filtered_links:
                    links = filtered_links
            
            info(f"ToLink: Successfully extracted {len(links)} download links")
            return {"status": "success", "links": links}
            
        except requests.RequestException as e:
            info(f"ToLink: Request error - {e}")
            return None
        except Exception as e:
            info(f"ToLink: Unexpected error - {e}")
            return None

    def _extract_tolink_download_links(self, soup: BeautifulSoup) -> list:
        """Extract download links from a ToLink page.

        Similar to Keeplinks extraction but adapted for ToLink's structure.
        """
        links = []

        combined_pattern = '|'.join(DOWNLOAD_LINK_PATTERNS)
        
        # Look for all links matching hoster patterns
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').strip()
            
            # Skip links with images (ads/banners)
            if link.find('img'):
                continue
            
            # Skip affiliate/free links
            if '/free' in href.lower() or 'affiliate' in href.lower():
                continue
            
            if re.search(combined_pattern, href, re.IGNORECASE):
                if href not in links:
                    links.append(href)
                    debug(f"ToLink: Found download link: {href[:60]}...")

        return links

    @staticmethod
    def _extract_tolink_ascii_text(soup: BeautifulSoup) -> Optional[str]:
        """Pull the ASCII art captcha text out of a ToLink challenge page.

        ToLink marks the captcha block up in two different ways depending on the
        theme: either as a short single-line ``<pre>`` or as a multi-line block
        inside a div/span/code. Both are sniffed, and the block is only accepted
        when it is dense enough in ASCII drawing characters to actually be art
        rather than page boilerplate.

        The thresholds below (20 chars / no newline for ``<pre>``, 50 chars total
        plus 3 newlines plus 20 drawing characters for the block form) look far too
        tight for four rows of ASCII art, but they are what the original solver
        checks - verified against the bytecode of the reference implementation, not
        guessed. Keep them as they are.
        """
        text_captcha_content = None

        for pre in soup.find_all('pre'):
            text = pre.get_text()
            if not text:
                continue
            if len(text.strip()) > 20:
                continue
            if '\n' in text:
                continue
            text_captcha_content = text
            break

        if not text_captcha_content:
            for tag in soup.find_all(['div', 'span', 'code']):
                text = tag.get_text()
                if not text:
                    continue
                # Total length, not width per line - see the docstring.
                if len(text.strip()) > 50:
                    continue
                if text.count('\n') < 3:
                    continue
                # Real ASCII art is dense in drawing characters.
                special_chars = sum(1 for c in text if c in '|/-\\_[]{}()=+*#@')
                if special_chars <= 20:
                    continue
                text_captcha_content = text
                break

        if not text_captcha_content:
            return None
        return text_captcha_content.strip()

    @staticmethod
    def _render_tolink_ascii_png(ascii_text: str) -> Optional[bytes]:
        """Render ToLink's ASCII art into a PNG the captcha service can read.

        The captcha service only accepts image captchas, so the plain text has to
        be drawn first. Returns PNG bytes, or ``None`` when Pillow is unavailable.
        """
        try:
            import io

            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:
            info(f"ToLink: Pillow is required for the ASCII captcha: {exc}")
            return None

        font_size = 15
        line_height = font_size + 4
        padding = 10
        hint_height = 25

        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
        ]
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, font_size)
                debug(f"ToLink: Using font: {path}")
                break
            except OSError:
                continue
        if font is None:
            try:
                font = ImageFont.load_default()
                debug("ToLink: Using default font")
            except OSError as exc:
                info(f"ToLink: No usable font for the ASCII captcha: {exc}")
                return None

        lines = ascii_text.split('\n')
        if not lines:
            return None

        try:
            max_width = max(font.getlength(line) for line in lines)
        except AttributeError:
            # Very old Pillow builds have no getlength; 7px per char is close enough.
            max_width = max(len(line) for line in lines) * 7

        img_width = int(max_width + padding * 2)
        img_height = int(len(lines) * line_height + padding * 2 + hint_height)

        image = Image.new('RGB', (img_width, img_height), color=(17, 21, 23))
        draw = ImageDraw.Draw(image)

        try:
            hint_font = ImageFont.truetype(font_paths[0], 12) if font_paths else font
        except OSError:
            hint_font = font
        draw.text((padding, 5), 'ASCII art letters (A-Z only, case matters):',
                  fill=(255, 200, 100), font=hint_font)

        y = padding + hint_height
        for line in lines:
            draw.text((padding, y), line, fill=(200, 200, 200), font=font)
            y += line_height

        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def _correct_tolink_text_token(text_token: str) -> str:
        """Fix the glyph confusions OCR makes on ToLink's ASCII art.

        The substitutions are two tables applied in order and are taken verbatim
        from the reference implementation (its ``get_tolink_links``), verified
        against the compiled bytecode rather than inferred from the site hint:

        * ``number_subs`` - most entries map a digit onto the letter it visually
          resembles (``5``-``S``, ``0``/``9``-``O``, ``1``-``I``, ``8``-``B``,
          ``6``-``G``, ``2``-``Z``). The last one is the exception: ``7`` maps to
          ``!``, which is not a letter at all. That looks wrong next to the page
          hint "A-Z only", but it is what the reference does - do not "fix" it.
        * ``letter_subs`` - ``T``-``I`` and ``l``-``I``, i.e. letters that OCR
          confuses with each other.

        (A second build of the reference ships ``q``-``a`` instead of ``7``-``!``
        and adds ``l``-``I`` to the number table; the first table is kept because
        it is the one with a matching ``letter_subs`` pair.)
        """
        corrected = text_token or ''
        for old, new in TOLINK_NUMBER_SUBSTITUTIONS:
            corrected = corrected.replace(old, new)
        for old, new in TOLINK_LETTER_SUBSTITUTIONS:
            corrected = corrected.replace(old, new)
        return corrected

    def _solve_tolink_text_captcha(
        self,
        session: requests.Session,
        soup: BeautifulSoup,
        url: str,
        headers: dict,
        password: str,
        mirror: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Solve ToLink's ASCII text captcha (plus an optional reCAPTCHA) and submit."""
        challenge_form = soup.find('form', {'id': 'challange'})
        if not challenge_form:
            info("ToLink: No challenge form found")
            return None

        csrf_input = soup.find('input', {'name': 'csrf'})
        if not csrf_input:
            info("ToLink: Could not find CSRF token")
            return None
        csrf_token = csrf_input.get('value', '') or ''

        captcha_text_id_input = soup.find('input', {'name': 'captcha-text[id]'})
        captcha_text_id = (
            (captcha_text_id_input.get('value', '') if captcha_text_id_input else '') or ''
        )

        password_field_exists = soup.find('input', {'id': 'password'}) is not None
        recaptcha_exists = soup.find('div', {'class': 'g-recaptcha'}) is not None
        ascii_text = self._extract_tolink_ascii_text(soup)

        info(
            f"ToLink: Challenge detected (password: {password_field_exists}, "
            f"reCAPTCHA: {recaptcha_exists}, textCaptcha: {ascii_text is not None})"
        )

        if not ascii_text and not password_field_exists and not recaptcha_exists:
            info("ToLink: Nothing to solve on the challenge page")
            return None

        if not self._client:
            info("ToLink: DBC client not initialized")
            return None

        # An arithmetic captcha can be answered locally, no credits burned.
        answer = solve_math_captcha(ascii_text) if ascii_text else None

        captcha_id = None
        if ascii_text and not answer:
            info(f"ToLink: Solving ASCII text captcha ({len(ascii_text)} chars)")
            debug(f"ToLink: ASCII art content:\n{ascii_text}")

            image_bytes = self._render_tolink_ascii_png(ascii_text)
            if not image_bytes:
                return None

            debug(f"ToLink: Rendered ASCII captcha to PNG ({len(image_bytes)} bytes)")
            captcha_result = self._client.solve_captcha(image_bytes)
            if not captcha_result or not captcha_result.text:
                info("ToLink: Text captcha solving failed")
                return None

            captcha_id = captcha_result.captcha_id
            # The service returns the string with line breaks - they have to go
            # before the glyph substitutions run.
            answer = ''.join(c for c in captcha_result.text if not c.isspace())
            info(f"ToLink: Text CAPTCHA {captcha_id} solved: '{answer}'")
        elif answer:
            info(f"ToLink: Local math captcha solved: '{ascii_text}' -> '{answer}'")

        # reCAPTCHA is layered on top of some containers; solve it separately.
        recaptcha_token = None
        if recaptcha_exists:
            info("ToLink: Solving reCAPTCHA via captcha service")
            recaptcha_token = self._solve_recaptcha_token(url, soup)
            if not recaptcha_token:
                info("ToLink: Could not solve reCAPTCHA")
                return None

        post_data = {
            'csrf': csrf_token,
            'captcha-text[id]': captcha_text_id,
            'captcha-text[input]': self._correct_tolink_text_token(answer) if answer else '',
            'submit': TOLINK_SUBMIT_LABEL,
        }
        if password_field_exists and password:
            post_data['password'] = password
        if recaptcha_token:
            post_data['g-recaptcha-response'] = recaptcha_token

        post_headers = dict(headers)
        post_headers['Content-Type'] = 'application/x-www-form-urlencoded'

        info(f"ToLink: Submitting text CAPTCHA solution")
        response = session.post(
            url, data=post_data, headers=post_headers,
            allow_redirects=True,
            timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS),
        )

        if response.status_code != 200:
            info(f"ToLink: POST failed with status {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # The challenge form is still on the page -> the answer was wrong.
        if soup.find('form', {'id': 'challange'}):
            info(f"ToLink: Text captcha rejected (submitted: '{post_data['captcha-text[input]']}')")
            self._report_incorrect(captcha_id)
            return None

        links = self._extract_tolink_download_links(soup)
        if not links:
            info("ToLink: Could not extract links after ASCII captcha submit")
            return None

        # Filter by mirror if specified
        if mirror:
            mirror_lower = mirror.lower()
            filtered_links = [link for link in links if mirror_lower in link.lower()]
            if filtered_links:
                links = filtered_links

        info(f"ToLink: Successfully extracted {len(links)} download links (ASCII captcha)")
        return {"status": "success", "links": links}

    @staticmethod
    def _decode_he_form_snapshot(raw_snapshot: Optional[str]) -> Optional[Dict[str, Any]]:
        """Parse the JSON that :data:`HE_FORM_SNAPSHOT_JS` returns.

        Returns ``None`` when the browser found no Content Protector form, which
        means the page is already unlocked.
        """
        if not raw_snapshot:
            return None

        try:
            snapshot = json.loads(raw_snapshot)
        except (TypeError, ValueError) as exc:
            debug(f"he: could not decode form snapshot: {exc}")
            return None

        normalized_fields = []
        try:
            for field in snapshot.get('fields') or []:
                name = (field[0] or '').strip()
                value = field[1]
                if not name:
                    return None
                if isinstance(value, list):
                    # Repeatable fields arrive as a list of values.
                    normalized_fields.extend((name, str(item)) for item in value)
                else:
                    normalized_fields.append((name, str(value)))
        except (TypeError, ValueError, IndexError) as exc:
            debug(f"he: malformed form fields: {exc}")
            return None

        try:
            image = base64.b64decode(snapshot.get('imageBase64') or '', validate=True)
        except (TypeError, ValueError) as exc:
            debug(f"he: could not decode captcha image: {exc}")
            image = b''

        return {
            'action': snapshot.get('action') or '',
            'fields': normalized_fields,
            'captcha_id': snapshot.get('captchaId') or '',
            'image': image,
        }

    @classmethod
    def _he_form_snapshot_from_html(cls, html: str, page_url: str) -> Optional[Dict[str, Any]]:
        """Build the same snapshot shape straight from the HTML.

        Used for pages that FlareSolverr did not have to touch, where the form is
        plain markup and the captcha image can be fetched with a normal request.
        """
        soup = BeautifulSoup(html or '', 'html.parser')
        form = soup.find('form', id=re.compile(r'content-protector-access-form'))
        if not form:
            return None

        action = form.get('action') or page_url
        fields = [
            (inp['name'], inp.get('value', '') or '')
            for inp in form.find_all('input')
            if inp.get('name')
        ]
        captcha_id_input = form.find('input', {'name': 'captcha_id'})
        image_tag = form.find('img', src=True)

        # action/image come from markup we do not control. The answer is posted
        # back to `action`, and the image is fetched directly, so both stay on
        # the container's origin.
        safe_action = cls._same_origin_asset_url(page_url, urljoin(page_url, action))
        if not safe_action:
            return None
        image_url = ''
        if image_tag:
            image_url = cls._same_origin_asset_url(page_url, image_tag['src']) or ''

        return {
            'action': safe_action,
            'fields': fields,
            'captcha_id': (captcha_id_input.get('value', '') if captcha_id_input else '') or '',
            'image_url': image_url,
        }

    @staticmethod
    def _replace_he_captcha_answer(fields: List[Tuple[str, str]], answer: str) -> List[Tuple[str, str]]:
        """Swap the placeholder value of the ``captcha_answer`` field."""
        return [
            (name, answer if name == 'captcha_answer' else value)
            for name, value in fields
        ]

    def _extract_he_download_links(self, soup: BeautifulSoup) -> list:
        """Collect the unlocked download links from an he.to container page."""
        links = []

        # Once unlocked he.to marks the container explicitly; fall back to the
        # still-present protector form for the theme that does not.
        anchors = soup.select('#unlocked a[href], .content-protector-access-form a[href]')
        seen = set()
        for anchor in anchors:
            href = (anchor.get('href') or '').strip()
            if not href or not href.startswith('http') or href in seen:
                continue
            seen.add(href)
            links.append(href)

        if links:
            debug(f"he: Found {len(links)} links in the unlocked container")
            return links

        return self._extract_tolink_download_links(soup)

    def _solve_he_with_dbc(
        self,
        title: str,
        url: str,
        password: str,
        mirror: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Solve the he.to / hit-parade Content Protector captcha.

        Flow:
        1. Load the container (FlareSolverr when Cloudflare is in the way, plain
           requests otherwise) and snapshot the Content Protector form
        2. Download the captcha image and solve it via the captcha service
        3. POST the form back with the answer in ``captcha_answer``
        4. Extract the now-unlocked download links
        """
        info(f"Attempting to decrypt he.to container: {url}")

        if not self._client:
            info("he: captcha client not initialized")
            return None

        try:
            # The whole flow stays inside the context manager: the browser session
            # that carries the Cloudflare cookies must survive until the POST.
            with self._he_open_container(url) as (page_url, page_html, snapshot, post_fn):
                return self._he_solve_with_snapshot(
                    page_url, page_html, snapshot, post_fn, url, mirror)
        except Exception as exc:
            info(f"he: could not load container: {exc}")
            return None

    def _he_solve_with_snapshot(
        self,
        page_url: str,
        page_html: str,
        snapshot: Optional[Dict[str, Any]],
        post_fn: Any,
        url: str,
        mirror: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Snapshot -> solve -> POST -> extract. Split out so the whole sequence
        can run inside :meth:`_he_open_container`."""
        if not snapshot:
            snapshot = self._he_form_snapshot_from_html(page_html, page_url)

        if not snapshot:
            links = self._extract_he_download_links(BeautifulSoup(page_html, 'html.parser'))
            if links:
                info(f"he: Container already unlocked - {len(links)} links")
                return {"status": "success", "links": links}
            info("he: No Content Protector form and no links found")
            return None

        if not snapshot.get('captcha_id') or not snapshot.get('fields'):
            info("he: Content Protector form is incomplete")
            return None

        image = snapshot.get('image')
        if not image and snapshot.get('image_url'):
            # The snapshot may come from FlareSolverr, where image_url is passed
            # through from the page markup unvalidated - re-check the origin.
            safe_image_url = self._same_origin_asset_url(page_url, snapshot['image_url'])
            if not safe_image_url:
                info("he: CAPTCHA image URL is not on the container origin - refusing to fetch")
                return None
            image = self._he_fetch_image(safe_image_url)

        if not image or len(image) < 100:
            info("he: Could not read the CAPTCHA image")
            return None

        debug(f"he: Solving CAPTCHA image ({len(image)} bytes)")
        captcha_result = self._client.solve_captcha(image)
        if not captcha_result or not captcha_result.text:
            info("he: DBC failed to solve CAPTCHA")
            return None

        answer = captcha_result.text.strip()
        info(f"he: CAPTCHA {captcha_result.captcha_id} solved: '{answer}'")
        if not answer:
            self._report_incorrect(captcha_result.captcha_id)
            return None

        payload = self._replace_he_captcha_answer(snapshot['fields'], answer)
        # The snapshot may have come from FlareSolverr (JS-built form), so the
        # action is re-checked here rather than trusted from the snapshot alone.
        submit_url = self._same_origin_asset_url(page_url, snapshot.get('action') or page_url)
        if not submit_url:
            info("he: form action is not on the container origin - refusing to POST")
            self._report_incorrect(captcha_result.captcha_id)
            return None

        info(f"he: Submitting CAPTCHA solution")
        result_html = post_fn(submit_url, payload)

        if not result_html:
            info("he: Could not submit the Content Protector form")
            self._report_incorrect(captcha_result.captcha_id)
            return None

        soup = BeautifulSoup(result_html, 'html.parser')
        links = self._extract_he_download_links(soup)

        if not links:
            # The form is still there -> the answer was wrong.
            if soup.find('form', id=re.compile(r'content-protector-access-form')):
                info(f"he: CAPTCHA rejected (submitted '{answer}')")
                self._report_incorrect(captcha_result.captcha_id)
                return None
            info("he: No download links found after CAPTCHA submission")
            return None

        # Filter by mirror if specified
        if mirror:
            mirror_lower = mirror.lower()
            filtered_links = [link for link in links if mirror_lower in link.lower()]
            if filtered_links:
                links = filtered_links

        info(f"he: Successfully extracted {len(links)} download links")
        return {"status": "success", "links": links}

    @contextmanager
    def _he_open_container(self, url: str) -> Iterator[Tuple[str, str, Optional[Dict[str, Any]], Any]]:
        """Fetch the container page and keep its browser session alive.

        Yields ``(page_url, html, snapshot, post_fn)``. ``snapshot`` is filled
        when FlareSolverr had to render the page, because he.to assembles the
        Content Protector form in the browser; on a plain page it stays ``None``
        and the HTML snapshot is authoritative. ``post_fn(target, payload)``
        submits the form and returns the response HTML (or ``None``).

        This is a context manager because the FlareSolverr branch needs a
        dedicated browser session for *both* the snapshot GET and the POST. That
        session is created with a random id and destroyed again when the block is
        left - including on exceptions - so nothing piles up inside FlareSolverr.
        """
        headers = {'User-Agent': self.shared_state.values["user_agent"]}
        session = self._same_origin_guard_for(requests.Session(), url)

        try:
            response = session.get(url, headers=headers,
                                   timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
            cf_protected = response.status_code == 403 or is_cloudflare_challenge(response.text)
        except requests.RequestException as exc:
            debug(f"he: direct GET failed: {exc}")
            cf_protected = True
            response = None

        if not cf_protected:
            page_url = response.url

            def plain_post(target: str, payload: List[Tuple[str, str]]) -> Optional[str]:
                post_headers = dict(headers)
                post_headers['Content-Type'] = 'application/x-www-form-urlencoded'
                post_headers['Referer'] = page_url
                try:
                    posted = session.post(
                        target, data=dict(payload), headers=post_headers,
                        allow_redirects=True,
                        timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS),
                    )
                except requests.RequestException as exc:
                    info(f"he: submit failed: {exc}")
                    return None
                return posted.text

            yield page_url, response.text, None, plain_post
            return

        # Cloudflare: drive the page through FlareSolverr and keep the browser
        # session alive so the POST reuses its cookies.
        info("he: Cloudflare protection detected - using FlareSolverr")
        session_id = f"kuasarr-he-{uuid4().hex[:12]}"
        if not flaresolverr_create_session(self.shared_state, session_id):
            info("he: could not create FlareSolverr session")
            yield url, "", None, _he_post_unavailable
            return

        try:
            def browser_post(target: str, payload: List[Tuple[str, str]]) -> Optional[str]:
                try:
                    posted = flaresolverr_request(
                        self.shared_state,
                        target,
                        cmd="request.post",
                        post_data=urlencode(payload),
                        session_id=session_id,
                        execute_js=HE_FORM_SNAPSHOT_JS,
                        wait=2,
                    )
                except RuntimeError as exc:
                    info(f"he: FlareSolverr submit failed: {exc}")
                    return None
                if posted is None:
                    info("he: FlareSolverr returned no answer for the submit")
                    return None
                return posted.text

            try:
                page = flaresolverr_request(
                    self.shared_state,
                    url,
                    cmd="request.get",
                    session_id=session_id,
                    execute_js=HE_FORM_SNAPSHOT_JS,
                    wait=2,
                )
            except RuntimeError as exc:
                info(f"he: FlareSolverr not available: {exc}")
                page = None

            if page is None:
                yield url, "", None, _he_post_unavailable
                return

            debug(f"he: FlareSolverr loaded the container ({page.status_code})")
            snapshot = self._decode_he_form_snapshot(page.execute_js_result)
            # The FlareSolverr HTML has no server-rendered form, so the browser
            # snapshot is the only source of truth here.
            yield page.url, page.text, snapshot, browser_post
        finally:
            flaresolverr_destroy_session(self.shared_state, session_id)

    def _he_fetch_image(self, image_url: str) -> bytes:
        """Download the he.to captcha image with a plain request."""
        headers = {'User-Agent': self.shared_state.values["user_agent"],
                   'Referer': image_url}
        try:
            response = requests.get(image_url, headers=headers,
                                    timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
        except requests.RequestException as exc:
            info(f"he: could not download CAPTCHA image: {exc}")
            return b''

        content_type = response.headers.get('Content-Type', 'unknown')
        if 'image' not in content_type:
            info(f"he: CAPTCHA response is not an image: {content_type}")
            return b''

        return response.content

    def _solve_hide_cx(
        self,
        title: str,
        url: str,
        password: str,
        mirror: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Solve hide.cx links via API (no CAPTCHA needed)."""
        # No key gate here: the public hide.cx API resolves containers and their
        # per-link URLs without authentication, and unhide_links already sends
        # the Authorization header only when a key is configured. Skipping every
        # container because no key was set failed each package three times over
        # and then marked it as failed.
        info(f"Decrypting hide.cx link via API: {url}")
        
        links, error = unhide_links(self.shared_state, url, password)
        
        if error:
            if error.startswith("PERMANENT:"):
                error_msg = error[10:]  # Remove "PERMANENT:" prefix
                info(f"Permanent failure for hide.cx link: {url} - {error_msg}")
                raise PermanentLinkFailure(error_msg)
            info(f"Failed to decrypt hide.cx link: {url} - {error}")
            return None
        
        if not links:
            info(f"No links found in hide.cx container: {url}")
            return None
        
        info(f"Successfully decrypted {len(links)} links from hide.cx")
        return {
            "links": links,
            "source": "hide.cx",
            "mirror": mirror,
        }

    def _solve_generic_link(
        self,
        title: str,
        url: str,
        password: str,
    ) -> Optional[Dict[str, Any]]:
        """Generic link solving for non-Filecrypt links."""
        # For now, just return None - can be extended for other crypters
        info(f"Generic link type not supported: {url}")
        return None

    def _extract_misery_key(self, api_key: str, html: str) -> str:
        """Extract CutCaptcha misery key."""
        match = re.search(r"miserykey['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{32})['\"]", html)
        if match:
            return match.group(1)
        
        try:
            # Default CutCaptcha host for v2 API
            ccc_host = self.shared_state.values.get("cutcaptcha_host", "v2.cutcaptcha.net")
            url = f'https://{ccc_host}/captcha/{api_key}.js'
            debug(f"Fetching misery key from: {url}")
            response = requests.get(url, verify=False, timeout=10)
            match = re.findall(r"='([a-zA-Z0-9]{32})'", response.text)
            if match:
                debug(f"Misery key found: {match[0][:8]}...")
                return match[0]
            else:
                debug(f"No misery key found in response ({len(response.text)} bytes)")
        except Exception as exc:
            info(f"Misery Key error: {exc}")
        
        return ""

    def _mark_as_failed(self, package_id: str, title: str, reason: str) -> None:
        """Mark a package as failed."""
        try:
            failed = fail(title, package_id, self.shared_state, reason=f"DBC: {reason}")
            if failed:
                self.shared_state.get_db("protected").delete(package_id)
                send_discord_message(self.shared_state, title=title, case="failed")
        except Exception as exc:
            debug(f"Error marking as failed: {exc}")
        
        push_jobs.remove_job(package_id)
        StatsHelper(self.shared_state).increment_failed_decryptions_automatic()
        info(f"Package {title} marked as failed: {reason}")

    def _record_failure(self) -> None:
        """Record a failure and activate backoff."""
        base = max(1, int(
            self.shared_state.values.get("dbc_retry_backoff", DEFAULT_DISPATCH_INTERVAL_SECONDS)
        ))
        self._failure_streak += 1
        multiplier = min(MAX_BACKOFF_MULTIPLIER, 2 ** (self._failure_streak - 1))
        backoff = base * multiplier
        self._backoff_until = time.time() + backoff
        debug(f"DBC Dispatcher backoff active ({backoff}s, streak={self._failure_streak})")


__all__ = ["DBCDispatcher"]
