"""Persistent application configuration backed by an INI file.

Replaces the duplicated config-parser boilerplate that was scattered across
gui/oob_viewer.py with a single class that handles path resolution, default
values, and section management.
"""

import configparser
import os


class AppConfig:
    """Typed get/set for paths, settings, and map-settings stored in app_config.ini."""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config")
        self._config_dir = config_dir
        self._config_path = os.path.join(config_dir, "app_config.ini")
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(self._config_dir, exist_ok=True)
        if not os.path.exists(self._config_path):
            parser = configparser.ConfigParser()
            parser.add_section("paths")
            for key in ("map-ini", "drills", "oob", "rifles", "artillery",
                        "gfx", "gfxpack", "unitglobal", "oobnames"):
                parser.set("paths", key, "")
            with open(self._config_path, "w") as f:
                parser.write(f)

    # ── Low-level read/write ────────────────────────────────────────

    def _read_section(self, section: str, defaults: dict = None) -> dict:
        parser = configparser.ConfigParser()
        parser.read(self._config_path)
        result = {}
        if defaults:
            for key, val in defaults.items():
                result[key] = parser.get(section, key, fallback=val)
        return result

    def _write_section(self, section: str, **kwargs):
        parser = configparser.ConfigParser()
        parser.read(self._config_path)
        if section not in parser:
            parser.add_section(section)
        for key, val in kwargs.items():
            parser.set(section, key, val)
        with open(self._config_path, "w") as f:
            parser.write(f)

    # ── Public API ──────────────────────────────────────────────────

    def get(self, key: str, default: str = "") -> str:
        """Return a config value. Checks paths, then settings, then map-settings."""
        parser = configparser.ConfigParser()
        parser.read(self._config_path)
        for section in ("paths", "settings", "map-settings"):
            if parser.has_section(section) and parser.has_option(section, key):
                return parser.get(section, key, fallback=default)
        return default

    def set(self, section: str, key: str, value: str):
        self._write_section(section, **{key: value})

    # ── Convenience methods ─────────────────────────────────────────

    def get_bool(self, key: str, default: bool = False) -> bool:
        return self.get(key, "true" if default else "false") == "true"

    def get_int(self, key: str, default: int = 0) -> int:
        return int(self.get(key, str(default)))

    def get_path(self, key: str) -> str:
        """Return a path value or empty string if not set."""
        return self.get(key, "")

    def load_all(self) -> dict:
        """Return a flat dict of all known config values for backward compat."""
        parser = configparser.ConfigParser()
        parser.read(self._config_path)
        result = {}

        path_keys = ("map-ini", "drills", "oob", "rifles", "artillery",
                     "gfx", "gfxpack", "unitglobal", "oobnames", "template_files_enabled")
        for key in path_keys:
            result[key] = parser.get("paths", key, fallback="")

        setting_defaults = {"debug_formation_plot": "true", "debug_logging": "false",
                           "tile_scale": "512", "units_per_yard": "30",
                           "formation_plot_level": "5"}
        for key, default in setting_defaults.items():
            result[key] = parser.get("settings", key, fallback=default)

        map_defaults = {"toggle_names": "false", "name_level": "3"}
        for key, default in map_defaults.items():
            result[key] = parser.get("map-settings", key, fallback=default)

        return result
