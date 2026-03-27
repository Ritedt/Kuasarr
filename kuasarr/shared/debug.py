# -*- coding: utf-8 -*-
"""
Debug utilities for troubleshooting and support.

Provides functions to upload debug information to external services
for easier issue diagnosis.
"""

import socket
import traceback
from typing import Optional


def upload_to_termbin(content: str, host: str = "termbin.com", port: int = 9999) -> Optional[str]:
    """
    Upload content to termbin.com for debugging.

    Creates a socket connection to termbin.com and uploads the content,
    returning a shareable URL.

    Args:
        content: Text content to upload
        host: Termbin host (default: termbin.com)
        port: Termbin port (default: 9999)

    Returns:
        URL to the pasted content or None if upload failed

    Example:
        >>> url = upload_to_termbin("Error log here...")
        >>> print(f"Debug info: {url}")
        Debug info: https://termbin.com/xxxx
    """
    if not content:
        return None

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect((host, port))
            s.sendall(content.encode('utf-8') + b'\n')

            response = s.recv(1024).decode('utf-8').replace('\x00', '').strip()

            if response.startswith('http'):
                return response
            return None
    except socket.timeout:
        return None
    except Exception:
        return None


def format_exception_for_upload(exc: Exception, context: Optional[dict] = None) -> str:
    """
    Format an exception with optional context for upload.

    Args:
        exc: Exception to format
        context: Optional dictionary with additional context

    Returns:
        Formatted string ready for upload
    """
    lines = [
        "=== Kuasarr Debug Report ===",
        "",
        "--- Exception ---",
        traceback.format_exception(type(exc), exc, exc.__traceback__),
        ""
    ]

    if context:
        lines.extend([
            "--- Context ---",
            ""
        ])
        for key, value in context.items():
            lines.append(f"{key}: {value}")
        lines.append("")

    return "\n".join(str(line) for line in lines)


def upload_exception(exc: Exception, context: Optional[dict] = None) -> Optional[str]:
    """
    Upload exception details to termbin.

    Convenience function that formats and uploads an exception.

    Args:
        exc: Exception to upload
        context: Optional context dictionary

    Returns:
        termbin.com URL or None if upload failed
    """
    content = format_exception_for_upload(exc, context)
    return upload_to_termbin(content)
