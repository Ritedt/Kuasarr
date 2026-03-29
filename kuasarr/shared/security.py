# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Security utilities for credential masking and sanitization.

This module provides functions to mask sensitive data like passwords,
tokens, and API keys in logs and debug output.
"""

import re
from typing import Optional


def mask_sensitive_data(value: str, visible_start: int = 1, visible_end: int = 1) -> str:
    """
    Mask sensitive data by replacing middle characters with asterisks.

    Args:
        value: The sensitive value to mask
        visible_start: Number of characters to show at the start
        visible_end: Number of characters to show at the end

    Returns:
        Masked string like 'a*******f' or '***EMPTY***' for empty strings

    Examples:
        >>> mask_sensitive_data("password123")
        'p*********3'
        >>> mask_sensitive_data("abc")
        'a*c'
        >>> mask_sensitive_data("ab")
        '**'
    """
    if not value:
        return "***EMPTY***"

    if len(value) <= visible_start + visible_end:
        return "*" * len(value)

    masked_length = len(value) - visible_start - visible_end
    return value[:visible_start] + "*" * masked_length + value[-visible_end:]


def mask_url_credentials(url: str) -> str:
    """
    Mask credentials in URLs.

    Args:
        url: URL potentially containing credentials

    Returns:
        URL with credentials masked

    Examples:
        >>> mask_url_credentials("http://user:pass@host.com/path")
        'http://*CREDENTIALS*@host.com/path'
        >>> mask_url_credentials("https://api.key@service.com")
        'https://*CREDENTIALS*@service.com'
    """
    if not url:
        return url

    # Pattern for user:pass@host or apikey@host
    pattern = r"(https?://)[^@]+(@)"
    return re.sub(pattern, r"\1*CREDENTIALS*\2", url)


def mask_config_value(key: str, value: str) -> str:
    """
    Mask a config value based on the key name.

    Automatically detects sensitive keys like password, token, api_key, etc.

    Args:
        key: The configuration key name
        value: The configuration value

    Returns:
        Masked value if key indicates sensitive data, original value otherwise
    """
    sensitive_patterns = [
        r"password",
        r"pass",
        r"token",
        r"api_key",
        r"apikey",
        r"secret",
        r"auth",
        r"credential",
        r"key",
    ]

    key_lower = key.lower()
    is_sensitive = any(re.search(pattern, key_lower) for pattern in sensitive_patterns)

    if is_sensitive and value:
        return mask_sensitive_data(value)

    return value


def mask_dict_values(data: dict, mask_keys: Optional[list] = None) -> dict:
    """
    Create a copy of a dict with sensitive values masked.

    Args:
        data: Dictionary potentially containing sensitive values
        mask_keys: List of keys to mask (defaults to common sensitive keys)

    Returns:
        New dict with masked values
    """
    if mask_keys is None:
        mask_keys = [
            "password", "pass", "token", "api_key", "apikey",
            "secret", "auth", "credential", "key", "sessiontoken"
        ]

    result = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(mask_key in key_lower for mask_key in mask_keys):
            result[key] = mask_sensitive_data(str(value)) if value else value
        elif isinstance(value, dict):
            result[key] = mask_dict_values(value, mask_keys)
        else:
            result[key] = value

    return result


def sanitize_log_message(message: str) -> str:
    """
    Sanitize a log message by masking potential credentials.

    Args:
        message: Log message that may contain sensitive data

    Returns:
        Sanitized message
    """
    if not message:
        return message

    # Mask URLs with credentials
    message = mask_url_credentials(message)

    # Mask common credential patterns
    patterns = [
        # JSON patterns
        (r'"password"\s*:\s*"([^"]*)"', '"password":"***MASKED***"'),
        (r'"token"\s*:\s*"([^"]*)"', '"token":"***MASKED***"'),
        (r'"api_key"\s*:\s*"([^"]*)"', '"api_key":"***MASKED***"'),
        # URL param patterns
        (r'(password=)([^&\s]+)', r'\1***MASKED***'),
        (r'(token=)([^&\s]+)', r'\1***MASKED***'),
        (r'(api_key=)([^&\s]+)', r'\1***MASKED***'),
    ]

    for pattern, replacement in patterns:
        message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)

    return message
