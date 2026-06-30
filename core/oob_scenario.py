"""Scenario import/export: transforms OOB data into game-compatible scenario files.

Extracted from OOBData.save_scenario() and the standalone _copy_templates().
"""

import os
import math
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from core.constants import HIERARCHY_COLS, INT_COLUMNS


# Columns required in the game's scenario.csv format
SCENARIO_COLUMNS = [
    "userName", "id", "sideIndex", "armyIndex", "corpsIndex", "divisionIndex",
    "brigadeIndex", "regimentIndex", "battalionIndex",
    "ammo", "dirSouth", "dirEast", "south", "east", "formation",
    "headCount", "fatigue", "morale",
]

# Mapping from scenario column -> OOB column (None = generated)
SCENARIO_TO_OOB = {
    "userName": "NAME1",
    "id": "ID",
    "sideIndex": "SIDE 1",
    "armyIndex": "ARMY 2",
    "corpsIndex": "CORPS 3",
    "divisionIndex": "DIV 4",
    "brigadeIndex": "BGDE 5",
    "regimentIndex": "BTN 6",
    "battalionIndex": None,
    "ammo": "AMMO",
    "dirSouth": None,
    "dirEast": None,
    "south": None,
    "east": None,
    "formation": "Formation",
    "headCount": "Head Count",
    "fatigue": "Fatigue",
    "morale": "Morale",
}

MAPLOCATIONS_HEADER = [
    "Name", "ID", "Priority", "Type", "AI",
    "loc x", "loc z", "radius", "Men", "Points",
    "Fatigue", "Morale", "Ammo", "OccMod",
    "Beg", "End", "Interval", "Sprite",
    "Army1", "Army2", "Army3",
]

VC_SECTION_MAP = {
    "Major Victory": "endmajwin",
    "Minor Victory": "endwin",
    "Draw": "endtie",
    "Minor Defeat": "endfail",
    "Major Defeat": "endmajfail",
}


def export_scenario(oob_data, scenario_dir: str, map_name: str, oob_filename: str,
                    placed_units, objectives=None, intro_text: str = "",
                    start_time: str = "", victory_conditions: dict = None,
                    oob_names_path: str = None, scenario_name: str = "",
                    inner_scenario_name: str = "",
                    auto_fill_supply: bool = True):
    """Export OOB data as a complete game scenario directory.

    Directory layout under *scenario_dir* (the top-level timestamped folder)::

        Scenarios/<inner_name>/   – scenario.csv, templates, intro, maplocations, ini
        OOBs/                     – OOB_SB_<name>.csv  (only when new units exist)
        Layout/Media/Language/    – OOBNames.xml       (only when new units exist)

    Args:
        oob_data: OOBData instance with loaded data.
        scenario_dir: Top-level destination directory (already timestamped).
        map_name: Name of the game map (without extension).
        oob_filename: Original OOB CSV filename for the MASTER line.
        placed_units: List of dicts with row_index, world_x, world_y, rotation, formation.
        objectives: List of objective data dicts (with 'fields' key).
        intro_text: Custom intro text in game HTML format.
        start_time: Start time string (HH:MM:SS).
        victory_conditions: Dict of label -> points.
        oob_names_path: Path to the loaded OOBNames.xml file (optional).
        scenario_name: Name of the scenario, used for OOBNames output filename.
        inner_scenario_name: Subfolder name under Scenarios/ (default: scenario_name).
    """
    inner_name = inner_scenario_name or scenario_name or "Scenario"
    scenarios_dir = os.path.join(scenario_dir, "Scenarios", inner_name)
    os.makedirs(scenario_dir, exist_ok=True)
    os.makedirs(scenarios_dir, exist_ok=True)

    # ── Build scenario_df (preserving original row indices) ────────────
    keys = np.array(
        [list(oob_data.get_hierarchy_key_by_index(i)) for i in range(len(oob_data.df))],
        dtype=np.int64,
    )
    order = np.lexsort(keys.T[::-1])
    df = oob_data.df.iloc[order].copy()
    if "line_number" in df.columns:
        df = df.drop(columns=["line_number"])

    scenario_df = pd.DataFrame()
    int_columns = set(HIERARCHY_COLS + INT_COLUMNS)

    for scenario_col in SCENARIO_COLUMNS:
        oob_col = SCENARIO_TO_OOB.get(scenario_col)
        if oob_col and oob_col in df.columns:
            if oob_col in int_columns:
                scenario_df[scenario_col] = df[oob_col].fillna(0)
            else:
                scenario_df[scenario_col] = df[oob_col].fillna("")
        else:
            scenario_df[scenario_col] = ""

    # ── Apply placed-unit positions ───────────────────────────────────
    if placed_units:
        placed_lookup = {pu["row_index"]: pu for pu in placed_units}
        for i in scenario_df.index:
            if i in placed_lookup:
                pu = placed_lookup[i]
                south = -1 * math.cos(math.radians(pu["rotation"]))
                east = math.sin(math.radians(pu["rotation"]))
                scenario_df.at[i, "south"] = pu["world_y"]
                scenario_df.at[i, "east"] = pu["world_x"]
                scenario_df.at[i, "dirSouth"] = south
                scenario_df.at[i, "dirEast"] = east
                if pu.get("formation"):
                    scenario_df.at[i, "formation"] = pu["formation"]

    # ── Auto-fill unplaced supply/couriers ───────────────────────────
    auto_fill_indices = set()
    if auto_fill_supply and placed_units:
        placed_row_indices_tmp = set(pu["row_index"] for pu in placed_units)
        for pu in placed_units:
            level = pu.get("level")
            if level is None or level > 4:
                continue
            children = oob_data.get_direct_children(
                pu["row_index"], exclude_supply=False)
            for child_idx in children:
                if child_idx in placed_row_indices_tmp:
                    continue
                child_class = str(
                    oob_data.df.iloc[child_idx].get("CLASS", ""))
                if "_Courier" in child_class or "_Wagon" in child_class:
                    parent_pu = placed_lookup[pu["row_index"]]
                    south = -1 * math.cos(math.radians(parent_pu["rotation"]))
                    east = math.sin(math.radians(parent_pu["rotation"]))
                    scenario_df.at[child_idx, "south"] = parent_pu["world_y"]
                    scenario_df.at[child_idx, "east"] = parent_pu["world_x"]
                    scenario_df.at[child_idx, "dirSouth"] = south
                    scenario_df.at[child_idx, "dirEast"] = east
                    auto_fill_indices.add(child_idx)

    # ── Filter to only placed (+ auto-filled) units ──────────────────
    if placed_units:
        placed_row_indices = set(
            pu["row_index"] for pu in placed_units) | auto_fill_indices
        scenario_df = scenario_df[scenario_df.index.isin(placed_row_indices)].reset_index(drop=True)

    # ── Detect new units not in original import ────────────────────────
    has_new = False
    if placed_units:
        if oob_data._original_df is not None and "ID" in oob_data.df.columns:
            orig_ids = set(oob_data._original_df["ID"].astype(str))
            for pu in placed_units:
                idx = pu["row_index"]
                if 0 <= idx < len(oob_data.df):
                    row_id = str(oob_data.df.iloc[idx].get("ID", ""))
                    if row_id and row_id not in orig_ids:
                        has_new = True
                        break
        else:
            has_new = True  # no original file, all units are new

    # ── Save OOB (conditional) ────────────────────────────────────────
    if has_new:
        oob_dir = os.path.join(scenario_dir, "OOBs")
        os.makedirs(oob_dir, exist_ok=True)
        safe = re.sub(r'[<>:"/\\|?*]', '_', scenario_name) if scenario_name else "Scenario"
        oob_filename = f"OOB_SB_{safe}.csv"
        _save_oob_for_scenario(oob_data, os.path.join(oob_dir, oob_filename))

    # ── Write scenario.csv + MASTER line ──────────────────────────────
    path = os.path.join(scenarios_dir, "scenario.csv")
    scenario_df.to_csv(path, encoding="cp1252", index=False)

    with open(path, "r", encoding="cp1252") as f:
        lines = f.readlines()
    master_fields = ["MASTER", oob_filename] + [""] * (len(SCENARIO_COLUMNS) - 2)
    master_line = ",".join(master_fields) + "\n"
    lines.insert(1, master_line)
    with open(path, "w", encoding="cp1252") as f:
        f.writelines(lines)

    # ── Copy template files ───────────────────────────────────────────
    _copy_templates(scenarios_dir)
    _copy_top_level_templates(scenario_dir)

    # ── Intro text ────────────────────────────────────────────────────
    if intro_text:
        intro_path = os.path.join(scenarios_dir, "EnglishScenIntro.txt")
        with open(intro_path, "w", encoding="cp1252") as f:
            f.write(intro_text)

    # ── Map locations / objectives ────────────────────────────────────
    if objectives:
        maplocations_path = os.path.join(scenarios_dir, "maplocations.csv")
        with open(maplocations_path, "w", encoding="cp1252") as f:
            f.write(",".join(MAPLOCATIONS_HEADER) + "\n")
            for obj in objectives:
                fields = obj.get("fields", {})
                row = ",".join(str(fields.get(col, "")) for col in MAPLOCATIONS_HEADER)
                f.write(row + "\n")

    # ── Scenario INI patching ─────────────────────────────────────────
    if map_name or start_time or victory_conditions:
        _patch_scenario_ini(scenarios_dir, map_name, start_time, victory_conditions)

    # ── OOBNames.xml (conditional) ────────────────────────────────────
    if has_new and oob_names_path and placed_units:
        from core.oob_names import parse_existing_ids, generate_oob_names_xml
        try:
            existing_ids = parse_existing_ids(oob_names_path)
            placed_indices = {pu["row_index"] for pu in placed_units} | auto_fill_indices
            media_dir = os.path.join(scenario_dir, "Layout", "Media", "Language")
            os.makedirs(media_dir, exist_ok=True)
            generate_oob_names_xml(
                oob_data.df, placed_indices, existing_ids,
                scenario_name, media_dir,
            )
        except Exception as e:
            print(f"Warning: Failed to generate OOBNames.xml: {e}")


def _save_oob_for_scenario(oob_data, path: str) -> None:
    """Save the current OOB to *path* without updating oob_data.filepath.

    Restores original column headers and sorts by hierarchy like save_csv,
    but is a pure export side-effect.
    """
    df = oob_data._df_sorted_by_hierarchy(oob_data.df.copy())
    if "line_number" in df.columns:
        df = df.drop(columns=["line_number"])
    if oob_data._original_headers:
        rename_map = {
            internal: original
            for internal, original in oob_data._original_headers.items()
            if internal in df.columns
        }
        df = df.rename(columns=rename_map)
    df.to_csv(path, encoding="cp1252", index=False)


def _patch_scenario_ini(scenario_dir: str, map_name: str, start_time: str,
                        victory_conditions: dict = None):
    ini_path = os.path.join(scenario_dir, "scenario.ini")
    if not os.path.exists(ini_path):
        return
    with open(ini_path, "r", encoding="cp1252") as f:
        lines = f.readlines()

    in_section = None
    vc_inserted = set()
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped[1:-1]
        elif in_section == "init" and stripped.startswith("map=") and map_name:
            lines[i] = f"map={map_name}\n"
        elif in_section == "init" and stripped.startswith("starttime=") and start_time:
            lines[i] = f"starttime={start_time}\n"
        elif (victory_conditions
              and in_section in VC_SECTION_MAP.values()
              and in_section not in vc_inserted):
            vc_label = {v: k for k, v in VC_SECTION_MAP.items()}.get(in_section)
            if vc_label and vc_label in victory_conditions and stripped.startswith("article="):
                points = victory_conditions[vc_label]
                lines.insert(i + 1, f"grade={points}\n")
                vc_inserted.add(in_section)

    with open(ini_path, "w", encoding="cp1252") as f:
        f.writelines(lines)


def _copy_templates(scenario_dir: str):
    """Copy template files from the templates/scenario/ folder into the scenario directory."""
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "templates", "scenario")
    for template_file in (
        "battlescript.csv",
        "EnglishScenIntro.txt",
        "EnglishScenScreen.txt",
        "maplocations.csv",
        "scenario.ini",
    ):
        src = os.path.join(templates_dir, template_file)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(scenario_dir, template_file))


def _copy_top_level_templates(scenario_dir: str):
    """Copy EnglishModIntro.txt and README.txt to the top-level scenario directory."""
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "templates", "scenario")
    for template_file in ("EnglishModIntro.txt", "README.txt"):
        src = os.path.join(templates_dir, template_file)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(scenario_dir, template_file))


# ── Load helpers ────────────────────────────────────────────────────────

def _resolve_scenarios_dir(folder: str) -> str:
    """Resolve the inner Scenarios/<name> directory from a user-selected folder.

    Handles two cases:
    - User selected an outer folder containing Scenarios/<name>/
    - User selected the inner scenario folder directly (contains scenario.csv)

    Returns the resolved path, or empty string if invalid.
    """
    csv_path = os.path.join(folder, "scenario.csv")
    if os.path.isfile(csv_path):
        return folder

    scenarios_sub = os.path.join(folder, "Scenarios")
    if os.path.isdir(scenarios_sub):
        for name in sorted(os.listdir(scenarios_sub)):
            sub = os.path.join(scenarios_sub, name)
            if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "scenario.csv")):
                return sub

    return ""


def load_scenario_csv(scenarios_dir: str) -> dict:
    """Parse scenario.csv and return structured data.

    The column headers may vary (e.g. userName/Name, id/ID, south/loc x),
    but the fields are always in the same positional order matching
    ``SCENARIO_COLUMNS``. The MASTER line and comment lines (starting with
    a comma) are skipped when extracting unit rows.

    Returns:
        {
            "oob_filename": str,
            "units": [
                {
                    "id": str,
                    "world_x": int,
                    "world_y": int,
                    "dir_south": float,
                    "dir_east": float,
                    "formation": str,
                    "head_count": int,
                },
                ...
            ],
        }
    """
    csv_path = os.path.join(scenarios_dir, "scenario.csv")
    with open(csv_path, "r", encoding="cp1252") as f:
        lines = f.readlines()

    if not lines:
        raise ValueError("scenario.csv is empty")

    oob_filename = ""
    units = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(","):
            continue
        parts = stripped.split(",")

        if parts[0].upper() == "MASTER":
            if len(parts) >= 2:
                oob_filename = parts[1].strip()
            continue

        units.append({
            "id": _field(parts, SCENARIO_COLUMNS.index("id")),
            "world_x": int(_safe_float(_field(parts, SCENARIO_COLUMNS.index("east")))),
            "world_y": int(_safe_float(_field(parts, SCENARIO_COLUMNS.index("south")))),
            "dir_south": _safe_float(_field(parts, SCENARIO_COLUMNS.index("dirSouth"))),
            "dir_east": _safe_float(_field(parts, SCENARIO_COLUMNS.index("dirEast"))),
            "formation": _field(parts, SCENARIO_COLUMNS.index("formation")),
            "head_count": _safe_int(_field(parts, SCENARIO_COLUMNS.index("headCount"))),
        })

    return {"oob_filename": oob_filename, "units": units}


def _field(parts: list, idx: int) -> str:
    return parts[idx].strip() if idx < len(parts) else ""


def load_maplocations_csv(scenarios_dir: str) -> list:
    """Parse maplocations.csv and return a list of objective field dicts."""
    csv_path = os.path.join(scenarios_dir, "maplocations.csv")
    if not os.path.isfile(csv_path):
        return []

    with open(csv_path, "r", encoding="cp1252") as f:
        lines = f.readlines()

    if not lines:
        return []

    headers = [h.strip() for h in lines[0].strip().split(",")]
    objectives = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(",")
        fields = {}
        for i, col in enumerate(headers):
            fields[col] = parts[i].strip() if i < len(parts) else ""
        objectives.append(fields)

    return objectives


def load_scenario_ini(scenarios_dir: str) -> dict:
    """Parse scenario.ini and return scenario settings.

    Returns:
        {
            "map_name": str,
            "start_time": str,
            "type": str,
            "victory_conditions": {label: points_str, ...},
        }
    """
    ini_path = os.path.join(scenarios_dir, "scenario.ini")
    result = {"map_name": "", "start_time": "", "type": "", "victory_conditions": {}}

    if not os.path.isfile(ini_path):
        return result

    with open(ini_path, "r", encoding="cp1252") as f:
        lines = f.readlines()

    in_section = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped[1:-1].lower()
        elif in_section == "init":
            if stripped.lower().startswith("map="):
                result["map_name"] = stripped.split("=", 1)[1].strip()
            elif stripped.lower().startswith("starttime="):
                result["start_time"] = stripped.split("=", 1)[1].strip()
            elif stripped.lower().startswith("type="):
                result["type"] = stripped.split("=", 1)[1].strip().upper()
        elif in_section and in_section.startswith("end"):
            if stripped.lower().startswith("grade="):
                vc_label = _vc_section_to_label(in_section)
                if vc_label:
                    result["victory_conditions"][vc_label] = stripped.split("=", 1)[1].strip()

    return result


def load_intro_text(scenarios_dir: str) -> str:
    """Read EnglishScenIntro.txt and return raw game-format text."""
    intro_path = os.path.join(scenarios_dir, "EnglishScenIntro.txt")
    if not os.path.isfile(intro_path):
        return ""
    with open(intro_path, "r", encoding="cp1252") as f:
        return f.read()


# ── Internal helpers ────────────────────────────────────────────────────

def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _vc_section_to_label(section: str) -> str:
    """Map an INI section name like 'endmajwin' to a display label like 'Major Victory'."""
    section = section.lower()
    for label, sec in VC_SECTION_MAP.items():
        if sec.lower() == section:
            return label
    return ""
