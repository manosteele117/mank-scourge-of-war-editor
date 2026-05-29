import pandas as pd
from io import StringIO
from typing import Tuple, List, Optional, Dict, Any
import os


class OOBData:
    """
    Handles CSV I/O, dataframe management, and hierarchy operations for Order of Battle data.
    
    Column aliases: each internal column name can have multiple valid alternate names
    in CSV files. On load, detected aliases are normalized to internal names.
    On save, the original file's headers are restored (or defaults if no file was loaded).
    """
    
    # Internal name -> list of valid alternate names (case-insensitive matching)
    COLUMN_ALIASES: Dict[str, List[str]] = {
        "Name": ["name"],
        "ID": ["id"],
        "NAME1": ["name1"],
        "NAME2": ["name2"],
        "SIDE 1": ["side 1", "side"],
        "ARMY 2": ["army 2", "army"],
        "CORPS 3": ["corps 3", "corps"],
        "DIV 4": ["div 4", "div"],
        "BGDE 5": ["bgde 5", "bgde"],
        "BTN 6": ["btn 6", "btn", "reg"],
        "CLASS": ["class"],
        "PORTRAIT": ["portrait"],
        "Weapon": ["weapon"],
        "AMMO": ["ammo"],
        "FLAGS": ["flags"],
        "FLAG2": ["flag2"],
        "Formation": ["formation"],
        "Head Count": ["head count"],
        "Ability": ["ability"],
        "Command": ["command"],
        "Control": ["control"],
        "Leadership": ["leadership"],
        "Style": ["style"],
        "Experience": ["experience"],
        "Fatigue": ["fatigue"],
        "Morale": ["morale"],
        "Close": ["close"],
        "Open": ["open"],
        "Edged": ["edged"],
        "Firearm": ["firearm"],
        "Marksmanship": ["marksmanship"],
        "Horsemanship": ["horsemanship"],
        "Surgeon": ["surgeon"],
        "Calisthenics": ["calisthenics"],
    }
    
    # Hierarchy columns in order (SIDE, ARMY, CORPS, DIV, BGDE, BTN)
    HIERARCHY_COLS: List[str] = ["SIDE 1", "ARMY 2", "CORPS 3", "DIV 4", "BGDE 5", "BTN 6"]
    
    # Human-readable names for each hierarchy level
    LEVEL_NAMES: List[str] = ["Side", "Army", "Corps", "Division", "Brigade", "Regiment"]
    
    # Columns that should be converted to nullable Int64 on load
    INT_COLUMNS: List[str] = [
        "Head Count", "Experience", "Fatigue", "Morale",
        "Close", "Open", "Edged", "Firearm",
        "Marksmanship", "Horsemanship", "Surgeon", "Calisthenics",
        "Ability", "Command", "Control", "Leadership", "Style",
    ]
    
    # Required columns for a valid OOB CSV
    REQUIRED_COLUMNS: List[str] = [
        "NAME1", "Head Count", "SIDE 1", "ARMY 2",
        "CORPS 3", "DIV 4", "BGDE 5", "BTN 6",
    ]
    
    # Reverse mapping: lowercase alias -> internal name
    _alias_map: Dict[str, str]
    
    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.filepath: Optional[str] = None
        self._original_headers: Optional[Dict[str, str]] = None  # internal_name -> original CSV header
        self._alias_map = {}
        self._build_alias_map()
    
    def _build_alias_map(self):
        """Build reverse lookup: lowercase alias -> internal name."""
        self._alias_map = {}
        for internal, aliases in self.COLUMN_ALIASES.items():
            for alias in aliases:
                self._alias_map[alias.lower()] = internal
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect column aliases in the dataframe and rename them to internal names.
        Stores the mapping from internal name -> original header for later save.
        If multiple columns map to the same internal name, the first match wins.
        """
        self._original_headers = {}
        renamed: Dict[str, str] = {}
        
        for col in df.columns:
            normalized = col.strip().lower()
            if normalized in self._alias_map:
                internal_name = self._alias_map[normalized]
                renamed[col] = internal_name
                self._original_headers[internal_name] = col
            else:
                # Column has no alias mapping; keep as-is
                self._original_headers[col] = col
        
        if renamed:
            df = df.rename(columns=renamed)
        
        return df
    
    def load_csv(self, path: str) -> None:
        """
        Load CSV file into dataframe.

        Column aliases in the CSV header are automatically detected and normalized
        to internal column names. The original headers are preserved for save.

        Args:
            path: Path to CSV file

        Raises:
            ValueError: If file is missing required columns
        """
        with open(path, "r", encoding="cp1252") as f:
            raw_lines = f.readlines()

        # Identify the header line (first non-empty, non-comment line)
        header_idx: Optional[int] = None
        for i, line in enumerate(raw_lines):
            stripped = line.strip()
            if stripped and not stripped.startswith(","):
                header_idx = i
                break

        if header_idx is None:
            raise ValueError("CSV file has no valid header")

        # Build filtered content: skip comment/empty lines, prepend original line numbers
        data_lines: List[str] = []
        for i, line in enumerate(raw_lines):
            stripped = line.strip()
            if i == header_idx:
                # Header line — prepend 'line_number' column name
                if not stripped.startswith("line_number"):
                    data_lines.append(f"line_number,{line}" if stripped else line)
            elif stripped and stripped.startswith(","):
                continue  # comment line
            elif stripped == "":
                continue  # empty line
            else:
                data_lines.append(f"{i + 1},{line}")

        csv_content = "".join(data_lines)
        self.df = pd.read_csv(StringIO(csv_content), encoding="cp1252", dtype=str, header=0)

        # Ensure the first column is named 'line_number'
        first_col = self.df.columns[0]
        if first_col != "line_number":
            self.df.rename(columns={first_col: "line_number"}, inplace=True)
        self.df["line_number"] = (
            pd.to_numeric(self.df["line_number"], errors="coerce")
            .fillna(0)
            .astype(int)
        )

        # Normalize column names (detect aliases, store original headers)
        self.df = self._normalize_columns(self.df)

        # Convert integer columns (hierarchy + stats)
        for col in self.HIERARCHY_COLS + self.INT_COLUMNS:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors="coerce").astype("Int64")

        # Validate required columns
        missing = [c for c in self.REQUIRED_COLUMNS if c not in self.df.columns]
        if missing:
            raise ValueError(f"CSV is missing required columns: {missing}")

        self.filepath = path
    
    def save_csv(self, path: str) -> None:
        """
        Save dataframe to CSV file using the original file's column headers.
        
        If the data was loaded from a file, the original CSV headers are restored.
        If no file was loaded (or headers were lost), default internal names are used.
        
        Args:
            path: Path to save CSV file to
            
        Raises:
            ValueError: If no dataframe is loaded
        """
        df = self._ensure_df().copy()
        
        # Remove internal 'line_number' column before saving
        if "line_number" in df.columns:
            df = df.drop(columns=["line_number"])
        
        # Map internal names back to original headers
        if self._original_headers:
            rename_map = {
                internal: original
                for internal, original in self._original_headers.items()
                if internal in df.columns
            }
            df = df.rename(columns=rename_map)
        
        df.to_csv(path, encoding="cp1252", index=False)
        self.filepath = path
    
    def save_scenario(self, scenario_dir: str, map_name: str, oob_filename: str) -> None:
        """
        Save a scenario CSV file in the specified directory.

        Maps OOB internal columns to scenario.csv columns where they match,
        leaving unmatched columns empty.

        Args:
            scenario_dir: Directory to save the scenario.csv file in
            map_name: Name of the map for the scenario - to be added to scenario.ini
            oob_name: Name of the OOB for the scenario - to be added to top line of scenario.csv
        """
        import os
        df = self._ensure_df().copy()

        # Remove internal 'line_number' column
        if "line_number" in df.columns:
            df = df.drop(columns=["line_number"])

        # Scenario CSV column order (from template)
        scenario_cols = [
            "userName", "id", "sideIndex", "armyIndex", "corpsIndex", "divisionIndex", "brigadeIndex", "regimentIndex", "battalionIndex", 
            "ammo", "dirSouth", "dirEast", "south", "east", "formation", "headCount", "fatigue", "morale"
        ]

        # Mapping: scenario column -> OOB internal column (None = leave empty)
        scenario_to_oob = {
            "userName": "NAME1",
            "id": "ID",
            "sideIndex": "SIDE 1",
            "armyIndex": "ARMY 2",
            "corpsIndex": "CORPS 3",
            "divisionIndex": "DIV 4",
            "brigadeIndex": "BGDE 5",
            "regimentIndex": "BTN 6",
            "battalionIndex": None,  # no OOB equivalent
            "ammo": "AMMO",
            "dirSouth": None,        # no OOB equivalent
            "dirEast": None,         # no OOB equivalent
            "south": None,           # no OOB equivalent
            "east": None,            # no OOB equivalent
            "formation": "Formation",
            "headCount": "Head Count",
            "fatigue": "Fatigue",
            "morale": "Morale"
         }

        scenario_df = pd.DataFrame()

        # Integer columns that should default to 0 instead of empty string
        int_columns = set(self.HIERARCHY_COLS + self.INT_COLUMNS)

        for scenario_col in scenario_cols:
            oob_col = scenario_to_oob.get(scenario_col)
            if oob_col and oob_col in df.columns:
                if oob_col in int_columns:
                    scenario_df[scenario_col] = df[oob_col].fillna(0)
                else:
                    scenario_df[scenario_col] = df[oob_col].fillna("")
            else:
                scenario_df[scenario_col] = ""

        os.makedirs(scenario_dir, exist_ok=True)
        path = os.path.join(scenario_dir, "scenario.csv")
        scenario_df.to_csv(path, encoding="cp1252", index=False)
        self.filepath = path

        # Insert a special MASTER line after the header (before data rows)
        with open(path, "r", encoding="cp1252") as f:
            lines = f.readlines()

        master_fields = ["MASTER", oob_filename] + [""] * (len(scenario_cols) - 2)
        master_line = ",".join(master_fields) + "\n"
        lines.insert(1, master_line)

        with open(path, "w", encoding="cp1252") as f:
            f.writelines(lines)

        # Copy template files into the scenario directory
        _copy_templates(scenario_dir)
    

    def get_row(self, row_index: int) -> pd.Series:
        """Get a single row by index."""
        return self._ensure_df().iloc[row_index]
    
    def set_cell(self, row_index: int, column: str, value: Any) -> None:
        """Update a cell value in the dataframe."""
        self._ensure_df().at[row_index, column] = value
    
    def _ensure_df(self) -> pd.DataFrame:
        """Raise if no dataframe is loaded; otherwise return it."""
        if self.df is None:
            raise ValueError("No data loaded")
        return self.df

    def _validate_and_key(self, row: pd.Series, row_index: int) -> Tuple[int, ...]:
        """Extract hierarchy key from a row, raising on invalid data."""
        key: List[int] = []
        for col in self.HIERARCHY_COLS:
            val = row.get(col, 0)
            if pd.isna(val):
                print(f"OOB Hierarchy Warning: Line {row_index + 2}: Column '{col}' is missing or empty (expected an integer)\nAttempting to treat as 0, this really should be fixed though!\n")
                val = 0  # treat missing hierarchy values as 0, but print a warning to console
            try:
                key.append(int(val))
            except (ValueError, TypeError):
                raise ValueError(f"Line {row_index + 2}: Column '{col}' has invalid value '{val}' (expected an integer)")
        return tuple(key)

    def _find_subordinate_indices(self, hierarchy_key: Tuple[int, ...], level: int) -> List[int]:
        """
        Find all row indices that are the unit itself or its subordinates.

        A row matches when its hierarchy key shares the first *level* components
        with *hierarchy_key*.
        """
        df = self._ensure_df()
        matches: List[int] = []

        for idx, df_row in df.iterrows():
            try:
                df_key = self._validate_and_key(df_row, idx)
            except ValueError:
                continue
            if all(hierarchy_key[i] == df_key[i] for i in range(level)):
                matches.append(idx)

        return matches

    # ------------------------------------------------------------------
    # Hierarchy utilities
    # ------------------------------------------------------------------

    def get_level_from_hierarchy(self, row: pd.Series) -> Optional[int]:
        """
        Determine hierarchy level from SIDE, ARMY, CORPS, DIV, BGDE, BTN columns.

        Returns the level (1-6) based on the deepest non-zero column:
        - Level 1: SIDE only
        - Level 2: SIDE + ARMY
        - Level 3: SIDE + ARMY + CORPS
        - Level 4: SIDE + ARMY + CORPS + DIV
        - Level 5: SIDE + ARMY + CORPS + DIV + BGDE (with BTN = 0, brigade commander)
        - Level 6: SIDE + ARMY + CORPS + DIV + BGDE + BTN (regiment/battalion)
        """
        level = 0
        for col in self.HIERARCHY_COLS:
            val = row.get(col, 0)
            if pd.notna(val) and val != 0:
                level += 1
            elif pd.notna(val) and val == 0:
                break
        return level if level > 0 else None

    def get_hierarchy_key(self, row: pd.Series, row_index: int) -> Tuple[int, ...]:
        """
        Get a unique hierarchical key for a unit based on SIDE, ARMY, CORPS, DIV, BGDE, BTN.

        Returns a tuple like (1, 1, 2, 3, 4, 0) representing the full hierarchical path.

        Raises:
            ValueError: If any hierarchy column contains invalid data
        """
        return self._validate_and_key(row, row_index)

    def get_parent_key(self, hierarchy_key: Tuple[int, ...]) -> Tuple[int, ...]:
        """
        Get the parent's hierarchy key by setting the last non-zero value to 0.

        For example: (1, 1, 2, 3, 4, 1) -> (1, 1, 2, 3, 4, 0)
                     (1, 1, 2, 3, 4, 0) -> (1, 1, 2, 3, 0, 0)
        """
        key = list(hierarchy_key)
        for i in range(len(key) - 1, -1, -1):
            if key[i] != 0:
                key[i] = 0
                break
        return tuple(key)

    def get_hierarchy_level_name_and_index(self, hierarchy_key: Tuple[int, ...]) -> str:
        """
        Get the hierarchy level name and its index.

        For example: (1, 1, 2, 3, 4, 0) -> "Brigade (4)"
                     (1, 1, 2, 0, 0, 0) -> "Corps (2)"
        """
        for i in range(len(hierarchy_key) - 1, -1, -1):
            if hierarchy_key[i] != 0:
                return f"{self.LEVEL_NAMES[i]} ({hierarchy_key[i]})"
        return "Unknown"

    # ------------------------------------------------------------------
    # Subordinate operations
    # ------------------------------------------------------------------

    def get_subordinate_row_indices(self, row_index: int) -> List[int]:
        """
        Get all subordinate row indices for a given unit.

        Args:
            row_index: Index of the unit

        Returns:
            List of row indices including the unit itself and all subordinates

        Raises:
            ValueError: If row_index is invalid or hierarchy data is corrupted
        """
        row = self.get_row(row_index)
        hierarchy_key = self.get_hierarchy_key(row, row_index)
        level = self.get_level_from_hierarchy(row)

        if level is None:
            raise ValueError(f"Line {row_index + 2}: Cannot determine hierarchy level")

        return self._find_subordinate_indices(hierarchy_key, level)

    def delete_unit(self, row_index: int) -> int:
        """
        Delete a unit and all its subordinates from the dataframe.

        Args:
            row_index: Index of the unit to delete

        Returns:
            Number of units deleted (including subordinates)

        Raises:
            ValueError: If row_index is invalid or hierarchy data is corrupted
        """
        row = self.get_row(row_index)
        hierarchy_key = self.get_hierarchy_key(row, row_index)
        level = self.get_level_from_hierarchy(row)

        if level is None:
            raise ValueError(f"Line {row_index + 2}: Cannot determine hierarchy level")

        rows_to_delete = self._find_subordinate_indices(hierarchy_key, level)

        for idx in sorted(rows_to_delete, reverse=True):
            self.df.drop(idx, inplace=True)

        self.df.reset_index(drop=True, inplace=True)
        return len(rows_to_delete)

    # ------------------------------------------------------------------
    # Stubbed future features
    # ------------------------------------------------------------------

    def insert_unit_template(self, parent_row_index: int, unit_name: str) -> int:
        """Insert a new unit template under the given parent unit. (Not yet implemented.)"""
        raise NotImplementedError("Unit template insertion not yet implemented")

    def copy_unit(self, row_index: int) -> Dict[str, Any]:
        """Copy a unit's data to an internal clipboard. (Not yet implemented.)"""
        raise NotImplementedError("Unit copy not yet implemented")

    def paste_unit(self, parent_row_index: int, clipboard_data: Dict[str, Any]) -> int:
        """Paste a unit from clipboard as a duplicate under the given parent. (Not yet implemented.)"""
        raise NotImplementedError("Unit paste not yet implemented")


def _copy_templates(scenario_dir: str):
    """Copy template files from the templates/ folder into the scenario directory."""
    import shutil
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
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
