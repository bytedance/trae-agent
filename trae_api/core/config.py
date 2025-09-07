"""
Compatibility shim for consolidated settings.

This module re-exports everything from trae_api.core.settings
which is the canonical source for application configuration.
"""

# Re-export everything from the canonical settings module
from trae_api.core.settings import (
    LogLevel,
    Settings,
    TEMP_DIR,
    get_settings,
    settings,
)

__all__ = ["LogLevel", "Settings", "TEMP_DIR", "get_settings", "settings"]