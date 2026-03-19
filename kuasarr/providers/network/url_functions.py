#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# URL Functions fÃ¼r kuasarr Providers

import re
import requests
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

def normalize_url(url, base_url=None):
    """
    Normalisiert eine URL (macht relative URLs absolut, etc.)
    
    Args:
        url (str): Die zu normalisierende URL
        base_url (str): Basis-URL fÃ¼r relative URLs
        
    Returns:
        str: Normalisierte URL
    """
    if not url:
        return ""
    
    # Wenn es eine relative URL ist und wir eine base_url haben
    if base_url and not url.startswith(('http://', 'https://')):
        return urljoin(base_url, url)
    
    return url

def extract_domain(url):
    """
    Extrahiert die Domain aus einer URL
    
    Args:
        url (str): Die URL
        
    Returns:
        str: Domain oder None
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except:
        return None

def build_search_url(base_url, query, params=None):
    """
    Baut eine Such-URL zusammen
    
    Args:
        base_url (str): Basis-URL fÃ¼r die Suche
        query (str): Suchbegriff
        params (dict): ZusÃ¤tzliche Parameter
        
    Returns:
        str: Zusammengebaute Such-URL
    """
    if not params:
        params = {}
    
    # FÃ¼ge Query hinzu
    params['q'] = query
    
    # Parse base URL
    parsed = urlparse(base_url)
    
    # Merge mit existing query params
    existing_params = parse_qs(parsed.query)
    for key, value in existing_params.items():
        if key not in params:
            params[key] = value[0] if isinstance(value, list) and len(value) > 0 else value
    
    # Baue neue URL
    new_query = urlencode(params)
    new_parsed = parsed._replace(query=new_query)
    
    return urlunparse(new_parsed)

def is_valid_download_link(url):
    """
    PrÃ¼ft ob eine URL ein gÃ¼ltiger Download-Link ist
    
    Args:
        url (str): Die zu prÃ¼fende URL
        
    Returns:
        bool: True wenn gÃ¼ltiger Download-Link
    """
    if not url:
        return False
    
    # Bekannte Download-Hoster
    download_domains = [
        'filecrypt.cc', 'filecrypt.co',
        'rapidgator.net', 'uploaded.net',
        'turbobit.net', 'nitroflare.com',
        '1fichier.com', 'ddownload.com'
    ]
    
    try:
        domain = extract_domain(url)
        return any(d in domain.lower() for d in download_domains)
    except:
        return False

def extract_file_id(url):
    """
    Extrahiert eine Datei-ID aus einer URL
    
    Args:
        url (str): Die URL
        
    Returns:
        str: Datei-ID oder None
    """
    # Verschiedene Patterns fÃ¼r verschiedene Hoster
    patterns = [
        r'/Container/([A-F0-9]+)\.html',  # FileCrypt
        r'/file/([a-zA-Z0-9]+)',         # Allgemein
        r'/([a-zA-Z0-9]{10,})',          # Allgemein 10+ chars
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def clean_url_params(url, keep_params=None):
    """
    Bereinigt URL-Parameter (entfernt Tracking, etc.)
    
    Args:
        url (str): Die URL
        keep_params (list): Parameter die behalten werden sollen
        
    Returns:
        str: Bereinigte URL
    """
    if not keep_params:
        keep_params = []
    
    try:
        parsed = urlparse(url)
        
        if not parsed.query:
            return url
        
        params = parse_qs(parsed.query)
        cleaned_params = {}
        
        for key, value in params.items():
            if key in keep_params:
                cleaned_params[key] = value[0] if isinstance(value, list) and len(value) > 0 else value
        
        new_query = urlencode(cleaned_params) if cleaned_params else ""
        new_parsed = parsed._replace(query=new_query)
        
        return urlunparse(new_parsed)
    except:
        return url

def get_final_url(url, session=None, timeout=10):
    """
    Folgt Redirects und gibt die finale URL zurÃ¼ck
    
    Args:
        url (str): Start-URL
        session: Optional requests Session
        timeout (int): Timeout in Sekunden
        
    Returns:
        str: Finale URL oder ursprÃ¼ngliche URL bei Fehler
    """
    try:
        if session:
            response = session.head(url, timeout=timeout, allow_redirects=True)
        else:
            response = requests.head(url, timeout=timeout, allow_redirects=True)
        
        return response.url
    except:
        return url

def get_url_headers(url=None):
    """
    Gibt Standard-HTTP-Headers zurÃ¼ck
    
    Args:
        url (str): Optional URL fÃ¼r spezifische Headers
        
    Returns:
        dict: HTTP Headers Dictionary
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    # Spezifische Headers fÃ¼r bestimmte Domains
    if url:
        domain = extract_domain(url)
        if 'data-load.me' in domain:
            headers['Referer'] = 'https://www.data-load.me/'
    
    return headers

def get_url(url, session=None, timeout=10, headers=None):
    """
    Macht einen GET-Request zu einer URL
    
    Args:
        url (str): Die URL
        session: Optional requests Session
        timeout (int): Timeout in Sekunden
        headers (dict): Optional Headers
        
    Returns:
        requests.Response: Response-Objekt oder None bei Fehler
    """
    if not headers:
        headers = get_url_headers(url)
    
    try:
        if session:
            response = session.get(url, timeout=timeout, headers=headers)
        else:
            response = requests.get(url, timeout=timeout, headers=headers)
        
        return response
    except Exception as e:
        print(f"Error getting URL {url}: {e}")
        return None 
