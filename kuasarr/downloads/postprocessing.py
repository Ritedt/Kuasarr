# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""
Post-Processing Modul für Downloads.
- Erkennt und korrigiert verschachtelte Ordnerstrukturen
- Triggert Sonarr/Radarr Rescan via API
"""

import os
import re
import shutil
from pathlib import Path
from typing import Optional, List, Tuple

import requests

from kuasarr.providers.log import info, debug
from kuasarr.storage.config import Config


def get_postprocessing_config() -> dict:
    """Lädt die Post-Processing Konfiguration."""
    try:
        pp_config = Config('PostProcessing')
        return {
            "flatten_nested_folders": pp_config.get("flatten_nested_folders"),
            "trigger_rescan": pp_config.get("trigger_rescan")
        }
    except Exception as e:
        debug(f"PostProcessing Config nicht verfügbar: {e}")
        return {
            "flatten_nested_folders": True,
            "trigger_rescan": True
        }


def get_sonarr_config() -> dict:
    """Lädt die Sonarr Konfiguration."""
    try:
        sonarr_config = Config('Sonarr')
        return {
            "url": sonarr_config.get("url"),
            "api_key": sonarr_config.get("api_key")
        }
    except Exception:
        return {"url": "", "api_key": ""}


def get_radarr_config() -> dict:
    """Lädt die Radarr Konfiguration."""
    try:
        radarr_config = Config('Radarr')
        return {
            "url": radarr_config.get("url"),
            "api_key": radarr_config.get("api_key")
        }
    except Exception:
        return {"url": "", "api_key": ""}


def normalize_folder_name(name: str) -> str:
    """
    Normalisiert einen Ordnernamen für Vergleiche.
    Ersetzt Punkte/Unterstriche durch Leerzeichen und macht lowercase.
    """
    # Ersetze Punkte und Unterstriche durch Leerzeichen
    normalized = re.sub(r'[._]', ' ', name)
    # Entferne mehrfache Leerzeichen
    normalized = re.sub(r'\s+', ' ', normalized)
    # Lowercase und strip
    return normalized.lower().strip()


def is_nested_duplicate(parent_name: str, child_name: str) -> bool:
    """
    Prüft ob ein Unterordner eine Duplikat-Verschachtelung ist.
    
    Beispiele:
    - "Movie Name 2024" / "Movie.Name.2024" → True
    - "Movie Name 2024" / "Movie.Name.2024.1080p" → True (Teilmatch)
    - "Movie Name 2024" / "Extras" → False
    """
    parent_norm = normalize_folder_name(parent_name)
    child_norm = normalize_folder_name(child_name)
    
    # Exakter Match nach Normalisierung
    if parent_norm == child_norm:
        return True
    
    # Einer ist Präfix des anderen (für Fälle wie "Movie" / "Movie 1080p")
    if parent_norm.startswith(child_norm) or child_norm.startswith(parent_norm):
        # Mindestens 80% Übereinstimmung
        min_len = min(len(parent_norm), len(child_norm))
        max_len = max(len(parent_norm), len(child_norm))
        if min_len / max_len > 0.7:
            return True
    
    return False


def find_nested_structure(base_path: str) -> Tuple[Optional[str], List[str]]:
    """
    Findet verschachtelte Ordnerstrukturen und gibt den tiefsten Ordner mit Dateien zurück.
    
    Returns:
        Tuple von (deepest_folder_with_files, list_of_files_to_move)
    """
    base = Path(base_path)
    
    if not base.exists() or not base.is_dir():
        return None, []
    
    # Sammle alle Dateien im Basisordner
    base_files = [f for f in base.iterdir() if f.is_file()]
    subdirs = [d for d in base.iterdir() if d.is_dir()]
    
    # Wenn Dateien im Basisordner sind, keine Verschachtelung
    if base_files:
        return None, []
    
    # Wenn kein oder mehr als ein Unterordner, keine einfache Verschachtelung
    if len(subdirs) != 1:
        return None, []
    
    subdir = subdirs[0]
    
    # Prüfe ob Unterordner ein Duplikat ist
    if not is_nested_duplicate(base.name, subdir.name):
        return None, []
    
    # Rekursiv weiter prüfen
    deeper_path, deeper_files = find_nested_structure(str(subdir))
    
    if deeper_path:
        return deeper_path, deeper_files
    
    # Dieser Unterordner ist der tiefste mit Dateien
    files_in_subdir = list(subdir.glob('*'))
    if files_in_subdir:
        return str(subdir), [str(f) for f in files_in_subdir]
    
    return None, []


def flatten_nested_folders(download_path: str) -> bool:
    """
    Korrigiert verschachtelte Ordnerstrukturen.
    
    Beispiel:
    /downloads/Movie Name 2024/Movie.Name.2024/Movie.Name.2024.mkv
    → /downloads/Movie Name 2024/Movie.Name.2024.mkv
    
    Returns:
        True wenn Änderungen vorgenommen wurden
    """
    if not download_path or not os.path.exists(download_path):
        debug(f"PostProcessing: Pfad existiert nicht: {download_path}")
        return False
    
    base = Path(download_path)
    changes_made = False
    
    # Finde verschachtelte Struktur
    nested_path, files_to_move = find_nested_structure(download_path)
    
    if not nested_path or not files_to_move:
        debug(f"PostProcessing: Keine Verschachtelung gefunden in {download_path}")
        return False
    
    nested = Path(nested_path)
    info(f"PostProcessing: Verschachtelung erkannt: {nested_path}")
    
    # Verschiebe alle Dateien nach oben
    for file_path in files_to_move:
        src = Path(file_path)
        dst = base / src.name
        
        if src.is_file():
            try:
                if dst.exists():
                    debug(f"PostProcessing: Ziel existiert bereits: {dst}")
                    continue
                    
                shutil.move(str(src), str(dst))
                info(f"PostProcessing: Verschoben: {src.name} → {base.name}/")
                changes_made = True
            except Exception as e:
                debug(f"PostProcessing: Fehler beim Verschieben von {src}: {e}")
        elif src.is_dir():
            # Unterordner auch verschieben (z.B. "Subs" Ordner)
            try:
                if dst.exists():
                    debug(f"PostProcessing: Zielordner existiert bereits: {dst}")
                    continue
                    
                shutil.move(str(src), str(dst))
                info(f"PostProcessing: Ordner verschoben: {src.name} → {base.name}/")
                changes_made = True
            except Exception as e:
                debug(f"PostProcessing: Fehler beim Verschieben von Ordner {src}: {e}")
    
    # Lösche leere Unterordner
    if changes_made:
        _cleanup_empty_dirs(download_path)
    
    return changes_made


def _cleanup_empty_dirs(base_path: str) -> None:
    """Löscht leere Unterordner rekursiv."""
    base = Path(base_path)
    
    for dirpath, dirnames, filenames in os.walk(str(base), topdown=False):
        current = Path(dirpath)
        
        # Überspringe den Basisordner selbst
        if current == base:
            continue
        
        # Prüfe ob Ordner leer ist
        try:
            if not any(current.iterdir()):
                current.rmdir()
                info(f"PostProcessing: Leerer Ordner gelöscht: {current.name}")
        except Exception as e:
            debug(f"PostProcessing: Fehler beim Löschen von {current}: {e}")


def trigger_sonarr_rescan(download_path: str) -> bool:
    """
    Triggert einen Sonarr Download-Scan.
    
    Returns:
        True wenn erfolgreich
    """
    config = get_sonarr_config()
    
    if not config["url"] or not config["api_key"]:
        debug("PostProcessing: Sonarr nicht konfiguriert")
        return False
    
    url = config["url"].rstrip('/')
    api_key = config["api_key"]
    
    try:
        # Trigger DownloadedEpisodesScan Command
        response = requests.post(
            f"{url}/api/v3/command",
            json={
                "name": "DownloadedEpisodesScan",
                "path": download_path
            },
            headers={"X-Api-Key": api_key},
            timeout=30
        )
        
        if response.status_code in (200, 201):
            info(f"PostProcessing: Sonarr Rescan getriggert für {download_path}")
            return True
        else:
            debug(f"PostProcessing: Sonarr Rescan fehlgeschlagen: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        debug(f"PostProcessing: Sonarr API Fehler: {e}")
        return False


def trigger_radarr_rescan(download_path: str) -> bool:
    """
    Triggert einen Radarr Download-Scan.
    
    Returns:
        True wenn erfolgreich
    """
    config = get_radarr_config()
    
    if not config["url"] or not config["api_key"]:
        debug("PostProcessing: Radarr nicht konfiguriert")
        return False
    
    url = config["url"].rstrip('/')
    api_key = config["api_key"]
    
    try:
        # Trigger DownloadedMoviesScan Command
        response = requests.post(
            f"{url}/api/v3/command",
            json={
                "name": "DownloadedMoviesScan",
                "path": download_path
            },
            headers={"X-Api-Key": api_key},
            timeout=30
        )
        
        if response.status_code in (200, 201):
            info(f"PostProcessing: Radarr Rescan getriggert für {download_path}")
            return True
        else:
            debug(f"PostProcessing: Radarr Rescan fehlgeschlagen: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        debug(f"PostProcessing: Radarr API Fehler: {e}")
        return False


def process_completed_download(download_path: str, category: str) -> dict:
    """
    Führt Post-Processing für einen abgeschlossenen Download durch.
    
    Args:
        download_path: Pfad zum Download-Ordner
        category: Kategorie des Downloads ("movies", "tv", "docs")
    
    Returns:
        Dict mit Ergebnissen
    """
    result = {
        "flattened": False,
        "sonarr_triggered": False,
        "radarr_triggered": False,
        "errors": []
    }
    
    config = get_postprocessing_config()
    
    if not download_path:
        result["errors"].append("Kein Download-Pfad angegeben")
        return result
    
    info(f"PostProcessing: Starte für {download_path} (Kategorie: {category})")
    
    # 1. Ordner-Flattening
    if config["flatten_nested_folders"]:
        try:
            result["flattened"] = flatten_nested_folders(download_path)
        except Exception as e:
            error_msg = f"Flattening fehlgeschlagen: {e}"
            debug(f"PostProcessing: {error_msg}")
            result["errors"].append(error_msg)
    
    # 2. Rescan triggern
    if config["trigger_rescan"]:
        try:
            if category == "movies":
                result["radarr_triggered"] = trigger_radarr_rescan(download_path)
            elif category in ("tv", "docs"):
                result["sonarr_triggered"] = trigger_sonarr_rescan(download_path)
            else:
                # Versuche beide
                result["radarr_triggered"] = trigger_radarr_rescan(download_path)
                result["sonarr_triggered"] = trigger_sonarr_rescan(download_path)
        except Exception as e:
            error_msg = f"Rescan-Trigger fehlgeschlagen: {e}"
            debug(f"PostProcessing: {error_msg}")
            result["errors"].append(error_msg)
    
    return result
