# -*- coding: utf-8 -*-
# Kuasarr
# Keeplinks.org decryption module

import re
import requests
from bs4 import BeautifulSoup

from kuasarr.providers.log import info, debug


def get_keeplinks_links(shared_state, captcha_token, title, url, password=None, mirror=None):
    """
    Decrypt Keeplinks.org container links.
    
    Flow:
    1. GET the keeplinks URL
    2. POST to proceed past the first page (showpageval=1)
    3. Solve the image CAPTCHA and POST the solution
    4. Extract the download links from the response
    
    Args:
        shared_state: Shared application state
        captcha_token: The solved CAPTCHA text (from DBC image CAPTCHA)
        title: Release title
        url: Keeplinks URL (e.g., https://www.keeplinks.org/p16/65380314ae40e)
        password: Optional password (not commonly used on keeplinks)
        mirror: Optional mirror preference
        
    Returns:
        dict with 'status' and 'links' on success, or False on failure
    """
    info(f"Attempting to decrypt Keeplinks: {url}")
    
    session = requests.Session()
    headers = {
        'User-Agent': shared_state.values["user_agent"],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': url,
    }
    
    try:
        # Step 1: Initial GET request
        debug(f"Keeplinks: Initial GET request to {url}")
        response = session.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            info(f"Keeplinks: Initial request failed with status {response.status_code}")
            return False
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check if we're on the "Click To Proceed" page
        proceed_form = soup.find('form', {'name': 'frmprotect'})
        if proceed_form:
            # Check for showpageval or a submit button with "proceed", "klick", "continue" text
            is_proceed_page = False
            showpageval_input = proceed_form.find('input', {'name': 'showpageval'})
            if showpageval_input and showpageval_input.get('value') == '1':
                is_proceed_page = True
            
            if not is_proceed_page:
                # Look for submit input or button
                submit_btn = proceed_form.find(['input', 'button'], {'type': 'submit'}) or proceed_form.find('button')
                if submit_btn:
                    btn_text = (submit_btn.get('value') or submit_btn.text or "").lower()
                    if any(x in btn_text for x in ['proceed', 'klick', 'continue', 'proceed', 'fortfahren']):
                        is_proceed_page = True
            
            if is_proceed_page:
                # Step 2: POST to proceed past the first page
                debug("Keeplinks: Submitting 'Click To Proceed' form")
                post_data = {}
                for input_elem in proceed_form.find_all('input'):
                    name = input_elem.get('name')
                    if name:
                        post_data[name] = input_elem.get('value', '')
                
                # Also check for buttons with names
                for btn in proceed_form.find_all(['input', 'button'], {'type': 'submit'}):
                    name = btn.get('name')
                    if name:
                        post_data[name] = btn.get('value', '')
                
                response = session.post(url, data=post_data, headers=headers, timeout=30)
                
                if response.status_code != 200:
                    info(f"Keeplinks: Proceed POST failed with status {response.status_code}")
                    return False
                
                soup = BeautifulSoup(response.text, 'html.parser')
        
        # Step 3: Check for download links FIRST (they are visible on the CAPTCHA page!)
        links = extract_download_links(soup)
        if links:
            info(f"Keeplinks: Found {len(links)} links (no CAPTCHA solving needed)")
            return {"status": "success", "links": links}
        
        # Step 4: If no links found, check for CAPTCHA form
        captcha_form = soup.find('form', {'name': 'frmprotect'})
        if not captcha_form:
            info("Keeplinks: Could not find CAPTCHA form and no links found")
            return False
        
        # Check if CAPTCHA is present
        captcha_input = captcha_form.find('input', {'name': 'captcha_cool'})
        if not captcha_input:
            info("Keeplinks: No CAPTCHA input and no links found")
            return False
        
        # Build POST data for CAPTCHA submission
        post_data = {}
        for input_elem in captcha_form.find_all('input'):
            name = input_elem.get('name')
            value = input_elem.get('value', '')
            if name:
                if name == 'captcha_cool':
                    post_data[name] = captcha_token
                else:
                    post_data[name] = value
        
        debug(f"Keeplinks: Submitting CAPTCHA with token: {captcha_token}")
        response = session.post(url, data=post_data, headers=headers, timeout=30)
        
        if response.status_code != 200:
            info(f"Keeplinks: CAPTCHA POST failed with status {response.status_code}")
            return False
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for error messages
        error_msg = soup.find(text=re.compile(r'wrong|invalid|incorrect', re.IGNORECASE))
        if error_msg:
            info(f"Keeplinks: CAPTCHA was rejected - {error_msg}")
            return False
        
        # Step 4: Extract download links
        links = extract_download_links(soup)
        
        if not links:
            info("Keeplinks: No download links found after CAPTCHA submission")
            return False
        
        # Filter by mirror if specified
        if mirror:
            mirror_lower = mirror.lower()
            filtered_links = [link for link in links if mirror_lower in link.lower()]
            if filtered_links:
                links = filtered_links
                debug(f"Keeplinks: Filtered to {len(links)} links matching mirror '{mirror}'")
        
        info(f"Keeplinks: Successfully extracted {len(links)} download links")
        return {"status": "success", "links": links}
        
    except requests.RequestException as e:
        info(f"Keeplinks: Request error - {e}")
        return False
    except Exception as e:
        info(f"Keeplinks: Unexpected error - {e}")
        return False


def extract_download_links(soup):
    """Extract download links from Keeplinks page.
    
    Links are in <label class="form_box_title"> with <a class="selecttext live">
    Filters out ads/affiliate links.
    """
    links = []
    
    # Patterns for valid download links (must have file path)
    hoster_patterns = [
        r'rapidgator\.net/file/',
        r'rg\.to/file/',
        r'ddownload\.com/[a-z0-9]+/',
        r'uploaded\.net/file/',
        r'uploaded\.to/file/',
        r'ul\.to/[a-z0-9]+',
        r'nitroflare\.com/view/',
        r'turbobit\.net/[a-z0-9]+/',
        r'1fichier\.com/\?[a-z0-9]+',
        r'katfile\.com/[a-z0-9]+/',
        r'mexashare\.com/[a-z0-9]+/',
        r'depositfiles\.com/files/',
        r'filefactory\.com/file/',
    ]
    
    combined_pattern = '|'.join(hoster_patterns)
    
    # First try: Look for links in form_box_title (Keeplinks specific)
    form_boxes = soup.find_all('label', class_='form_box_title')
    for box in form_boxes:
        for link in box.find_all('a', href=True):
            href = link.get('href', '').strip()
            if re.search(combined_pattern, href, re.IGNORECASE):
                if href not in links:
                    links.append(href)
                    debug(f"Keeplinks: Found download link: {href[:60]}...")
    
    # Fallback: Look for links with class "selecttext"
    if not links:
        for link in soup.find_all('a', class_='selecttext'):
            href = link.get('href', '').strip()
            if re.search(combined_pattern, href, re.IGNORECASE):
                if href not in links:
                    links.append(href)
    
    # Final fallback: Any matching link without image and not affiliate
    if not links:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').strip()
            
            # Skip links with images (ads/banners)
            if link.find('img'):
                continue
            
            # Skip affiliate/free links
            if '/free' in href.lower() or 'affiliate' in href.lower():
                continue
            
            if re.search(combined_pattern, href, re.IGNORECASE):
                if href not in links:
                    links.append(href)
    
    return links


def get_keeplinks_captcha_info(shared_state, url):
    session = requests.Session()
    headers = {
        'User-Agent': shared_state.values["user_agent"],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    try:
        # Initial GET
        response = session.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for "Click To Proceed" page
        proceed_form = soup.find('form', {'name': 'frmprotect'})
        if proceed_form:
            is_proceed_page = False
            showpageval_input = proceed_form.find('input', {'name': 'showpageval'})
            if showpageval_input and showpageval_input.get('value') == '1':
                is_proceed_page = True
            
            if not is_proceed_page:
                # Look for submit input or button
                submit_btn = proceed_form.find(['input', 'button'], {'type': 'submit'}) or proceed_form.find('button')
                if submit_btn:
                    btn_text = (submit_btn.get('value') or submit_btn.text or "").lower()
                    if any(x in btn_text for x in ['proceed', 'klick', 'continue', 'proceed', 'fortfahren']):
                        is_proceed_page = True
                    
            if is_proceed_page:
                # POST to proceed
                post_data = {}
                for input_elem in proceed_form.find_all('input'):
                    name = input_elem.get('name')
                    if name:
                        post_data[name] = input_elem.get('value', '')
                
                # Also check for buttons with names
                for btn in proceed_form.find_all(['input', 'button'], {'type': 'submit'}):
                    name = btn.get('name')
                    if name:
                        post_data[name] = btn.get('value', '')
                        
                response = session.post(url, data=post_data, headers=headers, timeout=30)
                if response.status_code != 200:
                    return None
                soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for CAPTCHA image
        captcha_img = soup.find('img', src=re.compile(r'captcha', re.IGNORECASE))
        if not captcha_img:
            # No CAPTCHA needed
            return None
        
        captcha_url = captcha_img.get('src', '')
        if not captcha_url.startswith('http'):
            # Make absolute URL
            captcha_url = f"https://www.keeplinks.org{captcha_url}" if captcha_url.startswith('/') else f"https://www.keeplinks.org/{captcha_url}"
        
        return {
            'captcha_type': 'image',
            'captcha_url': captcha_url,
            'session_cookies': dict(session.cookies),
            'page_url': url,
        }
        
    except Exception as e:
        debug(f"Keeplinks: Error getting CAPTCHA info - {e}")
        return None
