# -*- coding: utf-8 -*-
# Kuasarr WX Search Integration
# Based on PR #159 from rix1337/Quasarr

import html
import re
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from kuasarr.providers.imdb_metadata import get_localized_title
from kuasarr.providers.log import info, debug

hostname = "wx"

# Regex to detect porn-tag .XXX. (case-insensitive, dots included)
XXX_REGEX = re.compile(r"\.xxx\.", re.I)
# Regex to detect video resolution
RESOLUTION_REGEX = re.compile(r"\d{3,4}p", re.I)
# Regex to detect video codec tags
CODEC_REGEX = re.compile(r"x264|x265|h264|h265|hevc|avc", re.I)


def convert_to_rss_date(date_str):
    """
    Convert date string to RFC-822 style date with +0000 timezone.
    Handles various formats from WX.
    """
    if not date_str:
        return datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
    
    try:
        # Try ISO format first
        if 'T' in date_str:
            parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('+')[0])
        # Try German format
        elif '.' in date_str and '-' in date_str:
            parsed = datetime.strptime(date_str.split(' - ')[0], "%d.%m.%Y")
        else:
            parsed = datetime.now()
    except:
        parsed = datetime.now()
    
    return parsed.strftime("%a, %d %b %Y %H:%M:%S +0000")


def extract_size(text):
    """
    Extract size from text, e.g. "8 GB" -> {"size": "8", "sizeunit": "GB"}
    """
    if not text:
        return {"size": "0", "sizeunit": "MB"}
    
    match = re.search(r"(\d+(?:\.\d+)?)\s*([KMGT]?i?B)", text, re.I)
    if match:
        return {"size": match.group(1), "sizeunit": match.group(2).upper().replace('IB', 'B')}
    return {"size": "0", "sizeunit": "MB"}


def _parse_api_releases(data, shared_state, url_base, password, mirror_filter, 
                        request_from=None, search_string=None, season=None, episode=None):
    """
    Parse releases from WX API response.
    """
    releases = []
    is_search = search_string is not None
    one_hour_ago = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    
    items = data if isinstance(data, list) else data.get('releases', data.get('items', []))
    
    for item in items:
        try:
            title = item.get('title', item.get('name', ''))
            if not title:
                continue
            
            # Get detail URL
            slug = item.get('slug', item.get('id', ''))
            source = f"https://{url_base}/detail/{slug}/{quote_plus(title)}" if slug else ''
            
            # Filter in search context
            if is_search:
                if not shared_state.is_valid_release(title, request_from, search_string, season, episode):
                    continue
                
                if 'lazylibrarian' not in request_from.lower():
                    # Drop .XXX. unless user explicitly searched xxx
                    if XXX_REGEX.search(title) and 'xxx' not in search_string.lower():
                        continue
                    # Require resolution/codec for video releases
                    if not (RESOLUTION_REGEX.search(title) or CODEC_REGEX.search(title)):
                        continue
            
            # Extract size
            size_str = item.get('size', item.get('filesize', '0 MB'))
            sz = extract_size(str(size_str))
            mb = shared_state.convert_to_mb(sz)
            size_bytes = mb * 1024 * 1024
            
            # Extract date
            date_str = item.get('date', item.get('created_at', item.get('pubDate', '')))
            published = convert_to_rss_date(date_str) if date_str else one_hour_ago
            
            # IMDb ID if available
            imdb_id = item.get('imdb_id', item.get('imdb', None))
            
            # Create payload for download
            payload = urlsafe_b64encode(
                f"{title}|{source}|{mirror_filter or ''}|{mb}|{password}|{imdb_id or ''}".encode()
            ).decode()
            download_link = f"{shared_state.values['internal_address']}/download/?payload={payload}"
            
            releases.append({
                "details": {
                    "title": title,
                    "hostname": hostname,
                    "imdb_id": imdb_id,
                    "link": download_link,
                    "mirror": mirror_filter,
                    "size": size_bytes,
                    "date": published,
                    "source": source
                },
                "type": "unprotected"
            })
        except Exception as e:
            debug(f"Error parsing {hostname.upper()} item: {e}")
            continue
    
    return releases


def _parse_html_releases(soup, shared_state, url_base, password, mirror_filter,
                         request_from=None, search_string=None, season=None, episode=None):
    """
    Parse releases from WX HTML page (fallback).
    """
    releases = []
    is_search = search_string is not None
    one_hour_ago = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    
    # Look for release items in various HTML structures
    items = soup.select('.release-item, .item, article, .card')
    
    for item in items:
        try:
            # Find title and link
            title_elem = item.select_one('h2 a, h3 a, .title a, a.release-link')
            if not title_elem:
                continue
            
            title = title_elem.get_text(strip=True)
            href = title_elem.get('href', '')
            
            if not title or not href:
                continue
            
            # Build full URL
            if not href.startswith('http'):
                source = f"https://{url_base}{href}"
            else:
                source = href
            
            # Filter in search context
            if is_search:
                if not shared_state.is_valid_release(title, request_from, search_string, season, episode):
                    continue
                
                if 'lazylibrarian' not in request_from.lower():
                    if XXX_REGEX.search(title) and 'xxx' not in search_string.lower():
                        continue
                    if not (RESOLUTION_REGEX.search(title) or CODEC_REGEX.search(title)):
                        continue
            
            # Extract size
            size_elem = item.select_one('.size, .filesize, [data-size]')
            size_str = size_elem.get_text(strip=True) if size_elem else '0 MB'
            sz = extract_size(size_str)
            mb = shared_state.convert_to_mb(sz)
            size_bytes = mb * 1024 * 1024
            
            # Extract date
            date_elem = item.select_one('time, .date, .pubdate')
            date_str = date_elem.get('datetime', date_elem.get_text(strip=True)) if date_elem else ''
            published = convert_to_rss_date(date_str) if date_str else one_hour_ago
            
            # Create payload
            payload = urlsafe_b64encode(
                f"{title}|{source}|{mirror_filter or ''}|{mb}|{password}|".encode()
            ).decode()
            download_link = f"{shared_state.values['internal_address']}/download/?payload={payload}"
            
            releases.append({
                "details": {
                    "title": title,
                    "hostname": hostname,
                    "imdb_id": None,
                    "link": download_link,
                    "mirror": mirror_filter,
                    "size": size_bytes,
                    "date": published,
                    "source": source
                },
                "type": "unprotected"
            })
        except Exception as e:
            debug(f"Error parsing {hostname.upper()} HTML item: {e}")
            continue
    
    return releases


def wx_feed(shared_state, start_time, request_from, mirror=None):
    """
    Get feed/latest releases from WX.
    """
    wx = shared_state.values["config"]("Hostnames").get(hostname)
    if not wx:
        debug(f"{hostname.upper()} hostname not configured")
        return []
    
    password = f"www.{wx}"
    releases = []
    
    # Determine feed type based on request
    if "lazylibrarian" in request_from.lower():
        feed_type = "ebooks"
    elif "radarr" in request_from.lower():
        feed_type = "movies"
    else:
        feed_type = "tv"
    
    headers = {'User-Agent': shared_state.values["user_agent"]}
    
    try:
        # Try API first (no artificial limit to align with upstream)
        api_url = f"https://api.{wx}/releases?type={feed_type}"
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            try:
                data = response.json()
                releases = _parse_api_releases(data, shared_state, wx, password, mirror)
            except ValueError:
                debug(f"{hostname.upper()} API returned invalid JSON, falling back to HTML")
                # Fallback to HTML
                html_url = f"https://{wx}/{feed_type}"
                response = requests.get(html_url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.content, "html.parser")
                releases = _parse_html_releases(soup, shared_state, wx, password, mirror)
        else:
            # Fallback to HTML
            html_url = f"https://{wx}/{feed_type}"
            response = requests.get(html_url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")
            releases = _parse_html_releases(soup, shared_state, wx, password, mirror)
            
    except Exception as e:
        info(f"Error loading {hostname.upper()} feed: {e}")
        releases = []
    
    debug(f"Time taken: {time.time() - start_time:.2f}s ({hostname})")
    return releases


def wx_search(shared_state, start_time, request_from, search_string, mirror=None, season=None, episode=None):
    """
    Search for releases on WX.
    """
    wx = shared_state.values["config"]("Hostnames").get(hostname)
    if not wx:
        debug(f"{hostname.upper()} hostname not configured")
        return []
    
    password = f"www.{wx}"
    releases = []
    
    # Handle IMDb ID
    imdb_id = shared_state.is_imdb_id(search_string)
    if imdb_id:
        search_string = get_localized_title(shared_state, imdb_id, 'de')
        if not search_string:
            info(f"Could not extract title from IMDb-ID {imdb_id}")
            return releases
        search_string = html.unescape(search_string)
    
    q = quote_plus(search_string)
    headers = {'User-Agent': shared_state.values["user_agent"]}
    
    try:
        # Try API first
        api_url = f"https://api.{wx}/search?q={q}"
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            try:
                data = response.json()
                releases = _parse_api_releases(
                    data, shared_state, wx, password, mirror,
                    request_from=request_from,
                    search_string=search_string,
                    season=season, episode=episode
                )
            except ValueError:
                debug(f"{hostname.upper()} search API returned invalid JSON, falling back to HTML")
                # Fallback to HTML search
                html_url = f"https://{wx}/search?q={q}"
                response = requests.get(html_url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.content, "html.parser")
                releases = _parse_html_releases(
                    soup, shared_state, wx, password, mirror,
                    request_from=request_from,
                    search_string=search_string,
                    season=season, episode=episode
                )
        else:
            # Fallback to HTML search
            html_url = f"https://{wx}/search?q={q}"
            response = requests.get(html_url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")
            releases = _parse_html_releases(
                soup, shared_state, wx, password, mirror,
                request_from=request_from,
                search_string=search_string,
                season=season, episode=episode
            )
            
    except Exception as e:
        info(f"Error loading {hostname.upper()} search: {e}")
        releases = []
    
    debug(f"Time taken: {time.time() - start_time:.2f}s ({hostname})")
    return releases
