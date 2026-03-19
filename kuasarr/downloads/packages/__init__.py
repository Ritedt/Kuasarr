# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

import json
from collections import defaultdict
from urllib.parse import urlparse

from kuasarr.providers.jd_cache import JDPackageCache
from kuasarr.providers.log import info, debug
from kuasarr.providers.myjd_api import TokenExpiredException, RequestTimeoutException, MYJDException
from kuasarr.providers import shared_state as shared_state_module

# Set zum Tracken bereits verarbeiteter Downloads (verhindert doppeltes Post-Processing)
_processed_downloads = set()


def get_links_comment(package, package_links):
    package_uuid = package.get("uuid")
    if package_uuid and package_links:
        for link in package_links:
            if link.get("packageUUID") == package_uuid:
                return link.get("comment")
    return None


def get_links_status(package, all_links, is_archive=False):
    links_in_package = []
    package_uuid = package.get("uuid")
    if package_uuid and all_links:
        for link in all_links:
            link_package_uuid = link.get("packageUUID")
            if link_package_uuid and link_package_uuid == package_uuid:
                links_in_package.append(link)

    all_finished = True
    eta = None
    error = None

    mirrors = defaultdict(list)
    for link in links_in_package:
        url = link.get("url", "")
        base_domain = urlparse(url).netloc
        mirrors[base_domain].append(link)

    has_mirror_all_online = False
    for mirror_links in mirrors.values():
        if all(link.get('availability', '').lower() == 'online' for link in mirror_links):
            has_mirror_all_online = True
            break

    offline_links = [link for link in links_in_package if link.get('availability', '').lower() == 'offline']
    offline_ids = [link.get('uuid') for link in offline_links]
    offline_mirror_linkids = offline_ids if has_mirror_all_online else []

    for link in links_in_package:
        if link.get('availability', "").lower() == "offline" and not has_mirror_all_online:
            error = "Links offline for all mirrors"
        if link.get('statusIconKey', '').lower() == "false":
            error = "File error in package"
        link_finished = link.get('finished', False)
        link_extraction_status = link.get('extractionStatus', '').lower()  # "error" signifies an issue
        link_eta = link.get('eta', 0) // 1000
        if not link_finished:
            all_finished = False
        elif link_extraction_status and link_extraction_status != 'successful':
            if link_extraction_status == 'error':
                error = link.get('status', '')
            elif link_extraction_status == 'running' and link_eta > 0:
                if eta and link_eta > eta or not eta:
                    eta = link_eta
            all_finished = False
        elif is_archive:
            link_status = link.get('status', '').lower()
            if 'extraction ok' not in link_status and 'entpacken ok' not in link_status:
                # Archiv als nicht fertig behandeln, solange Extraction nicht OK meldet
                all_finished = False

    return {"all_finished": all_finished, "eta": eta, "error": error, "offline_mirror_linkids": offline_mirror_linkids}


def get_links_matching_package_uuid(package, package_links):
    package_uuid = package.get("uuid")
    link_ids = []

    if not isinstance(package_links, list):
        debug("Error - expected a list of package_links, got: %r" % type(package_links).__name__)
        return link_ids

    if package_uuid:
        for link in package_links:
            if link.get("packageUUID") == package_uuid:
                link_ids.append(link.get("uuid"))
    else:
        info("Error - package uuid missing in delete request!")
    return link_ids


def format_eta(seconds):
    if seconds < 0:
        return "23:59:59"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"


def _trigger_postprocessing(storage_path: str, category: str, package_id: str) -> None:
    """
    Triggert Post-Processing für einen abgeschlossenen Download.
    Wird nur einmal pro package_id ausgeführt.
    """
    global _processed_downloads
    
    try:
        from kuasarr.downloads.postprocessing import process_completed_download
        
        info(f"Post-Processing wird gestartet für: {package_id}")
        result = process_completed_download(storage_path, category)
        
        # Markiere als verarbeitet
        _processed_downloads.add(package_id)
        
        # Begrenze die Größe des Sets (behalte nur die letzten 1000)
        if len(_processed_downloads) > 1000:
            # Entferne die ältesten Einträge (Set hat keine Reihenfolge, aber das ist OK)
            excess = len(_processed_downloads) - 500
            for _ in range(excess):
                _processed_downloads.pop()
        
        if result.get("flattened"):
            info(f"Post-Processing: Ordnerstruktur korrigiert für {package_id}")
        if result.get("sonarr_triggered"):
            info(f"Post-Processing: Sonarr Rescan getriggert für {package_id}")
        if result.get("radarr_triggered"):
            info(f"Post-Processing: Radarr Rescan getriggert für {package_id}")
        if result.get("errors"):
            for error in result["errors"]:
                debug(f"Post-Processing Fehler: {error}")
                
    except ImportError as e:
        debug(f"Post-Processing Modul nicht verfügbar: {e}")
    except Exception as e:
        debug(f"Post-Processing Fehler für {package_id}: {e}")
        # Trotzdem als verarbeitet markieren, um Endlosschleifen zu vermeiden
        _processed_downloads.add(package_id)


def get_packages(shared_state, _cache=None):
    """
    Get all packages from protected DB, failed DB, linkgrabber, and downloader.

    Args:
        shared_state: The shared state object
        _cache: INTERNAL USE ONLY. Used by delete_package() to share cached data
                within a single request. External callers should never pass this.
    """
    packages = []

    # Create cache for this request - only valid for duration of this call
    if _cache is None:
        _cache = JDPackageCache(shared_state.get_device())

    cache = _cache  # Use shorter name internally

    protected_packages = shared_state.get_db("protected").retrieve_all_titles()
    if protected_packages:
        for package in protected_packages:
            package_id = package[0]

            data = json.loads(package[1])
            details = {
                "title": data["title"],
                "urls": data["links"],
                "size_mb": data["size_mb"],
                "password": data["password"]
            }

            packages.append({
                "details": details,
                "location": "queue",
                "type": "protected",
                "package_id": package_id
            })

    failed_packages = shared_state.get_db("failed").retrieve_all_titles()
    if failed_packages:
        for package in failed_packages:
            package_id = package[0]

            data = json.loads(package[1])
            try:
                if type(data) is str:
                    data = json.loads(data)
            except json.JSONDecodeError:
                pass
            details = {
                "name": data["title"],
                "bytesLoaded": 0,
                "saveTo": "/"
            }

            error = data.get("error", "Unknown error")

            packages.append({
                "details": details,
                "location": "history",
                "type": "failed",
                "error": error,
                "comment": package_id,
                "uuid": package_id
            })
    # Use cached queries instead of direct API calls
    linkgrabber_packages = cache.linkgrabber_packages
    linkgrabber_links = cache.linkgrabber_links

    if linkgrabber_packages:
        for package in linkgrabber_packages:
            # Use cached linkgrabber_links instead of re-querying
            comment = get_links_comment(package, linkgrabber_links)
            link_details = get_links_status(package, linkgrabber_links)

            error = link_details["error"]
            offline_mirror_linkids = link_details["offline_mirror_linkids"]
            if offline_mirror_linkids:
                shared_state.get_device().linkgrabber.cleanup(
                    "DELETE_OFFLINE",
                    "REMOVE_LINKS_ONLY",
                    "SELECTED",
                    offline_mirror_linkids,
                    [package["uuid"]]
                )

            location = "history" if error else "queue"
            packages.append({
                "details": package,
                "location": location,
                "type": "linkgrabber",
                "comment": comment,
                "uuid": package.get("uuid"),
                "error": error
            })
    # Use cached queries instead of direct API calls
    downloader_packages = cache.downloader_packages
    downloader_links = cache.downloader_links

    # Get archive package UUIDs using cached method
    archive_package_uuids = cache.get_archive_package_uuids(downloader_packages, downloader_links)

    if downloader_packages and downloader_links:
        for package in downloader_packages:
            comment = get_links_comment(package, downloader_links)

            # Use cached archive detection instead of per-package API call
            is_archive = package.get("uuid") in archive_package_uuids

            link_details = get_links_status(package, downloader_links, is_archive)

            error = link_details["error"]
            finished = link_details["all_finished"]
            if not finished and link_details["eta"]:
                package["eta"] = link_details["eta"]

            # Zusatz-Check: Download fertig, wenn Bytes voll und kein ETA
            # Markiere nur als fertig, wenn sicher kein Archiv bzw. Archiv nicht erkannt
            if not finished and not error:
                bytes_total = int(package.get("bytesTotal", 0))
                bytes_loaded = int(package.get("bytesLoaded", 0))
                eta = package.get("eta")
                if bytes_total > 0 and bytes_loaded >= bytes_total and eta is None:
                    if not is_archive:
                        finished = True

            # Post-Processing SOFORT wenn Download fertig ist (bevor Sonarr/Radarr reagiert)
            if finished and not error and comment and comment.startswith("kuasarr_"):
                if comment not in _processed_downloads:
                    storage_path = package.get("saveTo", "")
                    if "movies" in comment:
                        category = "movies"
                    elif "docs" in comment:
                        category = "docs"
                    else:
                        category = "tv"
                    _trigger_postprocessing(storage_path, category, comment)

            location = "history" if error or finished else "queue"

            packages.append({
                "details": package,
                "location": location,
                "type": "downloader",
                "comment": comment,
                "uuid": package.get("uuid"),
                "error": error
            })

    downloads = {
        "queue": [],
        "history": []
    }
    for package in packages:
        queue_index = 0
        history_index = 0

        package_id = None

        if package["location"] == "queue":
            time_left = "23:59:59"
            if package["type"] == "linkgrabber":
                details = package["details"]
                name = f"[Linkgrabber] {details['name']}"
                try:
                    mb = mb_left = int(details["bytesTotal"]) / (1024 * 1024)
                except KeyError:
                    mb = mb_left = 0
                try:
                    package_id = package["comment"]
                    if "movies" in package_id:
                        category = "movies"
                    elif "docs" in package_id:
                        category = "docs"
                    else:
                        category = "tv"
                except TypeError:
                    category = "not_quasarr"
                package_type = "linkgrabber"
                package_uuid = package["uuid"]
            elif package["type"] == "downloader":
                details = package["details"]
                status = "Downloading"
                eta = details.get("eta")
                bytes_total = int(details.get("bytesTotal", 0))
                bytes_loaded = int(details.get("bytesLoaded", 0))

                mb = bytes_total / (1024 * 1024)
                mb_left = (bytes_total - bytes_loaded) / (1024 * 1024) if bytes_total else 0
                if mb_left < 0:
                    mb_left = 0

                if mb_left == 0:
                    status = "Extracting"
                elif eta is None:
                    status = "Paused"
                else:
                    time_left = format_eta(int(eta))

                name = f"[{status}] {details['name']}"

                try:
                    package_id = package["comment"]
                    if "movies" in package_id:
                        category = "movies"
                    elif "docs" in package_id:
                        category = "docs"
                    else:
                        category = "tv"
                except TypeError:
                    category = "not_quasarr"
                package_type = "downloader"
                package_uuid = package["uuid"]
            else:
                details = package["details"]
                name = f"[CAPTCHA not solved!] {details['title']}"
                mb = mb_left = details["size_mb"]
                try:
                    package_id = package["package_id"]
                    if "movies" in package_id:
                        category = "movies"
                    elif "docs" in package_id:
                        category = "docs"
                    else:
                        category = "tv"
                except TypeError:
                    category = "not_quasarr"
                package_type = "protected"
                package_uuid = None

            try:
                if package_id:
                    mb_left = int(mb_left)
                    mb = int(mb)
                    try:
                        percentage = int(100 * (mb - mb_left) / mb)
                    except ZeroDivisionError:
                        percentage = 0

                    downloads["queue"].append({
                        "index": queue_index,
                        "nzo_id": package_id,
                        "priority": "Normal",
                        "filename": name,
                        "cat": category,
                        "mbleft": mb_left,
                        "mb": mb,
                        "status": "Downloading",
                        "percentage": percentage,
                        "timeleft": time_left,
                        "type": package_type,
                        "uuid": package_uuid
                    })
            except:
                debug(f"Parameters missing for {package}")
            queue_index += 1
        elif package["location"] == "history":
            details = package["details"]
            name = details["name"]
            try:
                size = int(details["bytesLoaded"])
            except KeyError:
                size = 0
            storage = details["saveTo"]
            try:
                package_id = package["comment"]
                if "movies" in package_id:
                    category = "movies"
                elif "docs" in package_id:
                    category = "docs"
                else:
                    category = "tv"
            except TypeError:
                category = "not_quasarr"

            error = package.get("error")
            fail_message = ""
            if error:
                status = "Failed"
                fail_message = error
            else:
                status = "Completed"
                # Fallback: Post-Processing falls im Downloader-Status verpasst
                if package_id and package_id.startswith("kuasarr_") and package_id not in _processed_downloads:
                    _trigger_postprocessing(storage, category, package_id)

            downloads["history"].append({
                "fail_message": fail_message,
                "category": category,
                "storage": storage,
                "status": status,
                "nzo_id": package_id,
                "name": name,
                "bytes": int(size),
                "percentage": 100,
                "type": "downloader",
                "uuid": package["uuid"]
            })
            history_index += 1
        else:
            info(f"Invalid package location {package['location']}")

    if shared_state_module.is_linkgrabber_start_due() and not cache.is_collecting:
        # Re-use cached data
        linkgrabber_packages = cache.linkgrabber_packages
        linkgrabber_links = cache.linkgrabber_links

        packages_to_start = []
        links_to_start = []

        for package in linkgrabber_packages:
            # Use cached linkgrabber_links
            comment = get_links_comment(package, linkgrabber_links)
            if comment and comment.startswith("kuasarr_"):
                package_uuid = package.get("uuid")
                if package_uuid:
                    linkgrabber_links = [link.get("uuid") for link in linkgrabber_links if
                                         link.get("packageUUID") == package_uuid]
                    if linkgrabber_links:
                        packages_to_start.append(package_uuid)
                        links_to_start.extend(linkgrabber_links)
                    else:
                        info(f"Package {package_uuid} has no links in linkgrabber - skipping start")

                    break

        if packages_to_start and links_to_start:
            info(
                "JDownloader Linkgrabber → Downloadliste: übertrage %s (links=%s)"
                % (packages_to_start, len(links_to_start))
            )
            shared_state.get_device().linkgrabber.move_to_downloadlist(links_to_start, packages_to_start)
            info(
                f"Started {len(packages_to_start)} package download"
                f"{'s' if len(packages_to_start) > 1 else ''} from linkgrabber"
            )
        else:
            debug("JDownloader: keine Quasarr-Pakete im Linkgrabber zum Starten gefunden")

        shared_state_module.complete_linkgrabber_start_check()

    return downloads


def delete_package(shared_state, package_id):
    try:
        deleted_title = ""

        packages = get_packages(shared_state)
        for package_location in packages:
            for package in packages[package_location]:
                if package["nzo_id"] == package_id:
                    if package["type"] == "linkgrabber":
                        ids = get_links_matching_package_uuid(package,
                                                              shared_state.get_device().linkgrabber.query_links())
                        if ids:
                            shared_state.get_device().linkgrabber.cleanup(
                                "DELETE_ALL",
                                "REMOVE_LINKS_AND_DELETE_FILES",
                                "SELECTED",
                                ids,
                                [package["uuid"]]
                            )
                            break
                    elif package["type"] == "downloader":
                        ids = get_links_matching_package_uuid(package,
                                                              shared_state.get_device().downloads.query_links())
                        if ids:
                            shared_state.get_device().downloads.cleanup(
                                "DELETE_ALL",
                                "REMOVE_LINKS_AND_DELETE_FILES",
                                "SELECTED",
                                ids,
                                [package["uuid"]]
                            )
                            break

                    # no state check, just clean up whatever exists with the package id
                    shared_state.get_db("failed").delete(package_id)
                    shared_state.get_db("protected").delete(package_id)

                    if package_location == "queue":
                        package_name_field = "filename"
                    else:
                        package_name_field = "name"

                    try:
                        deleted_title = package[package_name_field]
                    except KeyError:
                        pass

                    # Leave the loop
                    break

        if deleted_title:
            info(f'Deleted package "{deleted_title}" with ID "{package_id}"')
        else:
            info(f'Deleted package "{package_id}"')
    except:
        info(f"Failed to delete package {package_id}")
        return False
    return True
