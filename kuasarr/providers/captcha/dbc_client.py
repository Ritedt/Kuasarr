# -*- coding: utf-8 -*-
"""DeathByCaptcha HTTP API client for Kuasarr.

This client communicates with the DeathByCaptcha API (http://api.dbcapi.me/api/).

API Documentation: https://deathbycaptcha.com/api
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import requests
from requests import RequestException

from kuasarr.providers.log import info, debug, error


# Affiliate link for when balance is empty
DBC_AFFILIATE_LINK = "https://deathbycaptcha.com?refid=1237432788a"

# API Base URL
DBC_API_BASE = "http://api.dbcapi.me/api"


class DBCError(RuntimeError):
    """Base exception for DeathByCaptcha errors."""


class DBCAccessDenied(DBCError):
    """Raised when credentials are rejected or user is banned."""


class DBCServiceOverload(DBCError):
    """Raised when the DBC service is overloaded."""


class DBCInsufficientCredits(DBCError):
    """Raised when the user has no credits left."""


class CaptchaStatus(str, Enum):
    PENDING = "pending"
    SOLVED = "solved"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class CaptchaResult:
    """Result of a captcha solve operation."""
    captcha_id: int
    text: str
    is_correct: bool
    status: CaptchaStatus
    
    @property
    def is_solved(self) -> bool:
        return self.status == CaptchaStatus.SOLVED and bool(self.text)


@dataclass
class AccountInfo:
    """DBC account information."""
    user_id: int
    balance: float  # in US cents
    rate: float
    is_banned: bool
    
    @property
    def balance_dollars(self) -> float:
        return self.balance / 100.0


@dataclass
class ServiceStatus:
    """DBC service status."""
    accuracy: float
    solved_in: float
    is_overloaded: bool


class DeathByCaptchaClient:
    """HTTP client for DeathByCaptcha API."""
    
    def __init__(
        self,
        authtoken: str = "",
        timeout: int = 120,
        max_retries: int = 3,
        retry_backoff: int = 5,
    ) -> None:
        """Initialize the DBC client.
        
        Args:
            authtoken: DBC authentication token
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_backoff: Seconds to wait between retries
        """
        self.authtoken = authtoken
        self.timeout = max(1, int(timeout))
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff = max(1, int(retry_backoff))
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Kuasarr-DBCClient/1.0"
        })
        self._last_balance: Optional[float] = None
    
    def _get_auth_data(self) -> Dict[str, str]:
        """Get authentication data for API requests."""
        return {"authtoken": self.authtoken}
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (without base URL)
            data: Form data to send
            files: Files to upload
            
        Returns:
            JSON response as dictionary
            
        Raises:
            DBCError: On API errors
        """
        url = f"{DBC_API_BASE}/{endpoint}" if endpoint else DBC_API_BASE
        last_exc: Optional[Exception] = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                debug(f"DBC {method.upper()} {url} (Versuch {attempt}/{self.max_retries})")
                
                response = self._session.request(
                    method.upper(),
                    url,
                    data=data,
                    files=files,
                    timeout=self.timeout,
                )
                
                # Handle HTTP status codes
                if response.status_code == 403:
                    raise DBCAccessDenied("DBC credentials rejected or account banned")
                elif response.status_code == 400:
                    raise DBCError(f"Bad request: {response.text}")
                elif response.status_code == 503:
                    raise DBCServiceOverload("DBC service is overloaded")
                elif response.status_code == 500:
                    raise DBCError(f"DBC server error: {response.text}")
                
                response.raise_for_status()
                
                # Parse response
                if response.headers.get("Content-Type", "").startswith("application/json"):
                    result = response.json()
                else:
                    # URL-encoded response - parse manually
                    result = dict(x.split("=") for x in response.text.split("&") if "=" in x)
                
                # Check for error in response
                if result.get("status") == 255:
                    error_msg = result.get("error", "Unknown error")
                    raise DBCError(f"DBC API error: {error_msg}")
                
                return result
                
            except DBCAccessDenied:
                raise  # Don't retry auth errors
            except DBCServiceOverload as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    info(f"DBC service overloaded (attempt {attempt}/{self.max_retries}), waiting {self.retry_backoff}s...")
                    time.sleep(self.retry_backoff * attempt)
                    continue
                raise
            except RequestException as exc:
                last_exc = exc
                info(f"DBC {method.upper()} {url} failed ({attempt}/{self.max_retries}): {exc}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff * attempt)
                    continue
        
        raise DBCError(f"DBC request failed after {self.max_retries} attempts") from last_exc
    
    def get_balance(self) -> float:
        """Get account balance in US cents.
        
        Returns:
            Balance in US cents
            
        Raises:
            DBCInsufficientCredits: If balance is 0
        """
        data = self._get_auth_data()
        result = self._request("POST", "", data=data)
        
        balance = float(result.get("balance", 0))
        is_banned = result.get("is_banned", False)
        
        if is_banned or str(is_banned).lower() == "true" or is_banned == 1:
            raise DBCAccessDenied("DBC account is banned")
        
        self._last_balance = balance
        info(f"DBC Balance: {balance:.2f} cents (${balance/100:.4f})")
        
        if balance <= 0:
            info(f"⚠️ DBC credits exhausted! Top up at: {DBC_AFFILIATE_LINK}")
            raise DBCInsufficientCredits(f"No DBC credits left. Top up at: {DBC_AFFILIATE_LINK}")
        
        return balance
    
    def get_account_info(self) -> AccountInfo:
        """Get full account information.
        
        Returns:
            AccountInfo object with balance, rate, etc.
        """
        data = self._get_auth_data()
        result = self._request("POST", "", data=data)
        
        return AccountInfo(
            user_id=int(result.get("user", 0)),
            balance=float(result.get("balance", 0)),
            rate=float(result.get("rate", 0)),
            is_banned=result.get("is_banned", False) in (True, 1, "1", "true"),
        )
    
    def get_service_status(self) -> ServiceStatus:
        """Get DBC service status.
        
        Returns:
            ServiceStatus with accuracy, solve time, overload status
        """
        result = self._request("GET", "status")
        
        return ServiceStatus(
            accuracy=float(result.get("todays_accuracy", 0)),
            solved_in=float(result.get("solved_in", 0)),
            is_overloaded=result.get("is_service_overloaded", False) in (True, 1, "1", "true"),
        )
    
    def upload_captcha(
        self,
        image_data: bytes,
        timeout: Optional[int] = None,
    ) -> CaptchaResult:
        """Upload a captcha image for solving.
        
        Args:
            image_data: Raw image bytes (JPG, PNG, GIF, BMP)
            timeout: Optional custom timeout
            
        Returns:
            CaptchaResult with captcha_id (may not be solved yet)
        """
        # Log balance before cost-incurring operation
        try:
            self.get_balance()
        except DBCInsufficientCredits:
            raise
        except Exception as e:
            debug(f"Could not fetch balance before upload: {e}")
        
        data = self._get_auth_data()
        
        # Encode image as base64
        b64_image = "base64:" + base64.b64encode(image_data).decode("utf-8")
        data["captchafile"] = b64_image
        
        debug(f"DBC: Uploading image captcha ({len(image_data)} bytes)")
        result = self._request("POST", "captcha", data=data)
        debug(f"DBC: Upload response: captcha_id={result.get('captcha')}, text={result.get('text', '')[:50]}")
        
        captcha_id = int(result.get("captcha", 0))
        text = result.get("text", "")
        is_correct = result.get("is_correct", 1) in (1, True, "1", "true")
        
        status = CaptchaStatus.SOLVED if text else CaptchaStatus.PENDING
        
        return CaptchaResult(
            captcha_id=captcha_id,
            text=text,
            is_correct=is_correct,
            status=status,
        )
    
    def get_captcha_result(self, captcha_id: int) -> CaptchaResult:
        """Poll for captcha result.
        
        Args:
            captcha_id: ID of the uploaded captcha
            
        Returns:
            CaptchaResult with current status
        """
        result = self._request("GET", f"captcha/{captcha_id}")
        
        text = result.get("text", "")
        is_correct = result.get("is_correct", 1) in (1, True, "1", "true")
        
        if not text:
            status = CaptchaStatus.PENDING
        elif not is_correct:
            status = CaptchaStatus.FAILED
        else:
            status = CaptchaStatus.SOLVED
        
        return CaptchaResult(
            captcha_id=captcha_id,
            text=text,
            is_correct=is_correct,
            status=status,
        )
    
    def solve_captcha(
        self,
        image_data: bytes,
        poll_interval: float = 3.0,
        max_wait: float = 120.0,
    ) -> CaptchaResult:
        """Upload and wait for captcha solution.
        
        Args:
            image_data: Raw image bytes
            poll_interval: Seconds between status polls
            max_wait: Maximum seconds to wait for solution
            
        Returns:
            CaptchaResult with solution or timeout status
        """
        # Upload captcha
        result = self.upload_captcha(image_data)
        
        if result.is_solved:
            info(f"CAPTCHA {result.captcha_id} solved immediately: {result.text}")
            return result
        
        # Poll for result
        start = time.time()
        while time.time() - start < max_wait:
            time.sleep(poll_interval)
            
            result = self.get_captcha_result(result.captcha_id)
            
            if result.is_solved:
                info(f"CAPTCHA {result.captcha_id} solved: {result.text}")
                return result
            
            if result.status == CaptchaStatus.FAILED:
                info(f"CAPTCHA {result.captcha_id} failed")
                return result
            
            debug(f"CAPTCHA {result.captcha_id} not yet solved, waiting...")
        
        # Timeout
        info(f"CAPTCHA {result.captcha_id} timeout after {max_wait}s")
        return CaptchaResult(
            captcha_id=result.captcha_id,
            text="",
            is_correct=False,
            status=CaptchaStatus.TIMEOUT,
        )
    
    def report_incorrect(self, captcha_id: int) -> bool:
        """Report an incorrectly solved captcha for refund.
        
        Args:
            captcha_id: ID of the incorrectly solved captcha
            
        Returns:
            True if report was accepted
        """
        data = self._get_auth_data()
        
        try:
            result = self._request("POST", f"captcha/{captcha_id}/report", data=data)
            is_correct = result.get("is_correct", 1)
            success = is_correct in (0, False, "0", "false")
            if success:
                info(f"CAPTCHA {captcha_id} reported as incorrect, refund issued")
            return success
        except DBCError as e:
            info(f"Error reporting CAPTCHA {captcha_id}: {e}")
            return False
    
    def solve_recaptcha_v2(
        self,
        site_key: str,
        page_url: str,
        proxy: str = "",
        proxy_type: str = "",
        poll_interval: float = 5.0,
        max_wait: float = 180.0,
    ) -> CaptchaResult:
        """Solve a reCAPTCHA v2 challenge.
        
        Args:
            site_key: The reCAPTCHA site key (data-sitekey)
            page_url: URL of the page with the captcha
            proxy: Optional proxy in format ip:port or user:pass@ip:port
            proxy_type: Proxy type (HTTP, SOCKS4, SOCKS5)
            poll_interval: Seconds between status polls
            max_wait: Maximum seconds to wait
            
        Returns:
            CaptchaResult with g-recaptcha-response token
        """
        # Log balance before cost-incurring operation
        try:
            self.get_balance()
        except DBCInsufficientCredits:
            raise
        except Exception as e:
            debug(f"Could not fetch balance before reCAPTCHA: {e}")
        
        data = self._get_auth_data()
        
        token_params = {
            "googlekey": site_key,
            "pageurl": page_url,
        }
        if proxy:
            token_params["proxy"] = proxy
            token_params["proxytype"] = proxy_type or "HTTP"
        
        data["type"] = "4"  # reCAPTCHA v2 type
        data["token_params"] = json.dumps(token_params)
        
        debug(f"DBC: Solving reCAPTCHA v2 for {page_url} (sitekey={site_key[:20]}...)")
        result = self._request("POST", "captcha", data=data)
        debug(f"DBC: reCAPTCHA response: captcha_id={result.get('captcha')}")
        
        captcha_id = int(result.get("captcha", 0))
        text = result.get("text", "")
        
        if text:
            info(f"reCAPTCHA {captcha_id} solved immediately")
            return CaptchaResult(
                captcha_id=captcha_id,
                text=text,
                is_correct=True,
                status=CaptchaStatus.SOLVED,
            )
        
        poll_intervals = [1, 1, 2, 3, 2, 2, 3, 2, 2]  
        start = time.time()
        poll_idx = 0
        
        while time.time() - start < max_wait:
            # Wait before polling
            if poll_idx < len(poll_intervals):
                wait_time = poll_intervals[poll_idx]
                poll_idx += 1
            else:
                wait_time = poll_interval
            
            time.sleep(wait_time)
            
            poll_result = self.get_captcha_result(captcha_id)
            
            if poll_result.is_solved:
                info(f"reCAPTCHA {captcha_id} solved")
                return poll_result
            
            if poll_result.status == CaptchaStatus.FAILED:
                info(f"reCAPTCHA {captcha_id} failed")
                return poll_result
            
            debug(f"reCAPTCHA {captcha_id} not yet solved ({int(time.time() - start)}s elapsed)...")
        
        info(f"reCAPTCHA {captcha_id} timeout after {max_wait}s")
        return CaptchaResult(
            captcha_id=captcha_id,
            text="",
            is_correct=False,
            status=CaptchaStatus.TIMEOUT,
        )
    
    def solve_cutcaptcha(
        self,
        api_key: str,
        page_url: str,
        misery_key: str = "",
        proxy: str = "",
        proxy_type: str = "",
        poll_interval: float = 2.0,
        max_wait: float = 180.0,
    ) -> CaptchaResult:
        """Solve a CutCaptcha challenge using official DBC library.
        
        The HTTP API doesn't support CutCaptcha (returns 501).
        Must use the official deathbycaptcha-official package.
        
        Args:
            api_key: CutCaptcha API key (e.g. 'SAs61IAI')
            page_url: URL of the page with the captcha
            misery_key: CutCaptcha misery key (32 char hex)
            proxy: Optional proxy
            proxy_type: Proxy type (HTTP, SOCKS4, SOCKS5)
            poll_interval: Seconds between status polls
            max_wait: Maximum seconds to wait
            
        Returns:
            CaptchaResult with solution token
        """
        try:
            import deathbycaptcha
        except ImportError:
            error("deathbycaptcha-official package not installed! Run: pip install deathbycaptcha-official")
            return CaptchaResult(
                captcha_id=0,
                text="",
                is_correct=False,
                status=CaptchaStatus.FAILED,
            )
        
        info(f"Solving CutCaptcha for {page_url} (apikey={api_key})")
        debug(f"DBC: Using official SocketClient, miserykey={misery_key[:10] if misery_key else 'none'}...")
        debug(f"DBC: Credentials - authtoken={bool(self.authtoken)}")
        
        try:
            # Create official DBC SocketClient (required for type=19)
            # SocketClient signature: SocketClient(username, password, authtoken)
            # Use authtoken exclusively
            debug(f"DBC: Creating SocketClient with authtoken")
            client = deathbycaptcha.SocketClient("", "", self.authtoken)
            
            # Log balance
            balance = client.get_balance()
            info(f"DBC Balance: {balance} cents (${balance/100:.2f})")
            
            if balance <= 0:
                raise DBCInsufficientCredits(f"No credits left! Top up at: {DBC_AFFILIATE_LINK}")
            
            # Build CutCaptcha params
            captcha_params = {
                'proxy': proxy or '',
                'proxytype': proxy_type or '',
                'apikey': api_key,
                'miserykey': misery_key or '',
                'pageurl': page_url
            }
            json_params = json.dumps(captcha_params)
            
            debug(f"DBC: Sending CutCaptcha request with type=19, params={captcha_params}")
            
            # Use official client's decode method
            captcha = client.decode(type=19, cutcaptcha_params=json_params)
            
            if captcha and captcha.get("captcha") and captcha.get("text"):
                captcha_id = captcha["captcha"]
                text = captcha["text"]
                info(f"CutCaptcha {captcha_id} solved: {text[:50]}...")
                return CaptchaResult(
                    captcha_id=int(captcha_id),
                    text=text,
                    is_correct=True,
                    status=CaptchaStatus.SOLVED,
                )
            else:
                # Report failed captcha
                if captcha and captcha.get("captcha"):
                    try:
                        client.report(captcha["captcha"])
                    except Exception:
                        pass
                info("CutCaptcha solution failed - no text returned")
                return CaptchaResult(
                    captcha_id=int(captcha.get("captcha", 0)) if captcha else 0,
                    text="",
                    is_correct=False,
                    status=CaptchaStatus.FAILED,
                )
                
        except deathbycaptcha.AccessDeniedException:
            error("DBC Access Denied - check credentials")
            raise DBCAccessDenied("Access to DBC API denied - check credentials")
        except DBCInsufficientCredits:
            raise
        except Exception as e:
            error(f"CutCaptcha error: {e}")
            return CaptchaResult(
                captcha_id=0,
                text="",
                is_correct=False,
                status=CaptchaStatus.FAILED,
            )
    
    def solve_coordinates_captcha(
        self,
        image_data: bytes,
        poll_interval: float = 3.0,
        max_wait: float = 60.0,
    ) -> Optional[Tuple[int, int]]:
        """Solve a coordinates/click captcha (like Circle-Captcha).
        
        DBC returns coordinates in format "x,y" for where to click.
        
        Args:
            image_data: Raw image bytes of the captcha
            poll_interval: Seconds between status polls
            max_wait: Maximum seconds to wait
            
        Returns:
            Tuple of (x, y) coordinates or None if failed
        """
        result = self.solve_captcha(image_data, poll_interval, max_wait)
        
        if not result.is_solved or not result.text:
            return None
        
        # DBC returns coordinates as "x,y" or "x;y"
        text = result.text.strip()
        
        # Try different separators
        for sep in [",", ";", " ", ":"]:
            if sep in text:
                parts = text.split(sep)
                if len(parts) >= 2:
                    try:
                        x = int(parts[0].strip())
                        y = int(parts[1].strip())
                        info(f"Circle-Captcha solved: x={x}, y={y}")
                        return (x, y)
                    except ValueError:
                        continue
        
        # If no separator found, try to parse as single coordinate pair
        try:
            # Sometimes returned as just numbers
            coords = re.findall(r'\d+', text)
            if len(coords) >= 2:
                x = int(coords[0])
                y = int(coords[1])
                info(f"Circle-Captcha solved: x={x}, y={y}")
                return (x, y)
        except (ValueError, IndexError):
            pass
        
        info(f"Circle-Captcha coordinates not parsable: {text}")
        return None


def create_dbc_client(shared_state) -> Optional[DeathByCaptchaClient]:
    """Factory function: Create a DeathByCaptchaClient from shared_state.
    
    Args:
        shared_state: Kuasarr shared state module
        
    Returns:
        Configured DeathByCaptchaClient or None if not configured
    """
    dbc_config = shared_state.values.get("dbc_config", {})
    authtoken = dbc_config.get("authtoken", "")
    
    if not authtoken:
        return None
    
    timeout = int(dbc_config.get("timeout", 120))
    max_retries = int(dbc_config.get("max_retries", 3))
    retry_backoff = int(dbc_config.get("retry_backoff", 5))
    
    return DeathByCaptchaClient(
        authtoken=authtoken,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


__all__ = [
    "DeathByCaptchaClient",
    "DBCError",
    "DBCAccessDenied",
    "DBCServiceOverload",
    "DBCInsufficientCredits",
    "CaptchaResult",
    "CaptchaStatus",
    "AccountInfo",
    "ServiceStatus",
    "create_dbc_client",
    "DBC_AFFILIATE_LINK",
]
