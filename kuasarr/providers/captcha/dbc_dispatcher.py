# -*- coding: utf-8 -*-
"""Background dispatcher for DeathByCaptcha captcha solving.

This dispatcher handles captcha solving via the DeathByCaptcha API
and integrates with the existing Filecrypt decryption logic.
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
import threading
import time
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from kuasarr.providers import shared_state
from kuasarr.providers.captcha import push_jobs
from kuasarr.providers.network.cloudflare import is_cloudflare_challenge, ensure_session_cf_bypassed
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
from kuasarr.downloads.linkcrypters.filecrypt import CNL, DLC
from kuasarr.downloads.linkcrypters.hide import unhide_links
from kuasarr.constants import HTTP_DEFAULT_TIMEOUT_SECONDS, get_timeout

DEFAULT_DISPATCH_INTERVAL_SECONDS = 10
MAX_BACKOFF_MULTIPLIER = 8
PROCESSING_STATUS = "processing"  # job is actively being worked on this tick


# --- Filecrypt Proof-of-Work captcha (click-and-let-page-solve) ---
# filecrypt.cc's PoW (<div id="pow-captcha" data-challenge data-difficulty>) is
# solved by filecrypt's OWN JS worker (SHA-1 brute-force + browser fingerprint).
# Earlier Kuasarr attempts replicated the SHA-1 in Python and POSTed self-built
# pow_x/pow_data tokens — filecrypt rejected them (the re-injected fingerprint
# flagged Code 605). The working mechanic (reverse-engineered from rix1337's
# sponsors-helper, see docs/filecrypt-pow-reverse-engineering.md): send a JS
# snippet to flaresolverr-next's executeJs that CLICKS filecrypt's PoW box
# (cubic-Bezier pointer glide + click), lets filecrypt's main-world JS compute
# the clean token, then re-submits the form via in-browser fetch() and returns
# the unlocked page HTML. No token is extracted, no nonce brute-forced, no
# fingerprint touched — pure browser automation of filecrypt's own UI flow.


def _get_pow_captcha(soup):
    return soup.find("div", {"id": "pow-captcha", "class": "pow-captcha"})


class _PowSolvedResponse:
    """Minimal response-like returned when PoW is solved via executeJs.

    Quacks like requests.Response for the downstream CNL/DLC extraction: carries
    the unlocked-page HTML (.text), the final URL (.url) and the HTTP status
    (.status_code). Built from the JSON the in-browser fetch() in the probe
    returns, so the rest of the pipeline can parse it with BeautifulSoup exactly
    like a normal page GET.
    """

    __slots__ = ("text", "url", "status_code", "content")

    def __init__(self, text: str, url: str, status_code: int):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.content = text.encode("utf-8", "replace") if isinstance(text, str) else text


def _ensure_script_path(shared_state, name):
    """Locate a JavaScript asset in the wheel; cache its on-disk path.

    Resolution order:
      1. previously cached path (shared_state)
      2. sibling of this file in source-tree: kuasarr/scripts/<name>
      3. system-wide install dir: /usr/local/share/kuasarr/<name>
      4. Extract from the installed wheel via importlib.resources into
         $TMPDIR/kuasarr_sidecar/<name>.
    """
    cache_key = f"kuasarr_asset_path::{name}"
    cached = shared_state.values.get(cache_key)
    if cached and os.path.exists(cached):
        return cached

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.normpath(os.path.join(here, "..", "scripts", name)),
        os.path.join("/usr/local/share/kuasarr", name),
    ]
    for p in candidates:
        if os.path.exists(p):
            shared_state.values[cache_key] = p
            return p

    try:
        from importlib.resources import files
        src = files("kuasarr.scripts").joinpath(name)
        extracted_dir = os.path.join(tempfile.gettempdir(), "kuasarr_sidecar")
        os.makedirs(extracted_dir, exist_ok=True)
        extracted = os.path.join(extracted_dir, name)
        if not os.path.exists(extracted):
            with open(extracted, "wb") as f:
                f.write(src.read_bytes())
        shared_state.values[cache_key] = extracted
        return extracted
    except Exception:
        return None


def _find_pow_probe(shared_state):
    return _ensure_script_path(shared_state, "filecrypt_pow_probe.js")


# JavaScript that runs inside flaresolverr-next's Chrome browser via executeJs.
# We load the script body from disk (filecrypt_pow_probe.js) instead of inlining
# it as a Python triple-quoted string. That eliminates the multi-pass JSON-escape
# pipeline that was corrupting `\\\\b` regex tokens and making the previous
# executeJs come back as an empty string.
#
# The script itself reports every step (DOM, fetch, load, eval, R/S, collect)
# in `out.steps` so the dispatcher can log exactly what failed — the previous
# version only said "empty executeJsResult" with no detail.
def _load_fs_execjs(shared_state):
    """Read the executeJs snippet from disk and return its raw text.

    If the probe file can't be located, fall back to a minimal inline snippet
    so the dispatcher still has *something* to send.
    """
    path = _find_pow_probe(shared_state)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as exc:
            info(f"Filecrypt PoW: could not read probe from {path}: {exc}")
    # Last-resort inline fallback (kept tiny on purpose: no regex backrefs).
    return "(async function(){return JSON.stringify({ok:false,error:'probe missing'});})();"


def _create_or_get_pow_session(shared_state):
    """Get or create a flaresolverr-next session id for filecrypt PoW work.

    Reusing a session keeps the same cf_clearance cookie + Chrome browser
    instance across the PoW-solve and the SHA-1 POST, so the fingerprint
    tokens match what filecrypt's server recorded.
    """
    sid = shared_state.values.get("filecrypt_pow_session")
    if sid:
        return sid
    flaresolverr_url = shared_state.values["config"]("FlareSolverr").get("url")
    if not flaresolverr_url:
        return ""
    session_name = f"kuasarr_filecrypt_pow_{int(time.time())}"
    try:
        resp = requests.post(
            flaresolverr_url, json={"cmd": "sessions.create", "session": session_name},
            headers={"Content-Type": "application/json"},
            timeout=get_timeout(15),
        )
        resp.raise_for_status()
        sid = resp.json().get("session")
        if sid:
            shared_state.values["filecrypt_pow_session"] = sid
            info(f"Filecrypt PoW: created flaresolverr session {sid}")
            return sid
    except Exception as exc:
        info(f"Filecrypt PoW: failed to create flaresolverr session: {exc}")
    return ""


def _compute_pow_via_flaresolverr(shared_state, page_url):
    """Drive filecrypt's PoW box via flaresolverr-next executeJs (click-and-let-page-solve).

    Loads the JS snippet from kuasarr/scripts/filecrypt_pow_probe.js, sends it to
    flaresolverr-next's persistent session (which holds the cf_clearance cookie +
    headed-Xvfb Chrome fingerprint from the CF bypass). The snippet clicks filecrypt's
    PoW box (cubic-Bezier pointer glide + click), lets filecrypt's main-world JS
    compute the clean PoW token, then re-submits the form via in-browser fetch()
    and returns the unlocked-page HTML. We do NOT extract pow_x/pow_data ourselves.

    Returns a `_PowSolvedResponse` (.text + .url + .status_code) on success, or
    `None` on any failure (no session, executeJs error, timeout, haspow=true, etc.).
    The caller (in _solve_filecrypt_pow_if_present) treats None as "retry/hand-off".
    """
    flaresolverr_url = shared_state.values["config"]("FlareSolverr").get("url")
    if not flaresolverr_url:
        return None

    sid = _create_or_get_pow_session(shared_state)
    if not sid:
        return None

    payload = {
        "cmd": "request.get",
        "url": page_url,
        "session": sid,
        "maxTimeout": 60000,
        # Small waitInSeconds: the JS self-terminates by resolving its promise
        # with the final {status,code,url,haspow,html} payload. We only need
        # the post-JS settle delay for any post-resolution cleanup (rare).
        "waitInSeconds": 3,
        "executeJs": _load_fs_execjs(shared_state),
    }
    try:
        resp = requests.post(
            flaresolverr_url, json=payload,
            headers={"Content-Type": "application/json"},
            timeout=get_timeout(90),
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        info(f"Filecrypt PoW: flaresolverr executeJs HTTP error: {exc}")
        return None

    result = resp.json()
    if result.get("status") != "ok":
        info(f"Filecrypt PoW: flaresolverr status={result.get('status')}: {result.get('message', '<no msg>')[:200]}")
        return None

    exec_result = result["solution"].get("executeJsResult", "")
    if not exec_result:
        # Empty executeJsResult means the probe script did not return a promise
        # (Promise-Return-Bug from Versuch 7, already fixed — but if it recurs,
        # check the probe source ends with `return new Promise(...)`).
        info(
            "Filecrypt PoW: flaresolverr returned empty executeJsResult — "
            "Probe-Snippet-Promise-Return (Versuch 7) nicht aktiv. Prüfe: "
            "(1) rix1337/flaresolverr-next Image aktiv, "
            "(2) filecrypt_pow_probe.js endet mit `return new Promise(...)`, "
            "(3) tempfile-Cache /tmp/kuasarr_sidecar/filecrypt_pow_probe.js aktuell."
        )
        return None

    try:
        parsed = json.loads(exec_result)
    except json.JSONDecodeError as exc:
        info(f"Filecrypt PoW: executeJs result not JSON: {exc}: {exec_result[:200]}")
        return None

    # Diagnostic dump — log the diag payload (which carries the fingerprint
    # diagnostics: hasChromeRuntime, pointer, hover) so we can SEE on run one
    # whether the headed-Xvfb FS-next browser actually carries the expected
    # fingerprint. This settles the Code-605 question once and for all.
    diag = parsed.get("diag") or {}
    info(
        f"Filecrypt PoW probe diag: hasChrome={diag.get('hasChrome')} "
        f"hasChromeRuntime={diag.get('hasChromeRuntime')} "
        f"hasChromeWebstore={diag.get('hasChromeWebstore')} "
        f"pointer={diag.get('pointer')} hover={diag.get('hover')}"
    )

    status = parsed.get("status")
    if status != "ok":
        info(f"Filecrypt PoW: probe not ok — status={status!r} state={parsed.get('state')!r} "
             f"error={parsed.get('error')!r}")
        return None

    if parsed.get("haspow"):
        # filecrypt re-showed the PoW in the response → token was rejected. Caller
        # should retry; if all retries fail, fall back to the manual handoff.
        info("Filecrypt PoW: probe returned haspow=true — filecrypt rejected the submission")
        return None

    info(
        f"Filecrypt PoW: solved via FS-next executeJs "
        f"(code={parsed.get('code')}, haspow=False, html_len={len(parsed.get('html') or '')})"
    )
    return _PowSolvedResponse(
        text=parsed.get("html", "") or "",
        url=parsed.get("url", page_url),
        status_code=int(parsed.get("code") or 200),
    )



def _solve_filecrypt_pow_if_present(shared_state, session, output, headers):
    """Solve filecrypt.cc's PoW captcha via flaresolverr-next executeJs (click-and-let-page-solve).

    The probe script (kuasarr/scripts/filecrypt_pow_probe.js) drives filecrypt's
    own PoW box: cubic-Bezier pointer glide + click on `.pow-captcha__box`, lets
    filecrypt's m.js/s.js/SHA-1 worker compute the clean token in the main-world
    page context, then re-submits the form via in-browser fetch() and returns
    the unlocked-page HTML.

    This dispatcher up to 3 times (filecrypt sometimes requires a re-solve on
    a fresh pow_id rotation). On success, returns a _PowSolvedResponse that the
    downstream CNL/DLC extraction can parse. On total failure, raises
    RuntimeError so the caller hands the captcha off to the manual /captcha route.

    Why this works (and the earlier extract-and-POST did not):
    earlier attempts re-injected m.js/s.js via <script textContent> inside the
    executeJs isolated world; m.js there saw an empty `window.chrome.runtime`
    and reported Code 605. The current approach NEVER re-injects — it only
    dispatches a click, letting filecrypt's page-loaded m.js (which runs in the
    main world with the real headed-Xvfb-Chrome fingerprint from
    flaresolverr-next) compute the token.
    """
    if not _get_pow_captcha(BeautifulSoup(output.text, "html.parser")):
        return output

    MAX_ATTEMPTS = 3

    for attempt in range(1, MAX_ATTEMPTS + 1):
        info(f"Filecrypt PoW: click-and-let-page-solve attempt {attempt}/{MAX_ATTEMPTS}")
        solved = _compute_pow_via_flaresolverr(shared_state, output.url)
        if solved is None:
            info(f"Filecrypt PoW: attempt {attempt} returned no solved-response (see prior log line)")
            continue
        return solved

    # All attempts exhausted. Surface a clear reason so the caller hands the
    # captcha off to the manual /captcha route instead of looping forever.
    raise RuntimeError(
        "Filecrypt PoW: failed after "
        f"{MAX_ATTEMPTS} click-and-let-page-solve attempts — handing off to manual"
    )


class PermanentLinkFailure(Exception):
    """Raised when a link permanently fails (e.g., offline) and should not be retried."""
    pass


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

            # Skip packages awaiting manual captcha solving (filecrypt PoW etc.).
            # TTL: after 7 days without a manual solve, fail the package for good
            # (otherwise the queue fills up with packages no one ever solves).
            if data.get("needs_manual"):
                ts = data.get("manual_timestamp", 0)
                try:
                    if ts and (time.time() - float(ts) > 7 * 86400):
                        self._mark_as_failed(package_id, data.get("title", package_id),
                                             "Manual solve timeout (7d)")
                except (TypeError, ValueError):
                    pass
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

                # PoW/Captcha not auto-solvable → hand off to manual queue (keep package,
                # flag it) instead of failing it.
                if result and result.get("status") == "manual_required":
                    self._mark_as_manual_required(
                        package_id, title, result.get("reason", "PoW"), result.get("url")
                    )
                    return False

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
                        
            except (DBCInsufficientCredits, CaptchaInsufficientCredits):
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
            return self._solve_keeplinks_with_dbc(title, link_url, password, mirror)
        elif "tolink" in link_url.lower() or "tolink" in mirror.lower():
            return self._solve_tolink_with_dbc(title, link_url, password, mirror)
        else:
            # For other link types, try generic approach
            return self._solve_generic_link(title, link_url, password)

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

        # Filecrypt Proof-of-Work-Captcha lösen (falls vorhanden) via lokalem
        # Python-Solver (SHA-1 brute-force, kein Browser, kein Fingerprinting).
        # RuntimeError → hand-off to manual handoff (Dispatcher fängt das ab).
        try:
            output = _solve_filecrypt_pow_if_present(self.shared_state, session, output, headers)
            soup = BeautifulSoup(output.text, 'html.parser')
        except RuntimeError as e:
            msg = str(e)
            # PoW-related failures → hand off to manual captcha queue (browser solve).
            # Other RuntimeErrors (transient network etc.) → None → retry.
            if "PoW" in msg or "proof-of-work" in msg or "needs browser" in msg:
                info(f"Filecrypt PoW not auto-solvable — handing off to manual queue: {e}")
                return {"status": "manual_required", "reason": "PoW needs browser solving", "url": url}
            info(f"Filecrypt PoW solve failed (transient): {e}")
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

                coords = self._client.solve_coordinates_captcha(img_resp.content)
                if coords:
                    click_x, click_y = coords
                    info(f"Circle-Captcha coordinates: x={click_x}, y={click_y}")
                    output = session.post(
                        url,
                        data=f"button.x={click_x}&button.y={click_y}",
                        headers={
                            **headers,
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Origin": origin,
                            "Referer": url,
                        },
                        timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS),
                    )
                    url = output.url
                    soup = BeautifulSoup(output.text, 'html.parser')
                    # If we still see circle_captcha, the answer was wrong — fall
                    # through to the rest of the loop and let DBC retry on the
                    # next package attempt.
                    if soup.find("div", {"class": "circle_captcha"}):
                        info("Circle-Captcha still present after DBC click — coordinates were wrong")
                else:
                    info("DBC returned no coordinates for Circle-Captcha")
            else:
                # No circle captcha — try CutCaptcha/reCAPTCHA/image via DBC.
                # The previous fallback (random coords then POST without token)
                # was a no-op that produced the 'Token rejected' message in the log;
                # we skip that path entirely to avoid the wasted POST.
                info("Attempting to solve captcha via DBC...")
                token = self._get_captcha_token(url, soup)
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
                    )
                    url = output.url
                else:
                    info("No captcha token received — nothing to submit")
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

    def _get_captcha_token(self, url: str, soup: BeautifulSoup) -> Optional[str]:
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
            site_key = recaptcha_div.get("data-sitekey", "")
            if site_key:
                info("reCAPTCHA detected, solving via DBC...")
                debug(f"DBC: reCAPTCHA sitekey: {site_key[:30]}...")
                try:
                    result = self._client.solve_recaptcha_v2(
                        site_key=site_key,
                        page_url=url,
                    )
                    if result.is_solved:
                        return result.text
                except (DBCError, CaptchaClientError) as e:
                    info(f"reCAPTCHA error: {e}")
        
        # Check for image captcha
        captcha_img = soup.find("img", {"id": "captcha_img"})
        debug(f"DBC: Image captcha found: {bool(captcha_img)}")
        if captcha_img:
            img_src = captcha_img.get("src", "")
            if img_src:
                info("Image captcha detected, solving via DBC...")
                debug(f"DBC: Image captcha src: {img_src[:80]}...")
                try:
                    if not img_src.startswith("http"):
                        img_src = requests.compat.urljoin(url, img_src)
                    img_response = requests.get(img_src, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                    result = self._client.solve_captcha(img_response.content)
                    if result.is_solved:
                        return result.text
                except Exception as e:
                    info(f"Image captcha error: {e}")
        
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

        for mirror_url in mirrors:
            if len(mirrors) > 1:
                output = session.get(mirror_url, headers=headers)
                url = output.url
                soup = BeautifulSoup(output.text, 'html.parser')

            try:
                # Try CNL (Click'n'Load)
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
                    filtered_cnl_result = session.post(filtered_cnl_link, headers=headers)
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
                break
            except:
                if "The owner of this folder has deactivated all hosts in this container in their settings." in soup.text:
                    info(f"Mirror deactivated by the owner: {mirror_url}")
                    continue

                info("Click'n'Load not found! Falling back to DLC...")
                try:
                    # Try DLC
                    crypted_payload = soup.find("button", {"class": "dlcdownload"}).get("onclick")
                    crypted_data = re.findall(r"'(.*?)'", crypted_payload)
                    dlc_secret = crypted_data[0]
                    domain = urlparse(url).netloc
                    if episode and season:
                        dlc_link = f"https://{domain}/DLC/{dlc_secret}.dlc?{episode}&{season}"
                    else:
                        dlc_link = f"https://{domain}/DLC/{dlc_secret}.dlc"
                    dlc_file = session.get(dlc_link, headers=headers).content
                    links.extend(DLC(self.shared_state, dlc_file).decrypt())
                    break
                except:
                    info("DLC not found! Falling back to Circle-Captcha buttons...")
                    
                    # Return replacement info for Circle-Captcha handling
                    base_url = urlparse(url).netloc
                    phpsessid = session.cookies.get('PHPSESSID')
                    if not phpsessid:
                        info("PHPSESSID cookie not found!")
                        return None

                    results = []
                    for button in soup.find_all('button'):
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
        
        session = requests.Session()
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
                        redirect_url = requests.compat.urljoin(url, match.group(1))
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
                        if not img_src.startswith("http"):
                            img_src = requests.compat.urljoin(url, img_src)
                        
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
                                redirect_url = requests.compat.urljoin(url, match.group(1))
                                redirect_resp = session.get(redirect_url, allow_redirects=True, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                                if redirect_resp.ok and "expired" not in redirect_resp.text.lower():
                                    info(f"Circle-Captcha successfully solved: {redirect_resp.url}")
                                    return [redirect_resp.url]
                
                time.sleep(2)
                
            except Exception as e:
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
        
        Keeplinks uses a simple image captcha (coolcaptcha) that DBC can solve.
        
        Flow:
        1. GET the page
        2. POST to proceed past "Click To Proceed"
        3. Get CAPTCHA image and solve via DBC
        4. POST CAPTCHA solution
        5. Extract download links
        """
        info(f"Attempting to decrypt Keeplinks: {url}")
        
        session = requests.Session()
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
                    post_data = {}
                    for input_elem in proceed_form.find_all('input'):
                        name = input_elem.get('name')
                        if name:
                            post_data[name] = input_elem.get('value', '')
                    
                    # Also check for buttons with names
                    for btn in proceed_form.find_all(['input', 'button'], {'type': 'submit'}):
                        name = btn.get('name')
                        if name:
                            post_data[name] = btn.get('value', '')
                    
                    response = session.post(url, data=post_data, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
                    
                    if response.status_code != 200:
                        info(f"Keeplinks: Proceed POST failed with status {response.status_code}")
                        return None
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
            
            # Step 3: Check for download links FIRST (they are visible on the CAPTCHA page!)
            links = self._extract_keeplinks_download_links(soup)
            if links:
                info(f"Keeplinks: Found {len(links)} links (no CAPTCHA solving needed)")
                return {"status": "success", "links": links}
            
            # Step 4: If no links found, try to find and solve CAPTCHA
            captcha_img = soup.find('img', src=re.compile(r'captcha', re.IGNORECASE))
            if not captcha_img:
                info("Keeplinks: No CAPTCHA image and no links found")
                return None
            
            captcha_url = captcha_img.get('src', '')
            if not captcha_url.startswith('http'):
                captcha_url = f"https://www.keeplinks.org{captcha_url}" if captcha_url.startswith('/') else f"https://www.keeplinks.org/{captcha_url}"
            
            debug(f"Keeplinks: CAPTCHA image URL: {captcha_url}")
            
            # Download CAPTCHA image
            captcha_response = session.get(captcha_url, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
            if captcha_response.status_code != 200:
                info(f"Keeplinks: Failed to download CAPTCHA image")
                return None
            
            # Step 4: Solve CAPTCHA via DBC (image captcha)
            if not self._client:
                info("Keeplinks: DBC client not initialized")
                return None
            
            debug(f"Keeplinks: Solving image CAPTCHA ({len(captcha_response.content)} bytes)")
            captcha_result = self._client.solve_captcha(captcha_response.content)
            
            if not captcha_result or not captcha_result.text:
                info("Keeplinks: DBC failed to solve CAPTCHA")
                return None
            
            captcha_token = captcha_result.text
            info(f"Keeplinks: CAPTCHA solved: {captcha_token}")
            
            # Step 5: Build POST data and submit CAPTCHA solution
            captcha_form = soup.find('form', {'name': 'frmprotect'})
            if not captcha_form:
                info("Keeplinks: Could not find CAPTCHA form")
                return None
            
            post_data = {}
            for input_elem in captcha_form.find_all('input'):
                name = input_elem.get('name')
                value = input_elem.get('value', '')
                if name:
                    if name == 'captcha_cool':
                        post_data[name] = captcha_token
                    else:
                        post_data[name] = value
            
            debug(f"Keeplinks: Submitting CAPTCHA solution")
            response = session.post(url, data=post_data, headers=headers, timeout=get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))
            
            if response.status_code != 200:
                info(f"Keeplinks: CAPTCHA POST failed with status {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check for error messages
            error_msg = soup.find(text=re.compile(r'wrong|invalid|incorrect', re.IGNORECASE))
            if error_msg:
                info(f"Keeplinks: CAPTCHA was rejected")
                return None
            
            # Step 6: Extract download links
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
            
        except requests.RequestException as e:
            info(f"Keeplinks: Request error - {e}")
            return None
        except Exception as e:
            info(f"Keeplinks: Unexpected error - {e}")
            return None

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
        
        session = requests.Session()
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
                info("ToLink: No CAPTCHA image found and no links available")
                return None
            
            captcha_url = captcha_img.get('src', '')
            if not captcha_url.startswith('http'):
                # Build absolute URL
                from urllib.parse import urljoin
                captcha_url = urljoin(url, captcha_url)
            
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
            if form_action and not form_action.startswith('http'):
                from urllib.parse import urljoin
                form_action = urljoin(url, form_action)
            submit_url = form_action if form_action else url
            
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
        
        # Patterns for valid download links
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

    def _solve_hide_cx(
        self,
        title: str,
        url: str,
        password: str,
        mirror: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Solve hide.cx links via API (no CAPTCHA needed)."""
        from kuasarr.downloads.linkcrypters.hide import get_hide_api_key
        
        api_key = get_hide_api_key(self.shared_state)
        if not api_key:
            info("hide.cx API Key not configured - skipping")
            return None
        
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

    def _mark_as_manual_required(self, package_id: str, title: str, reason: str, url: Optional[str] = None) -> None:
        """Flag a package as needing manual captcha solving (e.g. filecrypt PoW).

        Unlike _mark_as_failed, the package stays in the protected-DB (so the WebUI
        captcha page can pick it up) and is only removed from the dispatcher's job
        queue (so it is not retried automatically). A timestamp enables TTL cleanup.
        """
        try:
            db = self.shared_state.get_db("protected")
            current = None
            for pid, raw in (db.retrieve_all_titles() or []):
                if pid == package_id:
                    current = raw
                    break
            data = json.loads(current) if current else {}
            data["needs_manual"] = True
            data["handoff_url"] = url
            data["manual_timestamp"] = time.time()
            data["handoff_reason"] = reason
            db.update_store(package_id, json.dumps(data))
            send_discord_message(self.shared_state, title=title, case="captcha")
        except Exception as exc:
            debug(f"Error marking as manual_required: {exc}")
        push_jobs.remove_job(package_id)
        info(f"Package {title} needs manual solving (reason: {reason})")

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
