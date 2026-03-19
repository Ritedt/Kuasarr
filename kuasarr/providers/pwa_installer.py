# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""
PWA Installation Helper for Windows EXE builds.
Opens the browser with PWA installation prompt on first run.
"""

import os
import sys
import webbrowser
import threading
import time


def is_frozen_exe():
    """Check if running as a frozen PyInstaller executable."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def is_windows():
    """Check if running on Windows."""
    return os.name == 'nt'


def should_prompt_pwa_install(config_class):
    """
    Check if PWA installation prompt should be shown.
    Only on first run of Windows EXE.
    """
    if not is_frozen_exe() or not is_windows():
        return False
    
    pwa_config = config_class('PWA')
    prompted = pwa_config.get('install_prompted')
    return not prompted


def mark_pwa_prompted(config_class):
    """Mark that PWA installation has been prompted."""
    pwa_config = config_class('PWA')
    pwa_config.save('install_prompted', True)


def open_pwa_install_page(base_url, delay=3):
    """
    Open the PWA installation page in the default browser after a delay.
    The delay allows the web server to start first.
    
    Args:
        base_url: The base URL of the Kuasarr server (e.g., http://localhost:8080)
        delay: Seconds to wait before opening browser
    """
    def _open_browser():
        time.sleep(delay)
        # Open the install page which will guide the user through PWA installation
        install_url = f"{base_url}/pwa-install"
        try:
            webbrowser.open(install_url)
        except Exception:
            pass  # Silently fail if browser can't be opened
    
    # Run in background thread to not block startup
    thread = threading.Thread(target=_open_browser, daemon=True)
    thread.start()
