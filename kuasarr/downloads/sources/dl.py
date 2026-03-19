# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)
# DL Download Source - ported from Quasarr v1.26.5
# Updated with DL-Verbesserungen from Quasarr v1.31.0

import re

from bs4 import BeautifulSoup, NavigableString

from kuasarr.providers.log import info, debug
from kuasarr.providers.sessions.dl import retrieve_and_validate_session, fetch_via_requests_session, invalidate_session
from kuasarr.providers.utils import generate_status_url, check_links_online_status

hostname = "dl"

# Common TLDs to strip for mirror name comparison
COMMON_TLDS = {'.com', '.net', '.io', '.cc', '.to', '.me', '.org', '.co', '.de', '.eu', '.info'}


def normalize_mirror_name(name):
    """
    Normalize mirror name for comparison by lowercasing and removing TLDs.
    e.g., "DDownload.com" -> "ddownload", "Rapidgator.net" -> "rapidgator"
    """
    if not name:
        return ""
    normalized = name.lower().strip()
    for tld in COMMON_TLDS:
        if normalized.endswith(tld):
            normalized = normalized[:-len(tld)]
            break
    return normalized


def extract_password_from_post(soup, host):
    """
    Extract password from forum post using multiple strategies.
    Returns empty string if no password found or if explicitly marked as 'no password'.
    """
    post_text = soup.get_text()
    post_text = re.sub(r'\s+', ' ', post_text).strip()

    password_pattern = r'(?:passwort|password|pass|pw)[\s:]+([a-zA-Z0-9._-]{2,50})'
    match = re.search(password_pattern, post_text, re.IGNORECASE)

    if match:
        password = match.group(1).strip()
        if not re.match(r'^(?:download|mirror|link|episode|info|mediainfo|spoiler|hier|click|klick|kein|none|no)',
                        password, re.IGNORECASE):
            debug(f"Found password: {password}")
            return password

    no_password_patterns = [
        r'(?:passwort|password|pass|pw)[\s:]*(?:kein(?:es)?|none|no|nicht|not|nein|-|–|—)',
        r'(?:kein(?:es)?|none|no|nicht|not|nein)\s*(?:passwort|password|pass|pw)',
    ]

    for pattern in no_password_patterns:
        if re.search(pattern, post_text, re.IGNORECASE):
            debug("No password required (explicitly stated)")
            return ""

    default_password = f"www.{host}"
    debug(f"No password found, using default: {default_password}")
    return default_password


def extract_mirror_name_from_link(link_element):
    """
    Extract the mirror/hoster name from the link text or nearby text.
    """
    link_text = link_element.get_text(strip=True)
    common_non_hosters = {'download', 'mirror', 'link', 'hier', 'click', 'klick', 'code', 'spoiler'}

    # Known hoster patterns for text/image detection
    known_hosters = {
        'rapidgator': ['rapidgator', 'rg.to', 'rg'],
        'ddownload': ['ddownload', 'ddl.to', 'ddl'],
        'turbobit': ['turbobit'],
        '1fichier': ['1fichier'],
        'nitroflare': ['nitroflare'],
        'filer': ['filer'],
        'katfile': ['katfile'],
    }

    # 1. Check link text for known hosters first (high priority)
    if link_text:
        text_lower = link_text.lower()
        for hoster, patterns in known_hosters.items():
            if any(p in text_lower for p in patterns):
                return hoster

    # 2. Check nearby text/images
    common_non_hosters = {'download', 'mirror', 'link', 'hier', 'click', 'klick', 'code', 'spoiler', 'via', 'über', 'untereinander', 'kompatibel', 'kein', 'passwort', 'ladbar', 'einzeln'}

    # Skip if link text is a URL
    if link_text and len(link_text) > 2 and not link_text.startswith('http'):
        cleaned = re.sub(r'[^\w\s-]', '', link_text).strip().lower()
        if cleaned and cleaned not in common_non_hosters:
            # If it's a multi-word string like "Download via Rapidgator", 
            # we already checked for known hosters above.
            # Otherwise, take the last word if it's not common.
            parts = cleaned.split()
            if parts:
                candidate = parts[-1]
                if candidate not in common_non_hosters and 2 < len(candidate) < 30:
                    return candidate

    # Check previous siblings including text nodes
    for sibling in link_element.previous_siblings:
        # Handle text nodes (NavigableString)
        if isinstance(sibling, NavigableString):
            text = sibling.strip()
            if text:
                # Remove common separators like @ : -
                cleaned = re.sub(r'[@:\-–—\s]+$', '', text).strip().lower()
                cleaned = re.sub(r'[^\w\s.-]', '', cleaned).strip()
                if cleaned and len(cleaned) > 2 and cleaned not in common_non_hosters:
                    # Take the last word as mirror name (e.g., "Rapidgator" from "Rapidgator @")
                    parts = cleaned.split()
                    if parts:
                        mirror = parts[-1]
                        if 2 < len(mirror) < 30:
                            return mirror
            continue

        # Skip non-Tag elements
        if not hasattr(sibling, 'name') or sibling.name is None:
            continue

        # Skip spoiler elements entirely
        classes = sibling.get('class', [])
        if classes and any('spoiler' in str(c).lower() for c in classes):
            continue

        # Check for images with hoster names in src/alt/data-url
        img = sibling.find('img') if sibling.name != 'img' else sibling
        if img:
            img_identifiers = (img.get('src', '') + img.get('alt', '') + img.get('data-url', '')).lower()
            for hoster, patterns in known_hosters.items():
                if any(pattern in img_identifiers for pattern in patterns):
                    return hoster

        sibling_text = sibling.get_text(strip=True).lower()
        # Skip if text is too long - likely NFO content or other non-mirror text
        if len(sibling_text) > 30:
            continue
        if sibling_text and len(sibling_text) > 2 and sibling_text not in common_non_hosters:
            cleaned = re.sub(r'[^\w\s-]', '', sibling_text).strip()
            if cleaned and 2 < len(cleaned) < 30:
                return cleaned.split()[0] if ' ' in cleaned else cleaned

    return None


def extract_status_url_from_html(link_element, crypter_type):
    """
    Extract status image URL from HTML near the link element.
    Used primarily for FileCrypt where status URLs cannot be generated.
    """
    if crypter_type != "filecrypt":
        return None

    # 1. Look for status image in the link itself
    img = link_element.find('img')
    if img:
        for attr in ['src', 'data-url']:
            url = img.get(attr, '')
            if 'filecrypt.cc/Stat/' in url:
                return url

    # 2. Look in siblings (both next and previous)
    # XenForo 2 often puts the status image in a separate line/div before or after the link
    search_distance = 6  # Look up to 6 siblings away
    
    # Check next siblings
    count = 0
    for sibling in link_element.next_siblings:
        if count >= search_distance:
            break
        if not hasattr(sibling, 'name') or sibling.name is None:
            continue
        
        # Stop if we hit another significant link (likely for a different mirror)
        if sibling.name == 'a':
            href = sibling.get('href', '')
            if any(c in href.lower() for c in ['filecrypt', 'hide', 'keeplinks', 'tolink']):
                break
        
        count += 1
        img = sibling.find('img') if sibling.name != 'img' else sibling
        if img:
            for attr in ['src', 'data-url']:
                url = img.get(attr, '')
                if 'filecrypt.cc/Stat/' in url:
                    return url

    # Check previous siblings
    count = 0
    for sibling in link_element.previous_siblings:
        if count >= search_distance:
            break
        if not hasattr(sibling, 'name') or sibling.name is None:
            continue
        
        # Stop if we hit another significant link
        if sibling.name == 'a':
            href = sibling.get('href', '')
            if any(c in href.lower() for c in ['filecrypt', 'hide', 'keeplinks', 'tolink']):
                break
                
        count += 1
        img = sibling.find('img') if sibling.name != 'img' else sibling
        if img:
            for attr in ['src', 'data-url']:
                url = img.get(attr, '')
                if 'filecrypt.cc/Stat/' in url:
                    return url

    return None


def build_filecrypt_status_map(soup):
    """
    Build a map of mirror names to FileCrypt status URLs.
    Handles cases where status images are in a separate section from links.
    Returns dict: {mirror_name_lowercase: status_url}
    """
    status_map = {}

    # Find all FileCrypt status images in the post
    for img in soup.find_all('img'):
        status_url = None
        for attr in ['src', 'data-url']:
            url = img.get(attr, '')
            if 'filecrypt.cc/Stat/' in url:
                status_url = url
                break

        if not status_url:
            continue

        # Look for associated mirror name in previous text/siblings
        mirror_name = None

        # Check parent's previous siblings and text nodes
        parent = img.parent
        if parent:
            # Get all previous text content before this image
            prev_text = ""
            for prev in parent.previous_siblings:
                if hasattr(prev, 'get_text'):
                    prev_text = prev.get_text(strip=True)
                elif isinstance(prev, NavigableString):
                    prev_text = prev.strip()
                if prev_text:
                    break

            # Also check text directly before within parent
            for prev in img.previous_siblings:
                if isinstance(prev, NavigableString) and prev.strip():
                    prev_text = prev.strip()
                    break
                elif hasattr(prev, 'get_text'):
                    text = prev.get_text(strip=True)
                    if text:
                        prev_text = text
                        break

            if prev_text:
                # Clean up the text to get mirror name
                cleaned = re.sub(r'[^\w\s.-]', '', prev_text).strip().lower()
                # Take last word/phrase as it's likely the mirror name
                parts = cleaned.split()
                if parts:
                    mirror_name = parts[-1] if len(parts[-1]) > 2 else cleaned

        if mirror_name and mirror_name not in status_map:
            status_map[mirror_name] = status_url
            debug(f"Mapped status image for mirror: {mirror_name} -> {status_url}")

    return status_map


def extract_links_and_password_from_post(post_content, host):
    """
    Extract download links and password from a forum post.
    Returns:
        direct_links: list of href strings
        protected_links: list of [href, identifier, status_url]
        password: str
    """
    direct_links = []
    protected_links = []
    soup = BeautifulSoup(post_content, 'html.parser')

    # Build status map for FileCrypt links (handles separated status images)
    filecrypt_status_map = build_filecrypt_status_map(soup)

    for link in soup.find_all('a', href=True):
        href = link.get('href')

        if href.startswith('/') or host in href:
            continue

        crypter_type = None
        if re.search(r'filecrypt\.', href, re.IGNORECASE):
            crypter_type = "filecrypt"
        elif re.search(r'hide\.', href, re.IGNORECASE):
            crypter_type = "hide"
        elif re.search(r'keeplinks\.', href, re.IGNORECASE):
            crypter_type = "keeplinks"
        elif re.search(r'tolink\.', href, re.IGNORECASE):
            crypter_type = "tolink"
        
        # Check for direct hoster links (Rapidgator, DDownload etc.)
        is_direct = False
        if not crypter_type:
            for hoster, patterns in {
                'rapidgator': ['rapidgator.net', 'rg.to'],
                'ddownload': ['ddownload.com', 'ddl.to'],
                'turbobit': ['turbobit.net'],
                '1fichier': ['1fichier.com'],
                'nitroflare': ['nitroflare.com'],
                'katfile': ['katfile.com'],
            }.items():
                if any(p in href.lower() for p in patterns):
                    is_direct = True
                    break
        
        if not crypter_type and not is_direct:
            debug(f"Unsupported link crypter/hoster found: {href}")
            continue

        mirror_name = extract_mirror_name_from_link(link)
        identifier = mirror_name if mirror_name else (crypter_type or "direct")

        if is_direct:
            if href not in direct_links:
                direct_links.append(href)
            continue

        # Get status URL - try extraction first, then status map, then generation
        status_url = extract_status_url_from_html(link, crypter_type)

        if not status_url and crypter_type == "filecrypt" and mirror_name:
            # Try to find in status map by mirror name (normalized, case-insensitive, TLD-stripped)
            mirror_normalized = normalize_mirror_name(mirror_name)
            for map_key, map_url in filecrypt_status_map.items():
                map_key_normalized = normalize_mirror_name(map_key)
                if mirror_normalized in map_key_normalized or map_key_normalized in mirror_normalized:
                    status_url = map_url
                    break

        if not status_url:
            status_url = generate_status_url(href, crypter_type)

        # Avoid duplicates (check href and identifier)
        if not any(l[0] == href and l[1] == identifier for l in protected_links):
            protected_links.append([href, identifier, status_url])
            status_info = f"status: {status_url}" if status_url else "no status URL"
            if mirror_name:
                debug(f"Found {crypter_type} link for mirror: {mirror_name} ({status_info})")
            else:
                debug(f"Found {crypter_type} link ({status_info})")

    password = ""
    if direct_links or protected_links:
        password = extract_password_from_post(soup, host)

    return direct_links, protected_links, password


def get_dl_download_links(shared_state, url, mirror, title, password):
    """
    KEEP THE SIGNATURE EVEN IF SOME PARAMETERS ARE UNUSED!

    DL source handler - extracts links and password from forum thread.
    Iterates through posts to find one with online links.

    Note: The password parameter is unused intentionally - password must be extracted from the post.
    """
    host = shared_state.values["config"]("Hostnames").get(hostname)
    if not host:
        return {"direct": [], "protected": [], "password": ""}

    clean_host = host.replace("www.", "")

    sess = retrieve_and_validate_session(shared_state)
    if not sess:
        info(f"Could not retrieve valid session for {clean_host}")
        return {"direct": [], "protected": [], "password": ""}

    try:
        response = fetch_via_requests_session(shared_state, method="GET", target_url=url, timeout=30)

        if response.status_code != 200:
            info(f"Failed to load thread page: {url} (Status: {response.status_code})")
            return {"direct": [], "protected": [], "password": ""}

        soup = BeautifulSoup(response.text, 'html.parser')

        # Get all posts in thread
        posts = soup.select('article.message--post')
        if not posts:
            # Fallback für andere XF2 Themes
            posts = soup.select('article.message')
            
        if not posts:
            info(f"Could not find any posts in thread: {url}")
            return {"direct": [], "protected": [], "password": ""}

        # Iterate through posts to find one with online links
        for post_index, post in enumerate(posts):
            post_content = post.select_one('div.bbWrapper')
            if not post_content:
                continue

            direct_links, protected_links_with_status, extracted_password = extract_links_and_password_from_post(str(post_content), clean_host)

            if not direct_links and not protected_links_with_status:
                continue

            # Check which protected links are online
            online_protected = check_links_online_status(protected_links_with_status)

            if direct_links or online_protected:
                post_info = "first post" if post_index == 0 else f"post #{post_index + 1}"
                debug(f"Found {len(direct_links)} direct and {len(online_protected)} protected online link(s) in {post_info} for: {title}")
                return {
                    "direct": direct_links,
                    "protected": online_protected,
                    "password": extracted_password
                }
            else:
                debug(f"All links in post #{post_index + 1} are offline, checking next post...")

        info(f"No online download links found in any post: {url}")
        return {"direct": [], "protected": [], "password": ""}

    except Exception as e:
        info(f"Error extracting download links from {url}: {e}")
        invalidate_session(shared_state)
        return {"direct": [], "protected": [], "password": ""}
