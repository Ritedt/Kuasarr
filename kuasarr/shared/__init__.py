# -*- coding: utf-8 -*-
"""
Security utilities for sensitive data masking.

Provides functions to mask credentials, tokens, and other sensitive
data in logs and error messages.
"""

from urllib.parse import urlparse, urlunparse


def mask_sensitive_data(value):
    """
    Mask sensitive data for logging purposes.

    Short strings (< 3 chars): returned unchanged
    Medium strings (3-20 chars): first + asterisks + last char
    Long strings (> 20 chars): first + *<<<LENGTH:XXX>>>* + last char

    Args:
        value: String to mask

    Returns:
        Masked string or empty string if not a string

    Examples:
        >>> mask_sensitive_data("ab")
        'ab'
        >>> mask_sensitive_data("password123")
        'p*********3'
        >>> mask_sensitive_data("a" * 32)
        'a*<<<LENGTH:032>>>*a'
    """
    if not isinstance(value, str):
        return ""

    length = len(value)

    if length <= 2:
        return value

    if length > 20:
        return f"{value[0]}*<<<LENGTH:{str(length).zfill(3)}>>>*{value[-1]}"

    return value[0] + "*" * (length - 2) + value[-1]


def mask_url_credentials(url):
    """
    Mask credentials in URLs.

    Replaces username and password in URL with masked placeholders.

    Args:
        url: URL string potentially containing credentials

    Returns:
        URL with masked credentials or original URL if no credentials

    Examples:
        >>> mask_url_credentials("http://user:pass@example.com/path")
        'http://*<<<USER>>>:*<<<PASS>>>*@example.com/path'
        >>> mask_url_credentials("https://api.example.com/data")
        'https://api.example.com/data'
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        if not parsed.username and not parsed.password:
            return url

        masked_user = "*<<<USER>>>*" if parsed.username else ""
        masked_pass = "*<<<PASS>>>*" if parsed.password else ""

        port_part = f":{parsed.port}" if parsed.port else ""
        netloc = f"{masked_user}:{masked_pass}@{parsed.hostname}{port_part}"

        return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        return url


def mask_dict_values(data, sensitive_keys=None):
    """
    Mask sensitive values in a dictionary.

    Recursively traverses dict and masks values for specified keys.

    Args:
        data: Dictionary to process
        sensitive_keys: List of keys whose values should be masked.
                       Defaults to common credential keys.

    Returns:
        Dictionary with masked values
    """
    if sensitive_keys is None:
        sensitive_keys = {
            'password', 'pass', 'token', 'api_key', 'apikey', 'secret',
            'auth_token', 'access_token', 'refresh_token', 'credential',
            'dbc_token', 'twocaptcha_key', 'key', 'private_key'
        }

    if not isinstance(data, dict):
        return data

    result = {}
    for key, value in data.items():
        key_lower = str(key).lower()

        if any(sensitive in key_lower for sensitive in sensitive_keys):
            if isinstance(value, str):
                result[key] = mask_sensitive_data(value)
            else:
                result[key] = "***"
        elif isinstance(value, dict):
            result[key] = mask_dict_values(value, sensitive_keys)
        elif isinstance(value, list):
            result[key] = [
                mask_dict_values(item, sensitive_keys) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value

    return result
