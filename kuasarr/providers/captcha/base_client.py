# -*- coding: utf-8 -*-
"""Abstract base class for captcha solving services.

This module provides a unified interface for different captcha solving
services like DeathByCaptcha and 2Captcha.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class CaptchaStatus(str, Enum):
    """Status of a captcha solving operation."""
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
        """Check if captcha was successfully solved."""
        return self.status == CaptchaStatus.SOLVED and bool(self.text)


@dataclass
class AccountInfo:
    """Captcha service account information."""
    user_id: int
    balance: float  # in US cents
    rate: float
    is_banned: bool
    
    @property
    def balance_dollars(self) -> float:
        """Get balance in dollars."""
        return self.balance / 100.0


class CaptchaClientError(RuntimeError):
    """Base exception for captcha client errors."""


class CaptchaAccessDenied(CaptchaClientError):
    """Raised when credentials are rejected or user is banned."""


class CaptchaServiceOverload(CaptchaClientError):
    """Raised when the captcha service is overloaded."""


class CaptchaInsufficientCredits(CaptchaClientError):
    """Raised when the user has no credits left."""


class BaseCaptchaClient(ABC):
    """Abstract base class for captcha solving services.
    
    This class defines the interface that all captcha solving clients
    must implement. It allows for easy switching between different
    services like DeathByCaptcha and 2Captcha.
    """
    
    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the name of the captcha service."""
        pass

    @abstractmethod
    def get_balance(self) -> float:
        """Get account balance in US cents."""
        pass

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """Get full account information."""
        pass

    @abstractmethod
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
        """Solve a CutCaptcha challenge."""
        pass

    @abstractmethod
    def solve_recaptcha_v2(
        self,
        site_key: str,
        page_url: str,
        proxy: str = "",
        proxy_type: str = "",
        poll_interval: float = 5.0,
        max_wait: float = 180.0,
    ) -> CaptchaResult:
        """Solve a reCAPTCHA v2 challenge."""
        pass

    @abstractmethod
    def solve_captcha(
        self,
        image_data: bytes,
        poll_interval: float = 3.0,
        max_wait: float = 120.0,
    ) -> CaptchaResult:
        """Upload and wait for image captcha solution."""
        pass

    @abstractmethod
    def solve_coordinates_captcha(
        self,
        image_data: bytes,
        poll_interval: float = 3.0,
        max_wait: float = 60.0,
    ) -> Optional[Tuple[int, int]]:
        """Solve a coordinates/click captcha (like Circle-Captcha)."""
        pass

    @abstractmethod
    def report_incorrect(self, captcha_id: int) -> bool:
        """Report an incorrectly solved captcha for refund."""
        pass


__all__ = [
    "BaseCaptchaClient",
    "CaptchaResult",
    "CaptchaStatus",
    "AccountInfo",
    "CaptchaClientError",
    "CaptchaAccessDenied",
    "CaptchaServiceOverload",
    "CaptchaInsufficientCredits",
]
