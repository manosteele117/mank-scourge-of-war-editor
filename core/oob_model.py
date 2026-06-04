import math
import pandas as pd
from io import StringIO
from typing import Tuple, List, Optional, Dict, Any
import os

from constants import (
    COLUMN_ALIASES, HIERARCHY_COLS, LEVEL_NAMES, INT_COLUMNS, REQUIRED_COLUMNS,
)


class OOBData:
    """
    Handles CSV I/O, dataframe management, and hierarchy operations for Order of Battle data.

    Column aliases: each internal column name can have multiple valid alternate names
    in CSV files. On load, detected aliases are normalized to internal names.
    On save, the original file's headers are restored (or defaults if no file was loaded).
    """

    # Reverse mapping: lowercase alias -> internal name
    _alias_map: Dict[str, str]

    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.filepath: Optional[str] = None
        self._original_headers: Optional[Dict[str, str]] = None
        self._alias_map = {}
        self._build_alias_map()

        # Caches – invalidated on load / set_cell / delete
        self._level_cache: Dict[int, Optional[int]] = {}
        self._key_cache: Dict[int, Tuple[int, ...]] = {}
        self._subordinate_cache: Dict[int, List[int]] = {}

    # ── Alias helpers ──────────────────────────────────────────────

    def _build_alias_map(self):
        self._alias_map = {}
        for internal, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                self._alias_map[alias.lower()] = internal

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        self._original_headers = {}
        renamed: Dict[str, str] = {}
        for col in df.columns:
            normalized = col.strip().lower()
            if normalized in self._alias_map:
                internal_name = self._alias_map[normalized]
                renamed[col] = internal_name
                self._original_headers[internal_name] = col
            else:
                self._original_headers[col] = col
        if renamed:
            df = df.rename(columns=renamed)
        return df

    # ── Cache management ───────────────────────────────────────────

    def _invalidate_caches(self):
        self._level_cache.clear()
        self._key_cache.clear()
        self._subordinate_cache.clear()

    # ── CSV I/O ────────────────────────────────────────────────────

    def load_csv(self, path: str) -> None:
        with open(path, "r", encoding="cp1252") as f:
            raw_lines = f.readlines()

        header_idx: Optional[int] = None
        for i, line in enumerate(raw_lines):
            stripped = line.strip()
            if stripped and not stripped.startswith(","):
                header_idx = i
                break

        if header_idx is None:
            raise ValueError("CSV file has no valid header")

        data_lines: List[str] = []
        for i, line in enumerate(raw_lines):
            stripped = line.strip()
            if i == header_idx:
                if not stripped.startswith("line_number"):
                    data_lines.append(f"line_number,{line}" if stripped else line)
            elif stripped and stripped.startswith(","):
                continue
            elif stripped == "":
                continue
            else:
                data_lines.append(f"{i + 1},{line}")

        csv_content = "".join(data_lines)
        self.df = pd.read_csv(StringIO(csv_content), encoding="cp1252", dtype=str, header=0)

        first_col = self.df.columns[0]
        if first_col != "line_number":
            self.df.rename(columns={first_col: "line_number"}, inplace=True)
        self.df["line_number"] = (
            pd.to_numeric(self.df["line_number"], errors="coerce")
            .fillna(0)
            .astype(int)
        )

        self.df = self._normalize_columns(self.df)

        for col in HIERARCHY_COLS + INT_COLUMNS:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors="coerce").astype("Int64")

        missing = [c for c in REQUIRED_COLUMNS if c not in self.df.columns]
        if missing:
            raise ValueError(f"CSV is missing required columns: {missing}")

        self.filepath = path
        self._invalidate_caches()

    def save_csv(self, path: str) -> None:
        df = self._ensure_df().copy()
        if "line_number" in df.columns:
            df = df.drop(columns=["line_number"])
        if self._original_headers:
            rename_map = {
                internal: original
                for internal, original in self._original_headers.items()
                if internal in df.columns
            }
            df = df.rename(columns=rename_map)
        df.to_csv(path, encoding="cp1252", index=False)
        self.filepath = path

    def save_scenario(self, scenario_dir: str, map_name: str, oob_filename: str, placed_units) -> None:
        import os
        df = self._ensure_df().copy()
        if "line_number" in df.columns:
            df = df.drop(columns=["line_number"])

        scenario_cols = [
            "userName", "id", "sideIndex", "armyIndex", "corpsIndex", "divisionIndex",
            "brigadeIndex", "regimentIndex", "battalionIndex",
            "ammo", "dirSouth", "dirEast", "south", "east", "formation",
            "headCount", "fatigue", "morale",
        ]

        scenario_to_oob = {
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

        scenario_df = pd.DataFrame()
        int_columns = set(HIERARCHY_COLS + INT_COLUMNS)

        for scenario_col in scenario_cols:
            oob_col = scenario_to_oob.get(scenario_col)
            if oob_col and oob_col in df.columns:
                if oob_col in int_columns:
                    scenario_df[scenario_col] = df[oob_col].fillna(0)
                else:
                    scenario_df[scenario_col] = df[oob_col].fillna("")
            else:
                scenario_df[scenario_col] = ""

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

        os.makedirs(scenario_dir, exist_ok=True)
        path = os.path.join(scenario_dir, "scenario.csv")
        scenario_df.to_csv(path, encoding="cp1252", index=False)
        self.filepath = path

        with open(path, "r", encoding="cp1252") as f:
            lines = f.readlines()
        master_fields = ["MASTER", oob_filename] + [""] * (len(scenario_cols) - 2)
        master_line = ",".join(master_fields) + "\n"
        lines.insert(1, master_line)
        with open(path, "w", encoding="cp1252") as f:
            f.writelines(lines)

        _copy_templates(scenario_dir)

    # ── Row access ─────────────────────────────────────────────────

    def get_row(self, row_index: int) -> pd.Series:
        return self._ensure_df().iloc[row_index]

    def set_cell(self, row_index: int, column: str, value: Any) -> None:
        self._ensure_df().at[row_index, column] = value
        self._invalidate_caches()

    def _ensure_df(self) -> pd.DataFrame:
        if self.df is None:
            raise ValueError("No data loaded")
        return self.df

    # ── Hierarchy utilities ────────────────────────────────────────

    def get_level_from_hierarchy(self, row: pd.Series) -> Optional[int]:
        """Determine hierarchy level (1-6) from the deepest non-zero hierarchy column."""
        level = 0
        for col in HIERARCHY_COLS:
            val = row.get(col, 0)
            if pd.notna(val) and val != 0:
                level += 1
            elif pd.notna(val) and val == 0:
                break
        return level if level > 0 else None

    def get_level_from_hierarchy_cached(self, row_index: int) -> Optional[int]:
        """Cached version of get_level_from_hierarchy."""
        if row_index in self._level_cache:
            return self._level_cache[row_index]
        row = self.get_row(row_index)
        level = self.get_level_from_hierarchy(row)
        self._level_cache[row_index] = level
        return level

    def get_hierarchy_key(self, row: pd.Series, row_index: int) -> Tuple[int, ...]:
        """Extract hierarchy key from a row, with caching."""
        if row_index in self._key_cache:
            return self._key_cache[row_index]
        key: List[int] = []
        for col in HIERARCHY_COLS:
            val = row.get(col, 0)
            if pd.isna(val):
                print(f"OOB Hierarchy Warning: Line {row_index + 2}: Column '{col}' is missing or empty (expected an integer)\nAttempting to treat as 0, this really should be fixed though!\n")
                val = 0
            try:
                key.append(int(val))
            except (ValueError, TypeError):
                raise ValueError(f"Line {row_index + 2}: Column '{col}' has invalid value '{val}' (expected an integer)")
        result = tuple(key)
        self._key_cache[row_index] = result
        return result

    def get_parent_key(self, hierarchy_key: Tuple[int, ...]) -> Tuple[int, ...]:
        """Get the parent's hierarchy key by setting the last non-zero value to 0."""
        key = list(hierarchy_key)
        for i in range(len(key) - 1, -1, -1):
            if key[i] != 0:
                key[i] = 0
                break
        return tuple(key)

    def get_hierarchy_level_name_and_index(self, hierarchy_key: Tuple[int, ...]) -> str:
        for i in range(len(hierarchy_key) - 1, -1, -1):
            if hierarchy_key[i] != 0:
                return f"{LEVEL_NAMES[i]} ({hierarchy_key[i]})"
        return "Unknown"

    # ── Subordinate operations ─────────────────────────────────────

    def get_subordinate_row_indices(self, row_index: int) -> List[int]:
        """Get all subordinate row indices including the unit itself. Cached."""
        if row_index in self._subordinate_cache:
            return self._subordinate_cache[row_index]

        row = self.get_row(row_index)
        hierarchy_key = self.get_hierarchy_key(row, row_index)
        level = self.get_level_from_hierarchy(row)

        if level is None:
            raise ValueError(f"Line {row_index + 2}: Cannot determine hierarchy level")

        result = self._find_subordinate_indices(hierarchy_key, level)
        self._subordinate_cache[row_index] = result
        return result

    def _find_subordinate_indices(self, hierarchy_key: Tuple[int, ...], level: int) -> List[int]:
        df = self._ensure_df()
        matches: List[int] = []
        for idx, df_row in df.iterrows():
            try:
                df_key = self.get_hierarchy_key(df_row, idx)
            except ValueError:
                continue
            if all(hierarchy_key[i] == df_key[i] for i in range(level)):
                matches.append(idx)
        return matches

    def delete_unit(self, row_index: int) -> int:
        row = self.get_row(row_index)
        hierarchy_key = self.get_hierarchy_key(row, row_index)
        level = self.get_level_from_hierarchy(row)
        if level is None:
            raise ValueError(f"Line {row_index + 2}: Cannot determine hierarchy level")
        rows_to_delete = self._find_subordinate_indices(hierarchy_key, level)
        for idx in sorted(rows_to_delete, reverse=True):
            self.df.drop(idx, inplace=True)
        self.df.reset_index(drop=True, inplace=True)
        self._invalidate_caches()
        return len(rows_to_delete)

    # ── Stubbed future features ────────────────────────────────────

    def insert_unit_template(self, parent_row_index: int, unit_name: str) -> int:
        raise NotImplementedError("Unit template insertion not yet implemented")

    def copy_unit(self, row_index: int) -> Dict[str, Any]:
        raise NotImplementedError("Unit copy not yet implemented")

    def paste_unit(self, parent_row_index: int, clipboard_data: Dict[str, Any]) -> int:
        raise NotImplementedError("Unit paste not yet implemented")


def _copy_templates(scenario_dir: str):
    """Copy template files from the templates/ folder into the scenario directory."""
    import shutil
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    template_files = [
        "battlescript.csv",
        "EnglishScenIntro.txt",
        "EnglishScenScreen.txt",
        "maplocations.csv",
        "scenario.ini",
    ]
    for template_file in template_files:
        src_path = os.path.join(templates_dir, template_file)
        dst_path = os.path.join(scenario_dir, template_file)
        if os.path.exists(src_path):
            shutil.copy2(src_path, dst_path)
