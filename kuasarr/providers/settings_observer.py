# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""
Settings observer pattern for live configuration updates.

Components can register callbacks to be notified when specific settings change,
enabling live updates without requiring a restart.
"""

from typing import Callable, Dict, List, Optional, Set
from functools import wraps

# Registry of observers: setting_name -> list of callback functions
_observers: Dict[str, List[Callable[[str, any], None]]] = {}

# Global callbacks that fire on any settings change
_global_observers: List[Callable[[str, any], None]] = []


def register_observer(setting_name: str, callback: Callable[[str, any], None]) -> None:
    """
    Register a callback to be called when a specific setting changes.

    Args:
        setting_name: The name of the setting to watch (e.g., 'internal_address')
        callback: Function to call when the setting changes.
                  Signature: callback(setting_name, new_value) -> None

    Example:
        def on_address_change(name, value):
            print(f"Address changed to: {value}")
        register_observer('internal_address', on_address_change)
    """
    if setting_name not in _observers:
        _observers[setting_name] = []
    _observers[setting_name].append(callback)


def unregister_observer(setting_name: str, callback: Callable[[str, any], None]) -> None:
    """
    Unregister a previously registered callback.

    Args:
        setting_name: The setting name the callback was registered for
        callback: The callback function to remove
    """
    if setting_name in _observers and callback in _observers[setting_name]:
        _observers[setting_name].remove(callback)


def register_global_observer(callback: Callable[[str, any], None]) -> None:
    """
    Register a callback to be called when ANY setting changes.

    Args:
        callback: Function to call on any settings change.
                  Signature: callback(setting_name, new_value) -> None
    """
    _global_observers.append(callback)


def unregister_global_observer(callback: Callable[[str, any], None]) -> None:
    """
    Unregister a previously registered global observer.

    Args:
        callback: The callback function to remove
    """
    if callback in _global_observers:
        _global_observers.remove(callback)


def notify_setting_changed(setting_name: str, new_value: any) -> None:
    """
    Notify all registered observers that a setting has changed.

    Args:
        setting_name: The name of the setting that changed
        new_value: The new value of the setting
    """
    # Notify specific observers for this setting
    if setting_name in _observers:
        for callback in _observers[setting_name][:]:
            try:
                callback(setting_name, new_value)
            except Exception as e:
                # Log but don't let observer errors break the flow
                print(f"Error in settings observer for {setting_name}: {e}")

    # Notify global observers
    for callback in _global_observers[:]:
        try:
            callback(setting_name, new_value)
        except Exception as e:
            print(f"Error in global settings observer: {e}")


def notify_core_settings_changed(settings: Dict[str, any]) -> None:
    """
    Notify observers that multiple core settings have changed.

    Args:
        settings: Dictionary of setting_name -> new_value
    """
    for setting_name, new_value in settings.items():
        notify_setting_changed(setting_name, new_value)


def get_registered_observers() -> Dict[str, int]:
    """
    Get a count of registered observers per setting (for debugging).

    Returns:
        Dictionary mapping setting names to observer counts
    """
    return {
        **{name: len(callbacks) for name, callbacks in _observers.items()},
        "__global__": len(_global_observers)
    }


def clear_all_observers() -> None:
    """Clear all registered observers. Useful for testing."""
    _observers.clear()
    _global_observers.clear()


# =============================================================================
# Convenience decorators
# =============================================================================

def on_setting_change(setting_name: str):
    """
    Decorator to register a function as an observer for a specific setting.

    Example:
        @on_setting_change('timezone')
        def update_timezone(name, value):
            # Update timezone in your component
            pass
    """
    def decorator(func: Callable[[str, any], None]) -> Callable[[str, any], None]:
        register_observer(setting_name, func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def on_any_setting_change(func: Callable[[str, any], None]) -> Callable[[str, any], None]:
    """
    Decorator to register a function as a global observer for all settings changes.

    Example:
        @on_any_setting_change
        def log_all_changes(name, value):
            print(f"Setting {name} changed to {value}")
    """
    register_global_observer(func)

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
