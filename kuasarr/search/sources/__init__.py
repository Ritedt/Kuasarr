# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)
# Source discovery adapted from Quasarr v4.0.0

import importlib
import inspect
import pkgutil
import threading

from kuasarr.providers.log import error, warn
from kuasarr.search.base import AbstractSearchSource

_sources: dict = {}
_source_module_names: list = []
_sources_lock = threading.Lock()
_source_module_names_lock = threading.Lock()


def get_source_module_names() -> list:
    global _source_module_names

    if _source_module_names:
        return _source_module_names

    with _source_module_names_lock:
        if not _source_module_names:
            discovered = []
            for _, module_name, _ in pkgutil.iter_modules(__path__):
                if module_name.startswith("_"):
                    continue
                discovered.append(module_name)

            _source_module_names = sorted(discovered)

    return _source_module_names


def get_sources() -> dict:
    """
    Auto-discover and instantiate all registered AbstractSearchSource classes.

    Returns:
        Dict mapping source initials to AbstractSearchSource instances.
        Sources without a Source class are silently skipped.
    """
    if not _sources:
        with _sources_lock:
            if not _sources:
                for module_name in get_source_module_names():
                    try:
                        mod = importlib.import_module(f"kuasarr.search.sources.{module_name}")
                    except Exception as e:
                        error(f"Error importing search source {module_name.upper()}: {e}")
                        continue

                    if hasattr(mod, "Source"):
                        if inspect.isclass(mod.Source) and issubclass(
                            mod.Source, AbstractSearchSource
                        ):
                            try:
                                instance = mod.Source()
                                _sources[instance.initials] = instance
                            except Exception as e:
                                error(f"Error instantiating search source {module_name.upper()}: {e}")
                        else:
                            error(
                                f"Search source '{module_name.upper()}.Source' does not implement AbstractSearchSource"
                            )
                    # Sources without a Source class are silently skipped (legacy plain-function sources)
    return _sources


def reset_sources() -> None:
    """Reset the source registry (for testing)."""
    global _sources, _source_module_names
    with _sources_lock:
        with _source_module_names_lock:
            _sources = {}
            _source_module_names = []
