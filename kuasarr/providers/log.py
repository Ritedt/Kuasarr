# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import datetime
import os


def timestamp():
    return datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")


def info(string):
    print(f"{timestamp()} {string}")


def debug(string):
    if os.getenv('DEBUG'):
        info(string)


def error(string):
    info(f"ERROR: {string}")


def warn(string):
    info(f"WARNING: {string}")


# ============================================================================
# Audit Logging
# ============================================================================

# Sensitive field names that should not have values logged (case-insensitive)
_SENSITIVE_FIELDS = {
    'password', 'pass', 'secret', 'key', 'token', 'api_key', 'apikey',
    'auth', 'credential', 'dbc_authtoken', 'twocaptcha_api_key',
    'internal_address', 'external_address', 'url', 'webhook'
}


def _is_sensitive_field(field_name: str) -> bool:
    """Check if a field name indicates sensitive data."""
    field_lower = field_name.lower()
    return any(sensitive in field_lower for sensitive in _SENSITIVE_FIELDS)


def audit_settings_change(section: str, changes: dict, user: str = None):
    """Log a settings change for audit purposes."""
    user_str = f" by user '{user}'" if user else ""
    info(f"AUDIT: Settings changed in section '{section}'{user_str}")

    for field_name, (old_value, new_value) in changes.items():
        if _is_sensitive_field(field_name):
            # Log that a sensitive field changed without exposing values
            info(f"AUDIT:   - {field_name}: [REDACTED] (value changed)")
        else:
            # Log non-sensitive fields with values
            old_display = old_value if old_value else "(empty)"
            new_display = new_value if new_value else "(empty)"
            info(f"AUDIT:   - {field_name}: '{old_display}' -> '{new_display}'")


def audit_core_settings_change(internal_address_changed: bool, external_address_changed: bool,
                                timezone_changed: bool, old_values: dict, new_values: dict, user: str = None):
    """Specialized audit log for core settings changes."""
    user_str = f" by user '{user}'" if user else ""
    info(f"AUDIT: Core settings modified{user_str}")

    if internal_address_changed:
        info(f"AUDIT:   - internal_address: [REDACTED] (URL changed)")
    if external_address_changed:
        info(f"AUDIT:   - external_address: [REDACTED] (URL changed)")
    if timezone_changed:
        old_tz = old_values.get('timezone', '(empty)')
        new_tz = new_values.get('timezone', '(empty)')
        info(f"AUDIT:   - timezone: '{old_tz}' -> '{new_tz}'")


def audit_security_event(event_type: str, details: str, user: str = None, ip: str = None):
    """Log a security-related event."""
    user_str = f" user='{user}'" if user else ""
    ip_str = f" ip={ip}" if ip else ""
    info(f"AUDIT SECURITY [{event_type}]:{user_str}{ip_str} - {details}")
