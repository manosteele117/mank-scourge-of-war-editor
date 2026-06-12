"""Dropdown option providers for details view and scenario tab columns.

Loads rifles.csv, artillery.csv, gfx.csv, unitglobal.csv, and gfxpack.csv
into module-level caches and provides functions to resolve valid dropdown
options per column.
"""
import csv
from typing import Dict, List, Optional

from core.constants import HIERARCHY_COLS

# ── caches ──────────────────────────────────────────────────────────────────
_rifles_cache: Dict[str, str] = {}       # ID -> Name
_artillery_cache: Dict[str, str] = {}    # ID -> Name
_gfx_cache: Dict[str, str] = {}          # Name -> Name (first column of gfx.csv)
_unitglobal_cache: Dict[str, str] = {}   # Class -> Class (first column of unitglobal.csv)
_gfxpack_cache: Dict[str, str] = {}      # Name -> Name (first column of gfxpack.csv)

# Columns that support dropdowns
DROPDOWN_COLUMNS = {"Formation", "Weapon", "CLASS", "FLAGS", "FLAG2"}


def has_dropdown(column_name: str) -> bool:
    return column_name in DROPDOWN_COLUMNS


# ── file loaders ────────────────────────────────────────────────────────────
def _load_id_name_csv(file_path: str) -> Dict[str, str]:
    """Load a 2-column CSV (Name, ID) into {ID: Name}, skipping 'Name'/'idstring' headers."""
    cache: Dict[str, str] = {}
    try:
        with open(file_path, "r", encoding="cp1252") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                name, rid = row[0].strip(), row[1].strip()
                if not rid or rid == "idstring" or not name or name == "Name":
                    continue
                cache[rid] = name
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
    return cache


def _load_single_col_csv(file_path: str, skip_header: str) -> Dict[str, str]:
    """Load a 1-column CSV into {Name: Name}, skipping a header row."""
    cache: Dict[str, str] = {}
    try:
        with open(file_path, "r", encoding="cp1252") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                name = row[0].strip()
                if not name or name == skip_header:
                    continue
                cache[name] = name
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
    return cache


def load_rifles(file_path: str) -> None:
    global _rifles_cache
    _rifles_cache = _load_id_name_csv(file_path)


def load_artillery(file_path: str) -> None:
    global _artillery_cache
    _artillery_cache = _load_id_name_csv(file_path)


def load_gfx(file_path: str) -> None:
    global _gfx_cache
    _gfx_cache = _load_single_col_csv(file_path, "Name")


def load_unitglobal(file_path: str) -> None:
    global _unitglobal_cache
    _unitglobal_cache = _load_single_col_csv(file_path, "Class")


def load_gfxpack(file_path: str) -> None:
    global _gfxpack_cache
    _gfxpack_cache = _load_single_col_csv(file_path, "Name")


# ── option providers ────────────────────────────────────────────────────────
def _get_unit_level(row_dict: dict) -> int:
    """Return the hierarchy level (1-6) of a unit based on its hierarchy columns."""
    for i in range(len(HIERARCHY_COLS) - 1, -1, -1):
        val = row_dict.get(HIERARCHY_COLS[i])
        if val is not None and val != "" and val != 0:
            return i + 1
    return 1


def get_formation_options(row_dict: dict) -> List[str]:
    """Return formation drill_ids valid for this unit's level."""
    from core.formation import FormationArchetype

    level = _get_unit_level(row_dict)
    # Levels 1-2 always see level 3 formations
    max_level = max(level, 3)
    options = []
    for drill_id in FormationArchetype.formations:
        for lvl in range(level, max_level + 1):
            if f"Lvl{lvl}" in drill_id:
                options.append(drill_id)
    options.sort()
    return options


def get_weapon_options(row_dict: dict) -> List[str]:
    """Return weapon IDs from loaded rifles and artillery files (level 6 only)."""
    level = _get_unit_level(row_dict)
    if level != 6:
        return []
    options = list(_rifles_cache.keys()) + list(_artillery_cache.keys())
    options.sort()
    return options


def get_unitglobal_class_options() -> List[str]:
    """Return class IDs from loaded unitglobal file."""
    return sorted(_unitglobal_cache.keys())


def get_gfxpack_options() -> List[str]:
    """Return sprite names from loaded gfxpack file."""
    return sorted(_gfxpack_cache.keys())


def get_gfx_options() -> List[str]:
    """Return sprite names from loaded gfx file."""
    return sorted(_gfx_cache.keys())
