# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""CAPTCHA module - routes and helpers for CAPTCHA handling."""

from .main_routes import setup_main_routes
from .provider_routes import setup_provider_routes
from .proxy_routes import setup_proxy_routes
from .submission_routes import setup_submission_routes


def setup_captcha_routes(app):
    """Register all CAPTCHA-related routes."""
    setup_main_routes(app)
    setup_provider_routes(app)
    setup_proxy_routes(app)
    setup_submission_routes(app)


__all__ = ['setup_captcha_routes']
