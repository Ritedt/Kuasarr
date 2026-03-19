# -*- coding: utf-8 -*-
# Kuasarr - Captcha providers

from typing import Optional, Union

from kuasarr.providers.log import info, debug


def create_captcha_client(shared_state) -> Optional[Union["DeathByCaptchaClient", "TwoCaptchaClient"]]:
    """Factory: Erstellt den konfigurierten Captcha-Client.
    
    Unterstützt:
    - DeathByCaptcha (dbc) - Standard
    - 2Captcha (2captcha) - 50% günstiger für CutCaptcha
    
    Args:
        shared_state: Kuasarr shared state module
        
    Returns:
        Configured captcha client or None if not configured
    """
    from kuasarr.storage.config import Config
    
    captcha_config = Config('Captcha')
    service = (captcha_config.get('service') or 'dbc').lower().strip()
    
    if service == '2captcha':
        from kuasarr.providers.captcha.twocaptcha_client import TwoCaptchaClient
        
        api_key = captcha_config.get('twocaptcha_api_key')
        if not api_key:
            debug("2Captcha: No API key configured")
            return None
        
        timeout = int(captcha_config.get('timeout') or 120)
        max_retries = int(captcha_config.get('max_retries') or 3)
        retry_backoff = int(captcha_config.get('retry_backoff') or 5)
        
        info("Using 2Captcha as captcha service (50% cheaper for CutCaptcha)")
        return TwoCaptchaClient(
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
        )
    
    else:  # Default: DBC
        from kuasarr.providers.captcha.dbc_client import create_dbc_client
        
        username = captcha_config.get('dbc_username')
        password = captcha_config.get('dbc_password')
        authtoken = captcha_config.get('dbc_authtoken')
        
        if not authtoken and not (username and password):
            debug("DeathByCaptcha: No credentials configured")
            return None
        
        # Update shared_state mit DBC config
        shared_state.values["dbc_config"] = {
            "username": username or "",
            "password": password or "",
            "authtoken": authtoken or "",
            "timeout": int(captcha_config.get('timeout') or 120),
            "max_retries": int(captcha_config.get('max_retries') or 3),
            "retry_backoff": int(captcha_config.get('retry_backoff') or 5),
        }
        
        info("Using DeathByCaptcha as captcha service")
        return create_dbc_client(shared_state)


__all__ = [
    "create_captcha_client",
]
