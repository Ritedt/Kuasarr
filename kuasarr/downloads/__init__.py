# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)
#
# Special note: The signatures of all handlers must stay the same so we can neatly call them in download()
# Same is true for every get_xx_download_links() function in sources/xx.py

import json

from kuasarr.downloads.linkcrypters.hide import decrypt_links_if_hide
from kuasarr.downloads.sources.ad import get_ad_download_links
from kuasarr.downloads.sources.al import get_al_download_links
from kuasarr.downloads.sources.by import get_by_download_links
from kuasarr.downloads.sources.dd import get_dd_download_links
from kuasarr.downloads.sources.dt import get_dt_download_links
from kuasarr.downloads.sources.dw import get_dw_download_links
from kuasarr.downloads.sources.he import get_he_download_links
from kuasarr.downloads.sources.mb import get_mb_download_links
from kuasarr.downloads.sources.nk import get_nk_download_links
from kuasarr.downloads.sources.nx import get_nx_download_links
from kuasarr.downloads.sources.dl import get_dl_download_links
from kuasarr.downloads.sources.sf import get_sf_download_links, resolve_sf_redirect
from kuasarr.downloads.sources.sl import get_sl_download_links
from kuasarr.downloads.sources.wd import get_wd_download_links
from kuasarr.downloads.sources.wx import get_wx_download_links
from kuasarr.providers.log import info
from kuasarr.providers.notifications import send_discord_message
from kuasarr.providers.statistics import StatsHelper


def handle_unprotected(shared_state, title, password, package_id, imdb_id, url,
                       mirror=None, size_mb=None, links=None, func=None, label="",
                       destination_folder=None):
    if func:
        links = func(shared_state, url, mirror, title)

    if links:
        info(f"Decrypted {len(links)} download links for {title}")
        send_discord_message(shared_state, title=title, case="unprotected", imdb_id=imdb_id, source=url)
        added = shared_state.download_package(
            links,
            title,
            password,
            package_id,
            destination_folder=destination_folder,
        )
        if not added:
            fail(title, package_id, shared_state,
                 reason=f'Failed to add {len(links)} links for "{title}" to linkgrabber')
            return {"success": False, "title": title}
    else:
        fail(title, package_id, shared_state,
             reason=f'Offline / no links found for "{title}" on {label} - "{url}"')
        return {"success": False, "title": title}

    StatsHelper(shared_state).increment_package_with_links(links)
    return {"success": True, "title": title}


def handle_protected(shared_state, title, password, package_id, imdb_id, url,
                     mirror=None, size_mb=None, func=None, label="", destination_folder=None):
    links = func(shared_state, url, mirror, title)
    if links:
        info(
            f"CAPTCHA-Solution required for \"{title}\" at: \"{shared_state.values['external_address']}/captcha\""
        )
        send_discord_message(shared_state, title=title, case="captcha", imdb_id=imdb_id, source=url)
        blob = json.dumps({
            "title": title,
            "links": links,
            "size_mb": size_mb,
            "password": password,
            "destination_folder": destination_folder,
        })
        shared_state.values["database"]("protected").update_store(package_id, blob)
    else:
        fail(title, package_id, shared_state,
             reason=f'No protected links found for "{title}" on {label} - "{url}"')
        return {"success": False, "title": title}
    return {"success": True, "title": title}


def handle_al(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb, destination_folder=None):
    data = get_al_download_links(shared_state, url, mirror, title, password)
    links = data.get("links", [])
    title = data.get("title", title)
    password = data.get("password", "")
    return handle_unprotected(
        shared_state, title, password, package_id, imdb_id, url,
        links=links,
        label='AL',
        destination_folder=destination_folder,
    )


def handle_by(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb, destination_folder=None):
    """
    Special handler for BY that separates:
    - Direct download links (from hide.cx) -> unprotected
    - Protected links (from filecrypt) -> need CAPTCHA
    """
    links = get_by_download_links(shared_state, url, mirror, title)
    
    if not links:
        fail(title, package_id, shared_state,
             reason=f'No links found for "{title}" on BY - "{url}"')
        return {"success": False, "title": title}
    
    # Separate direct links (strings) from protected links (lists with [url, hostname])
    direct_links = []
    protected_links = []
    
    for link in links:
        if isinstance(link, str):
            # Direct download link (from hide.cx)
            direct_links.append(link)
        elif isinstance(link, list) and len(link) >= 2:
            # Protected link [url, hostname] (from filecrypt)
            protected_links.append(link)
    
    # If we have direct links, download them immediately
    if direct_links:
        info(f"BY: Found {len(direct_links)} direct download links (hide.cx)")
        send_discord_message(shared_state, title=title, case="unprotected", imdb_id=imdb_id, source=url)
        added = shared_state.download_package(
            direct_links,
            title,
            password,
            package_id,
            destination_folder=destination_folder,
        )
        if added:
            StatsHelper(shared_state).increment_package_with_links(direct_links)
            return {"success": True, "title": title}
        else:
            fail(title, package_id, shared_state,
                 reason=f'Failed to add {len(direct_links)} direct links for "{title}" to linkgrabber')
    
    # If we have protected links (filecrypt), queue them for CAPTCHA
    if protected_links:
        info(f"BY: Found {len(protected_links)} protected links (filecrypt) - CAPTCHA required")
        send_discord_message(shared_state, title=title, case="captcha", imdb_id=imdb_id, source=url)
        blob = json.dumps({
            "title": title,
            "links": protected_links,
            "size_mb": size_mb,
            "password": password,
            "destination_folder": destination_folder,
        })
        shared_state.values["database"]("protected").update_store(package_id, blob)
        return {"success": True, "title": title}
    
    # No valid links found
    fail(title, package_id, shared_state,
         reason=f'No valid links found for "{title}" on BY - "{url}"')
    return {"success": False, "title": title}


def handle_ad(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb, destination_folder=None):
    data = get_ad_download_links(shared_state, url, mirror, title)
    if isinstance(data, dict):
        links = data.get("links") or []
        resolved_password = data.get("password")
    else:
        links = list(data) if data else []
        resolved_password = None

    if resolved_password:
        password = resolved_password

    if not links:
        fail(title, package_id, shared_state,
             reason=f'Offline / no links found for "{title}" on AD - "{url}"')
        return {"success": False, "title": title}

    return handle_unprotected(
        shared_state,
        title,
        password,
        package_id,
        imdb_id,
        url,
        links=links,
        label='AD',
        destination_folder=destination_folder,
    )


def handle_sf(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb, destination_folder=None):
    if url.startswith(f"https://{shared_state.values['config']('Hostnames').get('sf')}/external"):
        url = resolve_sf_redirect(url, shared_state.values["user_agent"])
    elif url.startswith(f"https://{shared_state.values['config']('Hostnames').get('sf')}/"):
        data = get_sf_download_links(shared_state, url, mirror, title)
        url = data.get("real_url")
        if not imdb_id:
            imdb_id = data.get("imdb_id")

    if not url:
        fail(title, package_id, shared_state,
             reason=f'Failed to get download link from SF for "{title}" - "{url}"')
        return {"success": False, "title": title}

    return handle_protected(
        shared_state, title, password, package_id, imdb_id, url,
        mirror=mirror,
        size_mb=size_mb,
        func=lambda ss, u, m, t: [[url, "filecrypt"]],
        label='SF',
        destination_folder=destination_folder,
    )


def handle_sl(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb, destination_folder=None):
    data = get_sl_download_links(shared_state, url, mirror, title)
    links = data.get("links")
    if not imdb_id:
        imdb_id = data.get("imdb_id")
    return handle_unprotected(
        shared_state, title, password, package_id, imdb_id, url,
        links=links,
        label='SL',
        destination_folder=destination_folder,
    )


def handle_wd(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb, destination_folder=None):
    data = get_wd_download_links(shared_state, url, mirror, title)
    links = data.get("links")
    if not links:
        fail(title, package_id, shared_state,
             reason=f'Offline / no links found for "{title}" on WD - "{url}"')
        return {"success": False, "title": title}

    decrypted = decrypt_links_if_hide(shared_state, links)
    if decrypted and decrypted.get("status") != "none":
        status = decrypted.get("status", "error")
        links = decrypted.get("results", [])
        if status == "success":
            return handle_unprotected(
                shared_state, title, password, package_id, imdb_id, url,
                links=links, label='WD', destination_folder=destination_folder
            )
        else:
            fail(title, package_id, shared_state,
                 reason=f'Error decrypting hide.cx links for "{title}" on WD - "{url}"')
            return {"success": False, "title": title}

    return handle_protected(
        shared_state, title, password, package_id, imdb_id, url,
        mirror=mirror,
        size_mb=size_mb,
        func=lambda ss, u, m, t: links,
        label='WD',
        destination_folder=destination_folder,
    )


def handle_dl(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb, destination_folder=None):
    """
    Handle DL source downloads.
    Separates:
    - Direct hoster links (rapidgator, ddownload, etc.) -> send to JDownloader immediately
    - Hide.cx links -> decrypt via API (no CAPTCHA needed) -> send to JDownloader
    - Filecrypt links -> queue for CAPTCHA solving
    """
    result = get_dl_download_links(shared_state, url, mirror, title, password)
    
    if not result:
        fail(title, package_id, shared_state,
             reason=f'Offline / no links found for "{title}" on DL - "{url}"')
        return {"success": False, "title": title}
    
    direct_links = result.get("direct") or []
    protected_links = result.get("protected") or []
    resolved_password = result.get("password")

    if resolved_password:
        password = resolved_password

    if not direct_links and not protected_links:
        fail(title, package_id, shared_state,
             reason=f'Offline / no links found for "{title}" on DL - "{url}"')
        return {"success": False, "title": title}

    # Separate links by type:
    # - hide.cx: decrypt via API (no CAPTCHA)
    # - filecrypt/keeplinks: need CAPTCHA solving via Kuasarr DBC
    hide_links = []
    captcha_links = []
    for link_item in protected_links:
        link_url = link_item[0] if isinstance(link_item, list) else link_item
        link_lower = link_url.lower()
        
        if "hide." in link_lower:
            hide_links.append(link_item)
        else:
            # filecrypt and keeplinks need CAPTCHA solving via Kuasarr DBC
            captcha_links.append(link_item)
    
    # Decrypt hide.cx links immediately (no CAPTCHA needed)
    if hide_links:
        info(f"DL: Found {len(hide_links)} hide.cx link(s) - decrypting via API")
        hide_result = decrypt_links_if_hide(shared_state, hide_links)
        status = hide_result.get("status")
        decrypted = hide_result.get("results", [])
        if status == "success" and decrypted:
            direct_links.extend(decrypted)
            info(f"DL: Decrypted {len(decrypted)} links from hide.cx")
        elif status == "none":
            debug("DL: hide.cx decrypt returned none/empty")
        else:
            info("DL: Failed to decrypt hide.cx links; leaving them protected (CAPTCHA queue)")
            captcha_links.extend([l for l in hide_links if l not in captcha_links])

    # If we have direct hoster links (including decrypted hide.cx), send to JDownloader
    if direct_links:
        info(f"DL: Sending {len(direct_links)} link(s) to JDownloader")
        send_discord_message(shared_state, title=title, case="unprotected", imdb_id=imdb_id, source=url)
        added = shared_state.download_package(
            direct_links,
            title,
            password,
            package_id,
            destination_folder=destination_folder,
        )
        if added:
            StatsHelper(shared_state).increment_package_with_links(direct_links)
            return {"success": True, "title": title}
        else:
            fail(title, package_id, shared_state,
                 reason=f'Failed to add {len(direct_links)} links for "{title}" to linkgrabber')
    
    # If we have container links (filecrypt/keeplinks - need CAPTCHA), queue them
    if captcha_links:
        info(f"DL: Found {len(captcha_links)} container link(s) - CAPTCHA required (DBC will solve)")
        send_discord_message(shared_state, title=title, case="captcha", imdb_id=imdb_id, source=url)
        blob = json.dumps({
            "title": title,
            "links": captcha_links,
            "size_mb": size_mb,
            "password": password,
            "destination_folder": destination_folder,
        })
        shared_state.values["database"]("protected").update_store(package_id, blob)
        return {"success": True, "title": title}
    
    # No valid links found
    fail(title, package_id, shared_state,
         reason=f'No valid links found for "{title}" on DL - "{url}"')
    return {"success": False, "title": title}


def download(shared_state, request_from, title, url, mirror, size_mb, password, imdb_id=None,
             destination_folder=None):
    if "lazylibrarian" in request_from.lower():
        category = "docs"
    elif "radarr" in request_from.lower():
        category = "movies"
    else:
        category = "tv"

    package_hash = str(hash(title + url)).replace('-', '')
    package_id = f"kuasarr_{category}_{package_hash}"

    if imdb_id is not None and imdb_id.lower() == "none":
        imdb_id = None

    config = shared_state.values["config"]("Hostnames")
    flags = {
        'AD': config.get("ad"),
        'AL': config.get("al"),
        'BY': config.get("by"),
        'DD': config.get("dd"),
        'DL': config.get("dl"),
        'DT': config.get("dt"),
        'DW': config.get("dw"),
        'HE': config.get("he"),
        'MB': config.get("mb"),
        'NK': config.get("nk"),
        'NX': config.get("nx"),
        'SF': config.get("sf"),
        'SL': config.get("sl"),
        'WD': config.get("wd"),
        'WX': config.get("wx")
    }

    if flags['DL'] and flags['DL'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_dl(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb,
                        destination_folder=destination_folder)
        }

    if flags['AD'] and flags['AD'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_ad(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb,
                        destination_folder=destination_folder)
        }

    if flags['AL'] and flags['AL'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_al(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb,
                        destination_folder=destination_folder)
        }

    if flags['BY'] and flags['BY'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_by(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb,
                        destination_folder=destination_folder)
        }

    if flags['DD'] and flags['DD'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_unprotected(
                shared_state, title, password, package_id, imdb_id, url, mirror=mirror, size_mb=size_mb,
                func=get_dd_download_links, label='DD', destination_folder=destination_folder,
            )
        }

    if flags['DT'] and flags['DT'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_unprotected(
                shared_state, title, password, package_id, imdb_id, url, mirror=mirror, size_mb=size_mb,
                func=get_dt_download_links, label='DT', destination_folder=destination_folder,
            )
        }

    if flags['DW'] and flags['DW'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_protected(
                shared_state, title, password, package_id, imdb_id, url, mirror=mirror, size_mb=size_mb,
                func=get_dw_download_links, label='DW', destination_folder=destination_folder,
            )
        }

    if flags['HE'] and flags['HE'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_unprotected(
                shared_state, title, password, package_id, imdb_id, url, mirror=mirror, size_mb=size_mb,
                func=get_he_download_links, label='HE', destination_folder=destination_folder,
            )
        }

    if flags['MB'] and flags['MB'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_protected(
                shared_state, title, password, package_id, imdb_id, url, mirror=mirror, size_mb=size_mb,
                func=get_mb_download_links, label='MB', destination_folder=destination_folder,
            )
        }

    if flags['NK'] and flags['NK'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_protected(
                shared_state, title, password, package_id, imdb_id, url, mirror=mirror, size_mb=size_mb,
                func=get_nk_download_links, label='NK', destination_folder=destination_folder,
            )
        }

    if flags['NX'] and flags['NX'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_unprotected(
                shared_state, title, password, package_id, imdb_id, url, mirror=mirror, size_mb=size_mb,
                func=get_nx_download_links, label='NX', destination_folder=destination_folder,
            )
        }

    if flags['SF'] and flags['SF'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_sf(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb,
                        destination_folder=destination_folder)
        }

    if flags['SL'] and flags['SL'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_sl(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb,
                        destination_folder=destination_folder)
        }

    if flags['WD'] and flags['WD'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_wd(shared_state, title, password, package_id, imdb_id, url, mirror, size_mb,
                        destination_folder=destination_folder)
        }

    if flags['WX'] and flags['WX'].lower() in url.lower():
        return {
            "package_id": package_id,
            **handle_unprotected(
                shared_state, title, password, package_id, imdb_id, url, mirror=mirror, size_mb=size_mb,
                func=get_wx_download_links, label='WX', destination_folder=destination_folder,
            )
        }

    if "filecrypt" in url.lower():
        return {"package_id": package_id, **handle_protected(
            shared_state, title, password, package_id, imdb_id, url, mirror, size_mb,
            func=lambda ss, u, m, t: [[u, "filecrypt"]],
            label='filecrypt',
            destination_folder=destination_folder,
        )}

    info(f'Could not parse URL for "{title}" - "{url}"')
    StatsHelper(shared_state).increment_failed_downloads()
    return {"success": False, "package_id": package_id, "title": title}


def fail(title, package_id, shared_state, reason="Offline / no links found"):
    try:
        info(f"Reason for failure: {reason}")
        StatsHelper(shared_state).increment_failed_downloads()
        blob = json.dumps({"title": title, "error": reason})
        stored = shared_state.get_db("failed").store(package_id, json.dumps(blob))
        if stored:
            info(f'Package "{title}" marked as failed!"')
            return True
        else:
            info(f'Failed to mark package "{title}" as failed!"')
            return False
    except Exception as e:
        info(f'Error marking package "{package_id}" as failed: {e}')
        return False



