#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Container Module fÃ¼r kuasarr Storage

import os
import json
from pathlib import Path

def get_movies(storage_path):
    """
    LÃ¤dt Filme-Informationen aus dem angegebenen Storage-Pfad
    
    Args:
        storage_path (str): Pfad zum Storage-Verzeichnis
        
    Returns:
        list: Liste der Filme oder leere Liste
    """
    if not storage_path:
        return []
    
    try:
        # Stelle sicher, dass der Pfad existiert
        storage_dir = Path(storage_path)
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Suche nach Movie-Dateien oder -Verzeichnissen
        movies = []
        
        # Verschiedene Dateierweiterungen fÃ¼r Videos
        video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        
        if storage_dir.exists() and storage_dir.is_dir():
            for item in storage_dir.iterdir():
                if item.is_file():
                    # Direkte Video-Dateien
                    if item.suffix.lower() in video_extensions:
                        movies.append({
                            'title': item.stem,
                            'path': str(item),
                            'size': item.stat().st_size,
                            'type': 'file'
                        })
                elif item.is_dir():
                    # Verzeichnisse (mÃ¶glicherweise Movie-Ordner)
                    movies.append({
                        'title': item.name,
                        'path': str(item),
                        'type': 'directory'
                    })
        
        return movies
        
    except Exception as e:
        print(f"Error loading movies from {storage_path}: {e}")
        return []

def get_tv_shows(storage_path):
    """
    LÃ¤dt TV-Shows-Informationen aus dem angegebenen Storage-Pfad
    
    Args:
        storage_path (str): Pfad zum Storage-Verzeichnis
        
    Returns:
        list: Liste der TV-Shows oder leere Liste
    """
    if not storage_path:
        return []
    
    try:
        storage_dir = Path(storage_path)
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        tv_shows = []
        
        if storage_dir.exists() and storage_dir.is_dir():
            for show_dir in storage_dir.iterdir():
                if show_dir.is_dir():
                    # Suche nach Staffel-Ordnern
                    seasons = []
                    for season_item in show_dir.iterdir():
                        if season_item.is_dir() and ('season' in season_item.name.lower() or 'staffel' in season_item.name.lower()):
                            seasons.append(season_item.name)
                    
                    tv_shows.append({
                        'title': show_dir.name,
                        'path': str(show_dir),
                        'seasons': seasons,
                        'type': 'tv_show'
                    })
        
        return tv_shows
        
    except Exception as e:
        print(f"Error loading TV shows from {storage_path}: {e}")
        return []

def save_container_info(storage_path, container_data):
    """
    Speichert Container-Informationen in einer JSON-Datei
    
    Args:
        storage_path (str): Pfad zum Storage-Verzeichnis
        container_data (dict): Container-Daten zum Speichern
    """
    try:
        storage_dir = Path(storage_path)
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        container_file = storage_dir / 'container_info.json'
        
        with open(container_file, 'w', encoding='utf-8') as f:
            json.dump(container_data, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"Error saving container info: {e}")

def load_container_info(storage_path):
    """
    LÃ¤dt Container-Informationen aus einer JSON-Datei
    
    Args:
        storage_path (str): Pfad zum Storage-Verzeichnis
        
    Returns:
        dict: Container-Daten oder leeres Dict
    """
    try:
        storage_dir = Path(storage_path)
        container_file = storage_dir / 'container_info.json'
        
        if container_file.exists():
            with open(container_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return {}
        
    except Exception as e:
        print(f"Error loading container info: {e}")
        return {}

def cleanup_storage(storage_path, max_age_days=30):
    """
    Bereinigt alte Dateien im Storage-Verzeichnis
    
    Args:
        storage_path (str): Pfad zum Storage-Verzeichnis
        max_age_days (int): Maximales Alter in Tagen
    """
    try:
        import time
        
        storage_dir = Path(storage_path)
        if not storage_dir.exists():
            return
        
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60
        
        for item in storage_dir.iterdir():
            if item.is_file():
                file_age = current_time - item.stat().st_mtime
                if file_age > max_age_seconds:
                    try:
                        item.unlink()
                        print(f"Deleted old file: {item}")
                    except Exception as e:
                        print(f"Error deleting {item}: {e}")
                        
    except Exception as e:
        print(f"Error during cleanup: {e}")

def get_storage_stats(storage_path):
    """
    Gibt Statistiken Ã¼ber den Storage-Pfad zurÃ¼ck
    
    Args:
        storage_path (str): Pfad zum Storage-Verzeichnis
        
    Returns:
        dict: Storage-Statistiken
    """
    try:
        storage_dir = Path(storage_path)
        if not storage_dir.exists():
            return {
                'total_size': 0,
                'file_count': 0,
                'directory_count': 0,
                'exists': False
            }
        
        total_size = 0
        file_count = 0
        directory_count = 0
        
        for item in storage_dir.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1
            elif item.is_dir():
                directory_count += 1
        
        return {
            'total_size': total_size,
            'file_count': file_count,
            'directory_count': directory_count,
            'exists': True
        }
        
    except Exception as e:
        print(f"Error getting storage stats: {e}")
        return {
            'total_size': 0,
            'file_count': 0,
            'directory_count': 0,
            'exists': False,
            'error': str(e)
        } 
