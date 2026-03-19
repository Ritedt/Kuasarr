# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

from kuasarr.providers.log import info, debug
from kuasarr.providers.sessions.dd import create_and_persist_session, retrieve_and_validate_session


def get_dd_download_links(shared_state, url, mirror, title): # signature must align with other download link functions!
    dd = shared_state.values["config"]("Hostnames").get("dd")

    dd_session = retrieve_and_validate_session(shared_state)
    if not dd_session:
        info(f"Could not retrieve valid session for {dd}")
        return []

    links = []

    qualities = [
        "disk-480p",
        "web-480p",
        "movie-480p-x265",
        "disk-1080p-x265",
        "web-1080p",
        "web-1080p-x265",
        "web-2160p-x265-hdr",
        "movie-1080p-x265",
        "movie-2160p-webdl-x265-hdr"
    ]

    headers = {
        'User-Agent': shared_state.values["user_agent"],
    }

    try:
        release_list = []
        qualities_param = ",".join(qualities)
        for page in range(0, 100, 20):
            url = f"https://{dd}/index/search/keyword/{title}/qualities/{qualities_param}/from/{page}/search"

            releases_on_page = dd_session.get(url, headers=headers, timeout=10).json()
            if releases_on_page:
                release_list.extend(releases_on_page)

        for release in release_list:
            try:
                if release.get("fake"):
                    debug(f"Release {release.get('release')} marked as fake. Invalidating DD session...")
                    create_and_persist_session(shared_state)
                    return []
                elif release.get("release") == title:
                    filtered_links = []
                    for link in release["links"]:
                        if mirror and mirror not in link["hostname"]:
                            debug(f'Skipping link from "{link["hostname"]}" (not the desired mirror "{mirror}")!')
                            continue

                        if any(
                                existing_link["hostname"] == link["hostname"] and
                                existing_link["url"].endswith(".mkv") and
                                link["url"].endswith(".mkv")
                                for existing_link in filtered_links
                        ):
                            debug(f"Skipping duplicate `.mkv` link from {link['hostname']}")
                            continue  # Skip adding duplicate `.mkv` links from the same hostname
                        filtered_links.append(link)

                    links = [link["url"] for link in filtered_links]
                    break
            except Exception as e:
                info(f"Error parsing DD download: {e}")
                continue

    except Exception as e:
        info(f"Error loading DD download: {e}")

    return links



