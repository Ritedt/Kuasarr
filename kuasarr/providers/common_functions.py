#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Common Functions fÃ¼r kuasarr Providers

import re
import socket
import requests

def check_ip(ip_address):
    """
    PrÃ¼ft ob eine IP-Adresse gÃ¼ltig ist
    
    Args:
        ip_address (str): Die zu prÃ¼fende IP-Adresse
        
    Returns:
        bool: True wenn IP gÃ¼ltig, False wenn nicht
    """
    try:
        socket.inet_aton(ip_address)
        return True
    except socket.error:
        return False

def sanitize_filename(filename):
    """
    Bereinigt einen Dateinamen von ungÃ¼ltigen Zeichen
    
    Args:
        filename (str): Der zu bereinigende Dateiname
        
    Returns:
        str: Bereinigter Dateiname
    """
    # Entferne ungÃ¼ltige Zeichen fÃ¼r Dateinamen
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    
    # Entferne fÃ¼hrende/abschlieÃŸende Punkte und Leerzeichen
    sanitized = sanitized.strip('. ')
    
    return sanitized

def validate_url(url):
    """
    Validiert eine URL
    
    Args:
        url (str): Die zu validierende URL
        
    Returns:
        bool: True wenn URL gÃ¼ltig, False wenn nicht
    """
    url_pattern = re.compile(
        r'^https?://'  # http:// oder https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...oder IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return url_pattern.match(url) is not None

def make_request(url, headers=None, timeout=10, **kwargs):
    """
    Macht einen HTTP-Request mit Standardeinstellungen
    
    Args:
        url (str): URL fÃ¼r den Request
        headers (dict): Optional HTTP Headers
        timeout (int): Timeout in Sekunden
        **kwargs: Weitere Argumente fÃ¼r requests
        
    Returns:
        requests.Response: Response-Objekt oder None bei Fehler
    """
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
    }
    
    if headers:
        default_headers.update(headers)
    
    try:
        response = requests.get(url, headers=default_headers, timeout=timeout, **kwargs)
        return response
    except Exception as e:
        print(f"Request error for {url}: {e}")
        return None

def extract_size_from_text(text):
    """
    Extrahiert GrÃ¶ÃŸenangaben aus Text (z.B. "1.2 GB", "500 MB")
    
    Args:
        text (str): Text mit GrÃ¶ÃŸenangabe
        
    Returns:
        str: Extrahierte GrÃ¶ÃŸe oder None
    """
    size_pattern = r'(\d+(?:\.\d+)?)\s*(GB|MB|KB|TB|GiB|MiB|KiB|TiB)'
    match = re.search(size_pattern, text, re.IGNORECASE)
    
    if match:
        return f"{match.group(1)} {match.group(2).upper()}"
    
    return None

def clean_title(title):
    """
    Bereinigt einen Titel von HTML-Tags und Ã¼berflÃ¼ssigen Zeichen
    
    Args:
        title (str): Der zu bereinigende Titel
        
    Returns:
        str: Bereinigter Titel
    """
    if not title:
        return ""
    
    # Entferne HTML-Tags
    clean = re.sub(r'<[^>]+>', '', title)
    
    # Entferne HTML-Entities
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&lt;', '<')
    clean = clean.replace('&gt;', '>')
    clean = clean.replace('&quot;', '"')
    clean = clean.replace('&#39;', "'")
    
    # Entferne Ã¼berflÃ¼ssige Leerzeichen
    clean = ' '.join(clean.split())
    
    return clean.strip() 
