# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)
# Source discovery adapted from Quasarr v4.0.0

import importlib
import inspect
import pkgutil

from kuasarr.providers.log import error
from kuasarr.downloads.base import AbstractDownloadSource

_sources: dict = {}
_source_module_names: list = []


def get_source_module_names() -> list:
    global _source_module_names

    if _source_module_names:
        return _source_module_names

    discovered = []
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        if module_name.startswith("_"):
            continue
        discovered.append(module_name)

    _source_module_names = sorted(discovered)
    return _source_module_names


def get_sources() -> dict:
    """Auto-discover and instantiate all registered AbstractDownloadSource classes."""
    if not _sources:
        for module_name in get_source_module_names():
            try:
                mod = importlib.import_module(f"kuasarr.downloads.sources.{module_name}")
            except Exception as e:
                error(f"Error importing download source {module_name.upper()}: {e}")
                continue

            if hasattr(mod, "Source"):
                if inspect.isclass(mod.Source) and issubclass(
                    mod.Source, AbstractDownloadSource
                ):
                    try:
                        instance = mod.Source()
                        _sources[instance.initials] = instance
                    except Exception as e:
                        error(f"Error instantiating download source {module_name.upper()}: {e}")
            # Sources without a Source class are silently skipped (legacy)
    return _sources


def reset_sources() -> None:
    """Reset the source registry (for testing)."""
    global _sources, _source_module_names
    _sources = {}
    _source_module_names = []
