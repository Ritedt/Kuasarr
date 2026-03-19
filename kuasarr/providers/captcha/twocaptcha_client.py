# -*- coding: utf-8 -*-
"""2Captcha API client for Kuasarr.

This client communicates with the 2Captcha API (https://api.2captcha.com).
2Captcha is 50% cheaper than DeathByCaptcha for CutCaptcha solving.

API Documentation: https://2captcha.com/api-docs
"""

from __future__ import annotations

import base64
import re
import time
from typing import Optional, Tuple

import requests
from requests import RequestException

from kuasarr.providers.log import info, debug, error
from kuasarr.providers.captcha.base_client import (
    BaseCaptchaClient,
    CaptchaResult,
    CaptchaStatus,
    AccountInfo,
    CaptchaClientError,
    CaptchaAccessDenied,
    CaptchaServiceOverload,
    CaptchaInsufficientCredits,
)


TWOCAPTCHA_API_BASE = "https://api.2captcha.com"
TWOCAPTCHA_AFFILIATE_LINK = "https://2captcha.com/?from=26376359"


class TwoCaptchaError(CaptchaClientError):
    """Base exception for 2Captcha errors."""


class TwoCaptchaClient(BaseCaptchaClient):
    """HTTP client for 2Captcha API.
    
    2Captcha pricing (as of 2025):
    - CutCaptcha: $1.45/1000 (vs. $2.89 at DBC - 50% cheaper!)
    - reCAPTCHA v2: $2.99/1000
    - Image Captcha: $1.00/1000
    """
    
    def __init__(
        self,
        api_key: str,
        timeout: int = 120,
        max_retries: int = 3,
        retry_backoff: int = 5,
    ) -> None:
        """Initialize the 2Captcha client.
        
        Args:
            api_key: 2Captcha API key
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_backoff: Seconds to wait between retries
        """
        self.api_key = api_key
        self.timeout = max(1, int(timeout))
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff = max(1, int(retry_backoff))
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Kuasarr-2CaptchaClient/1.0"
        })
        self._last_balance: Optional[float] = None
    
    @property
    def service_name(self) -> str:
        """Return the name of the captcha service."""
        return "2Captcha"
    
    def _request(
        self,
        endpoint: str,
        payload: dict,
    ) -> dict:
        """Execute an HTTP request with retry logic.
        
        Args:
            endpoint: API endpoint (e.g., "createTask", "getTaskResult")
            payload: JSON payload to send
            
        Returns:
            JSON response as dictionary
            
        Raises:
            TwoCaptchaError: On API errors
        """
        url = f"{TWOCAPTCHA_API_BASE}/{endpoint}"
        payload["clientKey"] = self.api_key
        last_exc: Optional[Exception] = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                debug(f"2Captcha POST {endpoint} (Versuch {attempt}/{self.max_retries})")
                
                response = self._session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )
                
                result = response.json()
                
                error_id = result.get("errorId", 0)
                if error_id:
                    error_code = result.get("errorCode", "")
                    error_desc = result.get("errorDescription", "Unknown error")
                    
                    if error_code in ("ERROR_KEY_DOES_NOT_EXIST", "ERROR_WRONG_USER_KEY"):
                        raise CaptchaAccessDenied(f"2Captcha: {error_desc}")
                    elif error_code == "ERROR_ZERO_BALANCE":
                        raise CaptchaInsufficientCredits(f"2Captcha: {error_desc}")
                    elif error_code in ("ERROR_NO_SLOT_AVAILABLE", "ERROR_TOO_MUCH_REQUESTS"):
                        raise CaptchaServiceOverload(f"2Captcha: {error_desc}")
                    else:
                        raise TwoCaptchaError(f"2Captcha API error: {error_code} - {error_desc}")
                
                return result
                
            except CaptchaAccessDenied:
                raise
            except CaptchaInsufficientCredits:
                raise
            except CaptchaServiceOverload as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    info(f"2Captcha service overloaded (attempt {attempt}/{self.max_retries}), waiting {self.retry_backoff}s...")
                    time.sleep(self.retry_backoff * attempt)
                    continue
                raise
            except RequestException as exc:
                last_exc = exc
                info(f"2Captcha request failed ({attempt}/{self.max_retries}): {exc}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff * attempt)
                    continue
        
        raise TwoCaptchaError(f"2Captcha request failed after {self.max_retries} attempts") from last_exc
    
    def get_balance(self) -> float:
        """Get account balance in US cents.
        
        Returns:
            Balance in US cents
            
        Raises:
            CaptchaInsufficientCredits: If balance is 0
        """
        result = self._request("getBalance", {})
        
        balance_dollars = float(result.get("balance", 0))
        balance_cents = balance_dollars * 100
        
        self._last_balance = balance_cents
        info(f"2Captcha Balance: ${balance_dollars:.4f} ({balance_cents:.2f} cents)")
        
        if balance_cents <= 0:
            info(f"⚠️ 2Captcha credits exhausted! Top up at: {TWOCAPTCHA_AFFILIATE_LINK}")
            raise CaptchaInsufficientCredits(f"No 2Captcha credits left. Top up at: {TWOCAPTCHA_AFFILIATE_LINK}")
        
        return balance_cents
    
    def get_account_info(self) -> AccountInfo:
        """Get full account information.
        
        Returns:
            AccountInfo object with balance, rate, etc.
        """
        result = self._request("getBalance", {})
        
        balance_dollars = float(result.get("balance", 0))
        
        return AccountInfo(
            user_id=0,
            balance=balance_dollars * 100,
            rate=0,
            is_banned=False,
        )
    
    def _create_task(self, task: dict) -> int:
        """Create a captcha solving task.
        
        Args:
            task: Task definition dictionary
            
        Returns:
            Task ID
        """
        result = self._request("createTask", {"task": task})
        task_id = int(result.get("taskId", 0))
        debug(f"2Captcha: Created task {task_id}")
        return task_id
    
    def _get_task_result(
        self,
        task_id: int,
        poll_interval: float = 5.0,
        max_wait: float = 180.0,
    ) -> CaptchaResult:
        """Poll for task result.
        
        Args:
            task_id: Task ID to poll
            poll_interval: Seconds between polls
            max_wait: Maximum seconds to wait
            
        Returns:
            CaptchaResult with solution or failure status
        """
        start = time.time()
        
        while time.time() - start < max_wait:
            try:
                result = self._request("getTaskResult", {"taskId": task_id})
                
                status = result.get("status", "")
                
                if status == "ready":
                    solution = result.get("solution", {})
                    token = (
                        solution.get("token", "") or 
                        solution.get("text", "") or
                        solution.get("gRecaptchaResponse", "")
                    )
                    
                    if token:
                        info(f"2Captcha task {task_id} solved")
                        return CaptchaResult(
                            captcha_id=task_id,
                            text=token,
                            is_correct=True,
                            status=CaptchaStatus.SOLVED,
                        )
                    else:
                        info(f"2Captcha task {task_id} ready but no token")
                        return CaptchaResult(
                            captcha_id=task_id,
                            text="",
                            is_correct=False,
                            status=CaptchaStatus.FAILED,
                        )
                
                elif status == "processing":
                    debug(f"2Captcha task {task_id} still processing ({int(time.time() - start)}s elapsed)...")
                    time.sleep(poll_interval)
                    continue
                
                else:
                    info(f"2Captcha task {task_id} unknown status: {status}")
                    return CaptchaResult(
                        captcha_id=task_id,
                        text="",
                        is_correct=False,
                        status=CaptchaStatus.FAILED,
                    )
                    
            except TwoCaptchaError as e:
                info(f"2Captcha polling error: {e}")
                time.sleep(poll_interval)
                continue
        
        info(f"2Captcha task {task_id} timeout after {max_wait}s")
        return CaptchaResult(
            captcha_id=task_id,
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
        try:
            self.get_balance()
        except CaptchaInsufficientCredits:
            raise
        except Exception as e:
            debug(f"Could not fetch balance before CutCaptcha: {e}")
        
        info(f"2Captcha: Solving CutCaptcha for {page_url} (apikey={api_key})")
        debug(f"2Captcha: miserykey={misery_key[:10] if misery_key else 'none'}...")
        
        task = {
            "type": "CutCaptchaTaskProxyless" if not proxy else "CutCaptchaTask",
            "websiteURL": page_url,
            "apiKey": api_key,
            "miseryKey": misery_key or "",
        }
        
        if proxy:
            task["proxyType"] = proxy_type or "http"
            task["proxyAddress"] = proxy.split(":")[0] if ":" in proxy else proxy
            if ":" in proxy:
                task["proxyPort"] = int(proxy.split(":")[1])
        
        try:
            task_id = self._create_task(task)
            return self._get_task_result(task_id, poll_interval, max_wait)
        except Exception as e:
            error(f"2Captcha CutCaptcha error: {e}")
            return CaptchaResult(
                captcha_id=0,
                text="",
                is_correct=False,
                status=CaptchaStatus.FAILED,
            )
    
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
        try:
            self.get_balance()
        except CaptchaInsufficientCredits:
            raise
        except Exception as e:
            debug(f"Could not fetch balance before reCAPTCHA: {e}")
        
        info(f"2Captcha: Solving reCAPTCHA v2 for {page_url} (sitekey={site_key[:20]}...)")
        
        task = {
            "type": "RecaptchaV2TaskProxyless" if not proxy else "RecaptchaV2Task",
            "websiteURL": page_url,
            "websiteKey": site_key,
        }
        
        if proxy:
            task["proxyType"] = proxy_type or "http"
            task["proxyAddress"] = proxy.split(":")[0] if ":" in proxy else proxy
            if ":" in proxy:
                task["proxyPort"] = int(proxy.split(":")[1])
        
        try:
            task_id = self._create_task(task)
            return self._get_task_result(task_id, poll_interval, max_wait)
        except Exception as e:
            error(f"2Captcha reCAPTCHA error: {e}")
            return CaptchaResult(
                captcha_id=0,
                text="",
                is_correct=False,
                status=CaptchaStatus.FAILED,
            )
    
    def solve_captcha(
        self,
        image_data: bytes,
        poll_interval: float = 3.0,
        max_wait: float = 120.0,
    ) -> CaptchaResult:
        """Upload and wait for image captcha solution.
        
        Args:
            image_data: Raw image bytes (JPG, PNG, GIF, BMP)
            poll_interval: Seconds between status polls
            max_wait: Maximum seconds to wait for solution
            
        Returns:
            CaptchaResult with solution text
        """
        try:
            self.get_balance()
        except CaptchaInsufficientCredits:
            raise
        except Exception as e:
            debug(f"Could not fetch balance before image captcha: {e}")
        
        info(f"2Captcha: Solving image captcha ({len(image_data)} bytes)")
        
        b64_image = base64.b64encode(image_data).decode("utf-8")
        
        task = {
            "type": "ImageToTextTask",
            "body": b64_image,
        }
        
        try:
            task_id = self._create_task(task)
            return self._get_task_result(task_id, poll_interval, max_wait)
        except Exception as e:
            error(f"2Captcha image captcha error: {e}")
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
        
        Args:
            image_data: Raw image bytes of the captcha
            poll_interval: Seconds between status polls
            max_wait: Maximum seconds to wait
            
        Returns:
            Tuple of (x, y) coordinates or None if failed
        """
        try:
            self.get_balance()
        except CaptchaInsufficientCredits:
            raise
        except Exception as e:
            debug(f"Could not fetch balance before coordinates captcha: {e}")
        
        info(f"2Captcha: Solving coordinates captcha ({len(image_data)} bytes)")
        
        b64_image = base64.b64encode(image_data).decode("utf-8")
        
        task = {
            "type": "ImageToCoordinatesTask",
            "body": b64_image,
            "mode": "points",
        }
        
        try:
            task_id = self._create_task(task)
            result = self._get_task_result(task_id, poll_interval, max_wait)
            
            if not result.is_solved or not result.text:
                return None
            
            text = result.text.strip()
            
            for sep in [",", ";", " ", ":"]:
                if sep in text:
                    parts = text.split(sep)
                    if len(parts) >= 2:
                        try:
                            x = int(parts[0].strip())
                            y = int(parts[1].strip())
                            info(f"2Captcha: Coordinates solved: x={x}, y={y}")
                            return (x, y)
                        except ValueError:
                            continue
            
            coords = re.findall(r'\d+', text)
            if len(coords) >= 2:
                x = int(coords[0])
                y = int(coords[1])
                info(f"2Captcha: Coordinates solved: x={x}, y={y}")
                return (x, y)
            
            info(f"2Captcha: Coordinates not parsable: {text}")
            return None
            
        except Exception as e:
            error(f"2Captcha coordinates captcha error: {e}")
            return None
    
    def report_incorrect(self, captcha_id: int) -> bool:
        """Report an incorrectly solved captcha for refund.
        
        Args:
            captcha_id: ID of the incorrectly solved captcha
            
        Returns:
            True if report was accepted
        """
        try:
            result = self._request("reportIncorrect", {"taskId": captcha_id})
            status = result.get("status", "")
            success = status == "success"
            if success:
                info(f"2Captcha: Task {captcha_id} reported as incorrect, refund issued")
            return success
        except TwoCaptchaError as e:
            info(f"2Captcha: Error reporting task {captcha_id}: {e}")
            return False


def create_twocaptcha_client(shared_state) -> Optional[TwoCaptchaClient]:
    """Factory function: Create a TwoCaptchaClient from shared_state.
    
    Args:
        shared_state: Kuasarr shared state module
        
    Returns:
        Configured TwoCaptchaClient or None if not configured
    """
    from kuasarr.storage.config import Config
    
    captcha_config = Config('Captcha')
    api_key = captcha_config.get('twocaptcha_api_key')
    
    if not api_key:
        return None
    
    timeout = int(captcha_config.get('timeout') or 120)
    max_retries = int(captcha_config.get('max_retries') or 3)
    retry_backoff = int(captcha_config.get('retry_backoff') or 5)
    
    return TwoCaptchaClient(
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


__all__ = [
    "TwoCaptchaClient",
    "TwoCaptchaError",
    "create_twocaptcha_client",
    "TWOCAPTCHA_AFFILIATE_LINK",
]
