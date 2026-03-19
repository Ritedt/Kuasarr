# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""
JDownloader connection and device management.
"""

import json
import time

import kuasarr
from kuasarr.providers import shared_state
from kuasarr.providers.log import info
from kuasarr.providers.myjd_api import (
    Myjdapi,
    TokenExpiredException,
    RequestTimeoutException,
    MYJDException,
    Jddevice,
)
from kuasarr.storage.config import Config

__all__ = [
    "connect_to_jd",
    "set_device",
    "set_device_from_config",
    "check_device",
    "connect_device",
    "get_device",
    "get_devices",
    "set_device_settings",
    "update_jdownloader",
    "start_downloads",
    "schedule_linkgrabber_start",
    "is_linkgrabber_start_due",
    "complete_linkgrabber_start_check",
]


def connect_to_jd(jd, user, password, device_name):
    """Connect to JDownloader and return True on success."""
    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            jd.connect(user, password)
            jd.update_devices()
            device = jd.get_device(device_name)
        except (TokenExpiredException, RequestTimeoutException, MYJDException) as e:
            msg = str(e).strip().lower()
            info("Error connecting to JDownloader: " + str(e).strip())
            # Simple maintenance/offline backoff
            if "maintenance" in msg or "offline" in msg:
                info("JDownloader API appears offline/maintenance - waiting 60s before retry")
                time.sleep(60)
                continue
            return False
        break
    if not device or not isinstance(device, (type, Jddevice)):
        info(f'Device "{device_name}" not found. Available devices may differ or be offline.')
        return False
    else:
        device.downloadcontroller.get_current_state()
        connection_info = device.check_direct_connection()
        if connection_info["status"]:
            info(f"Direct connection to JDownloader established: \"{connection_info['ip']}\"")
        else:
            info("Could not establish direct connection to JDownloader.")
        shared_state.update("device", device)
        return True


def set_device(user, password, device):
    """Set device credentials and connect."""
    jd = Myjdapi()
    jd.set_app_key('kuasarr')
    return connect_to_jd(jd, user, password, device)


def set_device_from_config():
    """Load device credentials from config and connect."""
    config = Config('JDownloader')
    user = str(config.get('user'))
    password = str(config.get('password'))
    device = str(config.get('device'))

    shared_state.update("device", device)

    if user and password and device:
        jd = Myjdapi()
        jd.set_app_key('kuasarr')
        return connect_to_jd(jd, user, password, device)
    return False


def check_device(device):
    """Check if device connection is valid."""
    try:
        valid = isinstance(device, (type, Jddevice)) and device.downloadcontroller.get_current_state()
    except (AttributeError, KeyError, TokenExpiredException, RequestTimeoutException, MYJDException):
        valid = False
    return valid


def connect_device():
    """Reconnect to device using stored config."""
    config = Config('JDownloader')
    user = str(config.get('user'))
    password = str(config.get('password'))
    device = str(config.get('device'))

    jd = Myjdapi()
    jd.set_app_key('kuasarr')

    if user and password and device:
        try:
            jd.connect(user, password)
            jd.update_devices()
            device = jd.get_device(device)
        except (TokenExpiredException, RequestTimeoutException, MYJDException):
            pass

    if check_device(device):
        shared_state.update("device", device)
        return True
    else:
        return False


def schedule_linkgrabber_start(delay_seconds=30):
    """Schedule a single automatic Linkgrabber→Downloadliste transfer attempt."""
    shared_state.update("linkgrabber_check_time", time.time() + delay_seconds)
    shared_state.update("linkgrabber_check_pending", True)


def is_linkgrabber_start_due():
    """Return True if a scheduled Linkgrabber start check is pending and due."""
    pending = shared_state.values.get("linkgrabber_check_pending", False)
    check_time = shared_state.values.get("linkgrabber_check_time", 0)
    return pending and check_time and time.time() >= check_time


def complete_linkgrabber_start_check():
    """Mark the scheduled Linkgrabber start check as completed."""
    shared_state.update("linkgrabber_check_pending", False)


def get_device():
    """Get device, reconnecting if necessary."""
    attempts = 0

    while True:
        try:
            if check_device(shared_state.values["device"]):
                break
        except (AttributeError, KeyError, TokenExpiredException, RequestTimeoutException, MYJDException):
            pass
        attempts += 1

        shared_state.update("device", False)

        if attempts % 10 == 0:
            info(f"WARNING: {attempts} consecutive JDownloader connection errors. Please check your credentials!")
        time.sleep(3)

        if connect_device():
            break

    return shared_state.values["device"]


def get_devices(user, password):
    """Get list of available devices for given credentials."""
    jd = Myjdapi()
    jd.set_app_key('kuasarr')
    try:
        jd.connect(user, password)
        jd.update_devices()
        devices = jd.list_devices()
        return devices
    except (TokenExpiredException, RequestTimeoutException, MYJDException) as e:
        info("Error connecting to JDownloader: " + str(e))
        return []


def set_device_settings():
    """Configure JDownloader settings for optimal kuasarr operation."""
    device = get_device()

    settings_to_enforce = [
        {
            "namespace": "org.jdownloader.settings.GeneralSettings",
            "storage": None,
            "setting": "AutoStartDownloadOption",
            "expected_value": "ALWAYS",
        },
        {
            "namespace": "org.jdownloader.settings.GeneralSettings",
            "storage": None,
            "setting": "IfFileExistsAction",
            "expected_value": "SKIP_FILE",
        },
        {
            "namespace": "org.jdownloader.settings.GeneralSettings",
            "storage": None,
            "setting": "CleanupAfterDownloadAction",
            "expected_value": "NEVER",
        },
        {
            "namespace": "org.jdownloader.settings.GraphicalUserInterfaceSettings",
            "storage": None,
            "setting": "BannerEnabled",
            "expected_value": False,
        },
        {
            "namespace": "org.jdownloader.settings.GraphicalUserInterfaceSettings",
            "storage": None,
            "setting": "DonateButtonState",
            "expected_value": "CUSTOM_HIDDEN",
        },
        {
            "namespace": "org.jdownloader.extensions.extraction.ExtractionConfig",
            "storage": "cfg/org.jdownloader.extensions.extraction.ExtractionExtension",
            "setting": "DeleteArchiveFilesAfterExtractionAction",
            "expected_value": "NULL",
        },
        {
            "namespace": "org.jdownloader.extensions.extraction.ExtractionConfig",
            "storage": "cfg/org.jdownloader.extensions.extraction.ExtractionExtension",
            "setting": "IfFileExistsAction",
            "expected_value": "OVERWRITE_FILE",
        },
        {
            "namespace": "org.jdownloader.extensions.extraction.ExtractionConfig",
            "storage": "cfg/org.jdownloader.extensions.extraction.ExtractionExtension",
            "setting": "DeleteArchiveDownloadlinksAfterExtraction",
            "expected_value": False,
        },
        {
            "namespace": "org.jdownloader.gui.views.linkgrabber.addlinksdialog.LinkgrabberSettings",
            "storage": None,
            "setting": "OfflinePackageEnabled",
            "expected_value": False,
        },
        {
            "namespace": "org.jdownloader.gui.views.linkgrabber.addlinksdialog.LinkgrabberSettings",
            "storage": None,
            "setting": "HandleOfflineOnConfirmLatestSelection",
            "expected_value": "INCLUDE_OFFLINE",
        },
        {
            "namespace": "org.jdownloader.gui.views.linkgrabber.addlinksdialog.LinkgrabberSettings",
            "storage": None,
            "setting": "AutoConfirmManagerHandleOffline",
            "expected_value": "INCLUDE_OFFLINE",
        },
        {
            "namespace": "org.jdownloader.gui.views.linkgrabber.addlinksdialog.LinkgrabberSettings",
            "storage": None,
            "setting": "DefaultOnAddedOfflineLinksAction",
            "expected_value": "INCLUDE_OFFLINE",
        },
    ]

    for setting in settings_to_enforce:
        namespace = setting["namespace"]
        storage = setting["storage"] or "null"
        name = setting["setting"]
        expected_value = setting["expected_value"]

        settings = device.config.get(namespace, storage, name)

        if settings != expected_value:
            success = device.config.set(namespace, storage, name, expected_value)
            location = f"{namespace}/{storage}" if storage != "null" else namespace
            status = "Updated" if success else "Failed to update"
            info(f'{status} "{name}" in "{location}" to "{expected_value}".')

    settings_to_add = [
        {
            "namespace": "org.jdownloader.extensions.extraction.ExtractionConfig",
            "storage": "cfg/org.jdownloader.extensions.extraction.ExtractionExtension",
            "setting": "BlacklistPatterns",
            "expected_values": [
                '.*sample/.*', '.*Sample/.*', '.*\\.jpe?g', '.*\\.idx',
                '.*\\.sub', '.*\\.srt', '.*\\.nfo', '.*\\.bat',
                '.*\\.txt', '.*\\.exe', '.*\\.sfv'
            ]
        },
        {
            "namespace": "org.jdownloader.controlling.filter.LinkFilterSettings",
            "storage": "null",
            "setting": "FilterList",
            "expected_values": [
                {
                    'conditionFilter': {'conditions': [], 'enabled': False, 'matchType': 'IS_TRUE'},
                    'created': 0,
                    'enabled': True,
                    'filenameFilter': {
                        'enabled': True,
                        'matchType': 'CONTAINS',
                        'regex': '.*\\.(sfv|jpe?g|idx|srt|nfo|bat|txt|exe)',
                        'useRegex': True
                    },
                    'filesizeFilter': {'enabled': False, 'from': 0, 'matchType': 'BETWEEN', 'to': 0},
                    'filetypeFilter': {
                        'archivesEnabled': False, 'audioFilesEnabled': False, 'customs': None,
                        'docFilesEnabled': False, 'enabled': False, 'exeFilesEnabled': False,
                        'hashEnabled': False, 'imagesEnabled': False, 'matchType': 'IS',
                        'subFilesEnabled': False, 'useRegex': False, 'videoFilesEnabled': False
                    },
                    'hosterURLFilter': {'enabled': False, 'matchType': 'CONTAINS', 'regex': '', 'useRegex': False},
                    'matchAlwaysFilter': {'enabled': False},
                    'name': 'kuasarr_Block_Files',
                    'onlineStatusFilter': {'enabled': False, 'matchType': 'IS', 'onlineStatus': 'OFFLINE'},
                    'originFilter': {'enabled': False, 'matchType': 'IS', 'origins': []},
                    'packagenameFilter': {'enabled': False, 'matchType': 'CONTAINS', 'regex': '', 'useRegex': False},
                    'pluginStatusFilter': {'enabled': False, 'matchType': 'IS', 'pluginStatus': 'PREMIUM'},
                    'sourceURLFilter': {'enabled': False, 'matchType': 'CONTAINS', 'regex': '', 'useRegex': False},
                    'testUrl': ''
                }
            ]
        },
    ]

    for setting in settings_to_add:
        namespace = setting["namespace"]
        storage = setting["storage"] or "null"
        name = setting["setting"]
        expected_values = setting["expected_values"]

        added_items = 0
        settings = device.config.get(namespace, storage, name)
        for item in expected_values:
            if item not in settings:
                settings.append(item)
                added_items += 1

        if added_items:
            success = device.config.set(namespace, storage, name, json.dumps(settings))
            location = f"{namespace}/{storage}" if storage != "null" else namespace
            status = "Added" if success else "Failed to add"
            info(f'{status} {added_items} items to "{name}" in "{location}".')


def update_jdownloader():
    """Check for and apply JDownloader updates."""
    try:
        if not get_device():
            set_device_from_config()
        device = get_device()

        if device:
            try:
                current_state = device.downloadcontroller.get_current_state()
                is_collecting = device.linkgrabber.is_collecting()
                update_available = device.update.update_available()

                if (current_state.lower() == "idle") and (not is_collecting and update_available):
                    info("JDownloader update ready. Starting update...")
                    device.update.restart_and_update()
            except kuasarr.providers.myjd_api.TokenExpiredException:
                return False
            return True
        else:
            return False
    except kuasarr.providers.myjd_api.MYJDException as e:
        info(f"Error updating JDownloader: {e}")
        return False


def start_downloads():
    """Start downloads in JDownloader."""
    try:
        if not get_device():
            set_device_from_config()
        device = get_device()

        if device:
            try:
                return device.downloadcontroller.start_downloads()
            except kuasarr.providers.myjd_api.TokenExpiredException:
                return False
        else:
            return False
    except kuasarr.providers.myjd_api.MYJDException as e:
        info(f"Error starting Downloads: {e}")
        return False
