import math
import re
import random
import traceback
import numpy as np
import pandas as pd
from io import StringIO
from typing import Tuple, List, Optional, Dict, Any, NamedTuple
import os

from constants import (
    COLUMN_ALIASES, HIERARCHY_COLS, LEVEL_NAMES, INT_COLUMNS, REQUIRED_COLUMNS,
    SPRITE_SCALE,
)


class UnitInfo(NamedTuple):
    """Lightweight view-model for a single OOB row."""
    row_index: int
    name: str
    side: int
    level: Optional[int]
    formation: str
    head_count: int

    def to_drag_payload(self) -> dict:
        """Compact dict suitable for JSON-serialized drag/drop payloads."""
        return {
            "row_index": self.row_index,
            "name": self.name,
            "side": self.side,
            "level": self.level if self.level is not None else 1,
            "formation": self.formation,
            "head_count": self.head_count,
        }

    @classmethod
    def from_drag_payload(cls, payload: dict) -> "UnitInfo":
        """Inverse of :meth:`to_drag_payload`."""
        return cls(
            row_index=int(payload.get("row_index", -1)),
            name=str(payload.get("name", "Unknown")),
            side=int(payload.get("side", 1)),
            level=payload.get("level"),
            formation=str(payload.get("formation", "")),
            head_count=int(payload.get("head_count", 0)),
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
        self._subordinate_cache: Dict[int, List[int]] = {}
        self._formation_cache: Dict[Tuple[int, Optional[str]], "ActualFormation"] = {}

        # Adjacency index: built once per load. ``None`` until _ensure_built.
        self._parent_to_children: Optional[Dict[int, List[int]]] = None
        self._children_set: set = set()  # all row indices that appear as a child

        # Template variation caches
        self._pool_cache: Dict[str, List[str]] = {}
        self._seq_counters: Dict[Tuple[int, str], int] = {}
        self._cycle_counters: Dict[Tuple[int, str], int] = {}
        self._level_by_row: Optional[np.ndarray] = None
        self._hierarchy_keys: Optional[np.ndarray] = None  # shape (n_rows, 6) int64

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
        self._subordinate_cache.clear()
        self._formation_cache.clear()
        self._parent_to_children = None
        self._children_set = set()
        self._level_by_row = None
        self._hierarchy_keys = None

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
        self._build_adjacency_index()

    def _df_sorted_by_hierarchy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return df rows sorted by hierarchy key to match tree view order."""
        keys = np.array(
            [list(self.get_hierarchy_key_by_index(i)) for i in range(len(df))],
            dtype=np.int64,
        )
        order = np.lexsort(keys.T[::-1])
        return df.iloc[order].reset_index(drop=True)

    def save_csv(self, path: str) -> None:
        df = self._df_sorted_by_hierarchy(self._ensure_df().copy())
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

    def save_scenario(self, scenario_dir: str, map_name: str, oob_filename: str, placed_units, objectives=None) -> None:
        import os
        df = self._df_sorted_by_hierarchy(self._ensure_df().copy())
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
                    if pu.get("formation"):
                        scenario_df.at[i, "formation"] = pu["formation"]

        # Only save rows for units that were placed on the map.
        if placed_units:
            placed_row_indices = set(pu["row_index"] for pu in placed_units)
            scenario_df = scenario_df[scenario_df.index.isin(placed_row_indices)].reset_index(drop=True)

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

        # Write objectives to maplocations.csv
        if objectives:
            maplocations_header = [
                "Name", "ID", "Priority", "Type", "AI",
                "loc x", "loc z", "radius", "Men", "Points",
                "Fatigue", "Morale", "Ammo", "OccMod",
                "Beg", "End", "Interval", "Sprite",
                "Army1", "Army2", "Army3",
            ]
            maplocations_path = os.path.join(scenario_dir, "maplocations.csv")
            with open(maplocations_path, "w", encoding="cp1252") as f:
                f.write(",".join(maplocations_header) + "\n")
                for obj in objectives:
                    fields = obj.get("fields", {})
                    row = ",".join(str(fields.get(col, "")) for col in maplocations_header)
                    f.write(row + "\n")

        if map_name:
            ini_path = os.path.join(scenario_dir, "scenario.ini")
            if os.path.exists(ini_path):
                with open(ini_path, "r", encoding="cp1252") as f:
                    lines = f.readlines()
                in_init = False
                for i, line in enumerate(lines):
                    stripped = line.strip().lower()
                    if stripped.startswith("[") and stripped.endswith("]"):
                        in_init = (stripped == "[init]")
                    elif in_init and stripped.startswith("map="):
                        lines[i] = f"map={map_name}\n"
                        break
                with open(ini_path, "w", encoding="cp1252") as f:
                    f.writelines(lines)

    # ── Row access ─────────────────────────────────────────────────

    def get_row(self, row_index: int) -> pd.Series:
        return self._ensure_df().iloc[row_index]

    def set_cell(self, row_index: int, column: str, value: Any) -> None:
        import numpy as np
        col_dtype = self._ensure_df()[column].dtype
        if value is not pd.NA and value is not None and str(value).strip() != "":
            try:
                kind = col_dtype.kind
            except AttributeError:
                kind = None
            if kind in ("i", "u"):  # signed or unsigned integer
                value = int(float(value))
            elif kind == "f":  # float
                value = float(value)
        self._ensure_df().at[row_index, column] = value
        self._invalidate_caches()

    def _ensure_df(self) -> pd.DataFrame:
        if self.df is None:
            raise ValueError("No data loaded")
        return self.df

    # ── Hierarchy utilities ────────────────────────────────────────

    def get_level_from_hierarchy(self, row: pd.Series) -> Optional[int]:
        """Legacy row-based level lookup. Prefer get_level(row_index)."""
        return self.get_level(self._row_index_of(row))

    def get_hierarchy_key(self, row: pd.Series, row_index: int) -> Tuple[int, ...]:
        """Legacy row+index-based hierarchy key lookup. Prefer get_hierarchy_key(row_index)."""
        return self.get_hierarchy_key_by_index(row_index)

    def _row_index_of(self, row: pd.Series) -> int:
        """Recover the positional index of a row from a Series returned by iloc."""
        try:
            return int(row.name)
        except Exception:
            return -1

    def get_level(self, row_index: int) -> Optional[int]:
        """Return the hierarchy level (1-6) of ``row_index``, or None if unknown."""
        self._ensure_built()
        lvl = int(self._level_by_row[row_index])
        return lvl if lvl > 0 else None

    def get_hierarchy_key_by_index(self, row_index: int) -> Tuple[int, ...]:
        """Return the cached hierarchy key tuple for ``row_index``."""
        self._ensure_built()
        return tuple(int(v) for v in self._hierarchy_keys[row_index])

    def get_row_index_by_key(self, hierarchy_key: Tuple[int, ...]) -> Optional[int]:
        """Return the row_index whose hierarchy key matches, or None if not found."""
        self._ensure_built()
        target = np.array(hierarchy_key, dtype=np.int64)
        for i, k in enumerate(self._hierarchy_keys):
            if np.array_equal(k, target):
                return i
        return None

    def get_parent_key(self, hierarchy_key: Tuple[int, ...]) -> Tuple[int, ...]:
        """Get the parent's hierarchy key by setting the last non-zero value to 0."""
        key = list(hierarchy_key)
        for i in range(len(key) - 1, -1, -1):
            if key[i] != 0:
                key[i] = 0
                break
        return tuple(key)

    def is_orphaned(self, row_index: int) -> bool:
        """Check if a unit has no parent row in the tree (orphaned)."""
        self._ensure_built()
        key = self.get_hierarchy_key_by_index(row_index)
        parent_key = self.get_parent_key(key)
        # A unit is orphaned if all positions in its key are 0 (side level)
        # or if its parent key doesn't resolve to any existing row
        if all(v == 0 for v in key):
            return True
        return self.get_row_index_by_key(parent_key) is None

    def get_hierarchy_level_name_and_index(self, hierarchy_key: Tuple[int, ...]) -> str:
        for i in range(len(hierarchy_key) - 1, -1, -1):
            if hierarchy_key[i] != 0:
                return f"{LEVEL_NAMES[i]} ({hierarchy_key[i]})"
        return "Unknown"

    # ── Adjacency index (O(1) per-row lookups, O(subtree) subordinates) ──

    def _ensure_built(self) -> None:
        if self._hierarchy_keys is None:
            self._build_adjacency_index()

    def _build_adjacency_index(self) -> None:
        """Build parent_to_children, level_by_row, hierarchy_keys from current df."""
        df = self._ensure_df()
        n = len(df)
        if n == 0:
            self._parent_to_children = {}
            self._children_set = set()
            self._level_by_row = np.zeros(0, dtype=np.int64)
            self._hierarchy_keys = np.zeros((0, 6), dtype=np.int64)
            return
        h = df[HIERARCHY_COLS].to_numpy()
        h_int = np.where(pd.isna(h), 0, h).astype(np.int64)
        # Level = position of first zero (1-indexed), or 6 if all nonzero.
        is_zero = (h_int == 0)
        any_zero = is_zero.any(axis=1)
        first_zero = is_zero.argmax(axis=1)  # 0 if no zero, else first zero position
        level = np.where(any_zero, first_zero, 6).astype(np.int64)
        # Compute parent key: zero out the last non-zero position in each row.
        last_nz = (h_int != 0).sum(axis=1) - 1  # -1 if all zero
        has_nz = last_nz >= 0
        positions = np.arange(6)
        mask = has_nz[:, None] & (positions[None, :] == last_nz[:, None])
        parent_h = np.where(mask, 0, h_int)
        # Build key -> row_index mapping.
        key_to_row: Dict[Tuple[int, ...], int] = {
            tuple(row.tolist()): i for i, row in enumerate(h_int)
        }
        parent_to_children: Dict[int, List[int]] = {i: [] for i in range(n)}
        children_set: set = set()
        for i, key in enumerate(h_int):
            pkey = tuple(parent_h[i].tolist())
            if has_nz[i] and pkey != tuple(key.tolist()) and pkey in key_to_row:
                parent_idx = key_to_row[pkey]
                parent_to_children[parent_idx].append(i)
                children_set.add(i)
        # Sort children by hierarchy key for stable iteration.
        for children in parent_to_children.values():
            children.sort(key=lambda idx: tuple(h_int[idx].tolist()))
        self._parent_to_children = parent_to_children
        self._children_set = children_set
        self._level_by_row = level
        self._hierarchy_keys = h_int

    # ── Lightweight row accessors (centralize the row.get(...) boilerplate) ──

    def unit_info(self, row_index: int) -> UnitInfo:
        """Return a typed snapshot of the common fields for a row."""
        row = self.get_row(row_index)
        return UnitInfo(
            row_index=row_index,
            name=str(row.get("NAME1", f"Unit {row_index}")),
            side=int(row.get("SIDE 1") if pd.notna(row.get("SIDE 1")) else 1),
            level=self.get_level(row_index),
            formation=str(row.get("Formation") if pd.notna(row.get("Formation")) else ""),
            head_count=int(row.get("Head Count") if pd.notna(row.get("Head Count")) else 0),
        )

    def get_direct_children(self, row_index: int, exclude_supply: bool = True) -> List[int]:
        """Return indices of rows that are exactly one level below ``row_index``.

        If ``exclude_supply`` is True, supply-wagon rows are filtered out.
        Uses the precomputed parent->children index, so cost is O(k) where
        k is the number of direct children.
        """
        self._ensure_built()
        if self.get_level(row_index) is None:
            return []
        children = list(self._parent_to_children.get(row_index, []))
        if not exclude_supply or not children:
            return children
        # Filter by Formation column. Done in one vectorized pass.
        df = self._ensure_df()
        formations = df.iloc[children]["Formation"].astype(str).tolist()
        return [c for c, f in zip(children, formations) if "SupplyWagon" not in f]

    def build_strength(self, row_index: int, archetype_id: Optional[str] = None,
                       allow_top_level_formation_fallback: bool = True) -> "ActualFormation":
        """Recursively build an ActualFormation tree rooted at ``row_index``.

        If ``archetype_id`` is None and the unit is below level 6, the unit's
        own Formation column is used (with a one-time warning). When
        ``allow_top_level_formation_fallback`` is True and the unit is below
        level 3, the parent archetype is reused for its children (this is a
        historical hack that lets a level-3 formation describe a level-1/2
        unit's children).

        Results are memoized by ``(row_index, archetype_id, allow_top_level_formation_fallback)``
        until the next load/set_cell/delete.
        """
        from core.formation import ActualFormation, FormationArchetype

        cache_key = (row_index, archetype_id, allow_top_level_formation_fallback)
        cached = self._formation_cache.get(cache_key)
        if cached is not None:
            return cached

        self._ensure_built()
        level = self.get_level(row_index)
        if level is None:
            raise ValueError(f"Cannot determine level for row {row_index}")
        sub_row = self.get_row(row_index)
        if archetype_id is None:
            if level != 6:
                print("Warning: No archetype_id provided to build_strength, "
                      "defaulting to listed value in OOB data.")
            archetype_id = str(sub_row.get("Formation", "") or "")
        if level >= 6:
            head_count = int(sub_row.get("Head Count", 0) or 0)
            result = ActualFormation(
                archetype_id=archetype_id,
                strength=int(head_count / SPRITE_SCALE),
            )
            self._formation_cache[cache_key] = result
            return result
        direct_children = self.get_direct_children(row_index, exclude_supply=True)
        archetype = FormationArchetype.formations.get(archetype_id) if archetype_id else None
        if level < 3 and allow_top_level_formation_fallback:
            child_formation = archetype_id
        else:
            child_formation = archetype.sub_form if archetype and archetype.sub_form else None
        sub_formations: List[Optional[ActualFormation]] = [None, None] + [
            self.build_strength(idx, archetype_id=child_formation) for idx in direct_children
        ]
        result = ActualFormation(archetype_id=archetype_id, strength=sub_formations)
        self._formation_cache[cache_key] = result
        return result

    # ── Subordinate operations ─────────────────────────────────────

    def get_subordinate_row_indices(self, row_index: int) -> List[int]:
        """Get all subordinate row indices including the unit itself.

        Walks the precomputed parent->children index, so cost is O(subtree size)
        rather than O(N). Results are cached per row_index.
        """
        if row_index in self._subordinate_cache:
            return self._subordinate_cache[row_index]

        self._ensure_built()
        if self.get_level(row_index) is None:
            raise ValueError(f"Line {row_index + 2}: Cannot determine hierarchy level")

        result: List[int] = [row_index]
        stack: List[int] = list(self._parent_to_children.get(row_index, []))
        while stack:
            i = stack.pop()
            result.append(i)
            children = self._parent_to_children.get(i)
            if children:
                stack.extend(children)
        self._subordinate_cache[row_index] = result
        return result

    def delete_unit(self, row_index: int) -> int:
        self._ensure_built()
        if self.get_level(row_index) is None:
            raise ValueError(f"Line {row_index + 2}: Cannot determine hierarchy level")
        rows_to_delete = self.get_subordinate_row_indices(row_index)
        keep_mask = np.ones(len(self.df), dtype=bool)
        keep_mask[rows_to_delete] = False
        self.df = self.df.loc[keep_mask].reset_index(drop=True)
        self._invalidate_caches()
        self._build_adjacency_index()
        return len(rows_to_delete)

    def delete_rows(self, row_indices: set) -> int:
        self._ensure_built()
        if not row_indices:
            return 0
        keep_mask = np.ones(len(self.df), dtype=bool)
        keep_mask[list(row_indices)] = False
        self.df = self.df.loc[keep_mask].reset_index(drop=True)
        self._invalidate_caches()
        self._build_adjacency_index()
        return len(row_indices)

    # ── Move / Insert / Regenerate ─────────────────────────────────

    def move_unit(self, row_index: int, direction: int) -> bool:
        """Move a unit up (-1) or down (+1) among its siblings.

        Swaps the hierarchy column value at the unit's level with the adjacent
        sibling at that level.  All descendants of both the source and target
        rows have their column at that level swapped so parent references stay
        consistent.  Deeper hierarchy levels are preserved unchanged.
        Returns True if the move was performed, False if already at the boundary.
        """
        self._ensure_built()
        level = self.get_level(row_index)
        if level is None:
            return False

        parent_key = self.get_parent_key(self.get_hierarchy_key_by_index(row_index))
        parent_row = next((i for i, k in enumerate(self._hierarchy_keys)
                           if tuple(k) == parent_key), -1)
        siblings = self._parent_to_children.get(parent_row, [])
        if not siblings:
            return False

        # Find current position among siblings
        current_pos = None
        for pos, sib_idx in enumerate(siblings):
            if sib_idx == row_index:
                current_pos = pos
                break
        if current_pos is None:
            return False

        target_pos = current_pos + direction
        if target_pos < 0 or target_pos >= len(siblings):
            return False

        source = row_index
        target = siblings[target_pos]

        # Collect all rows in both subtrees (before any mutation).
        def collect_subtree(idx: int) -> set:
            rows: List[int] = []
            stack: List[int] = [idx]
            while stack:
                cur = stack.pop()
                if cur in rows:
                    continue
                rows.append(cur)
                for child in self._parent_to_children.get(cur, []):
                    if child not in rows:
                        stack.append(child)
            return set(rows)

        source_rows = collect_subtree(source)
        target_rows = collect_subtree(target)

        # Swap the hierarchy column value at the move level for every row in
        # both subtrees.  Deeper levels are left untouched.
        level_col_idx = level - 1
        col = HIERARCHY_COLS[level_col_idx]
        source_val = self.df.at[source, col]
        target_val = self.df.at[target, col]
        for r in source_rows:
            self.df.at[r, col] = target_val
        for r in target_rows:
            self.df.at[r, col] = source_val

        self._invalidate_caches()
        self._build_adjacency_index()
        return True

    def reparent_unit(self, row_index: Optional[int], target_row_index: int,
                      peer_drop: bool, new_row_data: Optional[Dict[str, Any]] = None,
                      source_level: Optional[int] = None,
                      parent_drop: bool = False) -> Any:
        """Reparent a unit subtree OR insert a new unit at a target location.

        This method serves two purposes:
        1. Move an existing unit (and its subtree) to a new parent or peer
           position. Pass row_index=int, new_row_data=None. Returns True/False.
        2. Insert a new unit from template data at a target location.
           Pass row_index=None, new_row_data=column dict. Returns new row index.

        Placement rules (same for both modes):
        - peer_drop=True: target is at the same level; insert AFTER the target
          under the target's parent, renumbering siblings as needed.
        - peer_drop=False, parent_drop=False: target is one level above;
          insert as the last child of the target.
        - parent_drop=True: target is one level below; insert a new parent
          ABOVE the target. Target becomes a child of the new parent.
          Only allowed when target level > 1.

        Args:
            row_index: The unit to move (its full subtree follows), or None
                for insert mode.
            target_row_index: The drop target.
            peer_drop: Peer vs child placement.
            new_row_data: Column dict for the new row (insert mode only).
            source_level: The level of the unit being inserted (insert mode).
                For peer drops, equals target level. For child drops, equals
                target level + 1. For parent drops, equals target level - 1.
            parent_drop: If True, insert a new parent above the target.

        Returns the new row index (insert mode) or True/False (move mode).
        """
        self._ensure_built()
        target_level = self.get_level(target_row_index)
        if target_level is None:
            return False

        # Insert mode: determine source level and validate
        if new_row_data is not None:
            if source_level is None:
                return False
            if parent_drop:
                if source_level != target_level - 1:
                    return False
                if target_level <= 1:
                    return False
                if not self.is_orphaned(target_row_index):
                    return False
            elif peer_drop:
                if source_level != target_level:
                    return False
            else:
                if source_level != target_level + 1:
                    return False
        else:
            # Move mode: validate source
            if row_index is None:
                return False
            source_level = self.get_level(row_index)
            if source_level is None:
                return False
            if target_row_index == row_index:
                return False
            if self.is_descendant_of(target_row_index, row_index):
                return False
            if peer_drop and source_level != target_level:
                return False
            if not peer_drop and source_level != target_level + 1:
                return False

        if peer_drop:
            target_key = self.get_hierarchy_key_by_index(target_row_index)
            new_parent_key = self.get_parent_key(target_key)
            target_l_value = target_key[source_level - 1]
            new_l_value = target_l_value + 1
            # Renumber siblings at level L and all their descendants at
            # deeper levels so subunit keys stay consistent.
            for i in range(len(self.df)):
                level_i = self.get_level(i)
                if level_i is None or level_i < source_level:
                    continue
                k = self.get_hierarchy_key_by_index(i)
                if k[:source_level - 1] != new_parent_key[:source_level - 1]:
                    continue
                existing_val = k[source_level - 1]
                if existing_val >= new_l_value:
                    self.df.at[i, HIERARCHY_COLS[source_level - 1]] = existing_val + 1
        elif parent_drop and new_row_data is not None:
            # Parent drop (orphaned unit only): new parent goes above the target.
            # Use the target's own parent-level key value to create the parent
            # it never had.
            target_key = self.get_hierarchy_key_by_index(target_row_index)
            new_l_value = target_key[source_level - 1]
            new_parent_key = [0] * (source_level - 1) + [new_l_value] + [0] * (6 - source_level)
        else:
            new_parent_key = self.get_hierarchy_key_by_index(target_row_index)
            existing_indices = []
            for c in self._parent_to_children.get(target_row_index, []):
                if self.get_level(c) == source_level:
                    val = self.df.at[c, HIERARCHY_COLS[source_level - 1]]
                    if pd.notna(val) and val != 0:
                        existing_indices.append(int(val))
            new_l_value = max(existing_indices) + 1 if existing_indices else 1

        new_prefix = list(new_parent_key[:source_level - 1])

        if new_row_data is not None:
            # Insert mode: create a single new row
            new_row = {col: new_row_data.get(col, "") for col in self.df.columns}
            for i, hcol in enumerate(HIERARCHY_COLS):
                new_row[hcol] = new_prefix[i] if i < source_level - 1 else (
                    new_l_value if i == source_level - 1 else 0)
            new_row["line_number"] = ""

            # Determine actual parent row for modifier resolution
            if peer_drop:
                actual_parent = self.get_row_index_by_key(new_parent_key)
                if actual_parent is None:
                    actual_parent = target_row_index
            elif parent_drop:
                actual_parent = target_row_index
            else:
                actual_parent = target_row_index

            # Resolve template modifiers (seq, pool, range, pick)
            self._resolve_modifiers(new_row, actual_parent)

            # Assign a unique ID by appending an index to the template ID
            template_id = str(new_row.get("ID", "")).strip()
            if template_id and "ID" in self.df.columns:
                used_indices = set()
                for val in self.df["ID"].dropna():
                    val_str = str(val).strip()
                    if val_str.startswith(template_id) and val_str != template_id:
                        suffix = val_str[len(template_id):]
                        try:
                            used_indices.add(int(suffix))
                        except ValueError:
                            pass
                idx = 1
                while idx in used_indices:
                    idx += 1
                new_row["ID"] = f"{template_id}{idx}"

            new_df = pd.DataFrame([new_row])
            for col in INT_COLUMNS:
                if col in new_df.columns:
                    new_df[col] = pd.to_numeric(new_df[col], errors="coerce").astype("Int64")

            if parent_drop:
                # Collect target's subtree BEFORE insertion (indices will shift)
                subtree_rows = self._collect_subtree_rows(target_row_index)
                # Remove target from subtree set — we handle it separately
                subtree_rows.discard(target_row_index)

                # Insert new parent row BEFORE the target
                before = self.df.iloc[:target_row_index]
                after = self.df.iloc[target_row_index:]
                self.df = pd.concat([before, new_df, after], ignore_index=True)

                # New parent is at target_row_index
                # Target shifted to target_row_index + 1
                new_target_idx = target_row_index + 1

                # Target becomes first child of new parent: L=1 at its level
                target_new_key = list(new_parent_key[:target_level - 1]) + [1] + [0] * (6 - target_level + 1)
                for i, hcol in enumerate(HIERARCHY_COLS):
                    self.df.at[new_target_idx, hcol] = target_new_key[i]

                # Update descendants: replace old target prefix with new target prefix
                for old_idx in subtree_rows:
                    new_idx = old_idx + 1  # Shifted by insertion
                    old_key = [self.df.at[new_idx, hcol] for hcol in HIERARCHY_COLS]
                    new_key = list(target_new_key[:target_level]) + list(old_key[target_level:])
                    for i, hcol in enumerate(HIERARCHY_COLS):
                        self.df.at[new_idx, hcol] = new_key[i]

                self._invalidate_caches()
                self._build_adjacency_index()
                return target_row_index  # Return new parent's index
            else:
                new_row_idx = len(self.df)
                self.df = pd.concat([self.df, new_df], ignore_index=True)
                self._invalidate_caches()
                self._build_adjacency_index()
                return new_row_idx
        else:
            # Move mode: rewrite hierarchy keys for the entire subtree
            subtree_rows = self._collect_subtree_rows(row_index)
            for r in subtree_rows:
                old_key = self.get_hierarchy_key_by_index(r)
                new_key = new_prefix + [new_l_value] + list(old_key[source_level:])
                for i, hcol in enumerate(HIERARCHY_COLS):
                    self.df.at[r, hcol] = new_key[i]
            self._invalidate_caches()
            self._build_adjacency_index()
            return True

    def _collect_subtree_rows(self, row_index: int) -> set:
        """Collect all row indices in the subtree rooted at row_index (including itself)."""
        rows: set = set()
        stack: List[int] = [row_index]
        while stack:
            cur = stack.pop()
            if cur in rows:
                continue
            rows.add(cur)
            for child in self._parent_to_children.get(cur, []):
                if child not in rows:
                    stack.append(child)
        return rows

    def is_descendant_of(self, potential_descendant: int, ancestor: int) -> bool:
        """Check if potential_descendant is in the subtree of ancestor."""
        if potential_descendant == ancestor:
            return False
        return potential_descendant in self._collect_subtree_rows(ancestor)

    def insert_unit(self, parent_row_index: int, template_path: str) -> int:
        """Insert a new unit from a template CSV under the given parent.

        The template CSV should have a single data row (plus header).
        The hierarchy columns are set based on the parent's key, with the
        next available index for the child level.

        Returns the row index of the newly inserted unit.
        """
        self._ensure_built()
        parent_level = self.get_level(parent_row_index)
        if parent_level is None:
            raise ValueError("Cannot determine parent level")
        if parent_level >= 6:
            raise ValueError("Cannot add sub-units to a level 6 unit")

        parent_key = self.get_hierarchy_key_by_index(parent_row_index)
        child_level_idx = parent_level  # 0-indexed: parent_level=4 (Division) -> child at index 4 (BGDE 5)
        child_col = HIERARCHY_COLS[child_level_idx]

        # Find next available index for this child level
        existing_children = self._parent_to_children.get(parent_row_index, [])
        if existing_children:
            existing_indices = []
            for c in existing_children:
                val = self.df.at[c, child_col]
                if pd.notna(val) and val != 0:
                    existing_indices.append(int(val))
            next_index = max(existing_indices) + 1 if existing_indices else 1
        else:
            next_index = 1

        # Load the template CSV
        template_df = pd.read_csv(template_path, encoding="cp1252", dtype=str)
        template_df = self._normalize_columns(template_df)

        # Convert numeric columns
        for col in HIERARCHY_COLS + INT_COLUMNS:
            if col in template_df.columns:
                template_df[col] = pd.to_numeric(template_df[col], errors="coerce").astype("Int64")

        # Build the new hierarchy key
        new_key = list(parent_key)
        new_key[child_level_idx] = next_index

        # Set hierarchy columns in the template
        for i, hcol in enumerate(HIERARCHY_COLS):
            if hcol in template_df.columns:
                template_df[hcol] = new_key[i]
            else:
                template_df[hcol] = new_key[i]

        # Append to the DataFrame
        new_row_idx = len(self.df)
        self.df = pd.concat([self.df, template_df], ignore_index=True)

        self._invalidate_caches()
        self._build_adjacency_index()
        return new_row_idx

    def insert_formation(self, parent_row_index: int, composition: Dict[str, Any]) -> List[int]:
        """Insert a commander and composed sub-units under the given parent.

        ``composition`` has the form:
        {
            "commander_name": "Gen. Smith",
            "commander_level": 5,
            "commander_formation": "Infantry",
            "sub_units": [
                {"template": "lvl6_infantry", "count": 3},
                {"template": "lvl6_cavalry", "count": 1},
            ]
        }

        Returns a list of row indices of all newly inserted units.
        """
        self._ensure_built()
        parent_level = self.get_level(parent_row_index)
        if parent_level is None:
            raise ValueError("Cannot determine parent level")
        if parent_level >= 6:
            raise ValueError("Cannot add sub-units to a level 6 unit")

        parent_key = self.get_hierarchy_key_by_index(parent_row_index)
        child_level_idx = parent_level
        child_col = HIERARCHY_COLS[child_level_idx]

        # Find next available index
        existing_children = self._parent_to_children.get(parent_row_index, [])
        if existing_children:
            existing_indices = []
            for c in existing_children:
                val = self.df.at[c, child_col]
                if pd.notna(val) and val != 0:
                    existing_indices.append(int(val))
            next_index = max(existing_indices) + 1 if existing_indices else 1
        else:
            next_index = 1

        templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "units")
        inserted_indices = []

        # Insert the commander
        cmd_level = composition.get("commander_level", parent_level + 1)
        cmd_name = composition.get("commander_name", "New Commander")
        cmd_formation = composition.get("commander_formation", "")

        cmd_key = list(parent_key)
        cmd_key[child_level_idx] = next_index
        next_index += 1

        cmd_row = {col: "" for col in self.df.columns}
        cmd_row["NAME1"] = cmd_name
        cmd_row["Formation"] = cmd_formation
        for i, hcol in enumerate(HIERARCHY_COLS):
            cmd_row[hcol] = cmd_key[i]

        # Determine a template for the commander
        cmd_template_name = f"lvl{cmd_level}_infantry.csv" if cmd_level <= 6 else "lvl6_infantry.csv"
        cmd_template_path = os.path.join(templates_dir, cmd_template_name)
        if os.path.exists(cmd_template_path):
            cmd_template_df = pd.read_csv(cmd_template_path, encoding="cp1252", dtype=str)
            cmd_template_df = self._normalize_columns(cmd_template_df)
            for col in HIERARCHY_COLS + INT_COLUMNS:
                if col in cmd_template_df.columns:
                    cmd_template_df[col] = pd.to_numeric(cmd_template_df[col], errors="coerce").astype("Int64")
            if len(cmd_template_df) > 0:
                for col in cmd_row:
                    if col in cmd_template_df.columns:
                        val = cmd_template_df.iloc[0][col]
                        if pd.notna(val):
                            cmd_row[col] = val

        # Ensure hierarchy columns are set
        for i, hcol in enumerate(HIERARCHY_COLS):
            cmd_row[hcol] = cmd_key[i]

        cmd_df = pd.DataFrame([cmd_row])
        for col in HIERARCHY_COLS + INT_COLUMNS:
            if col in cmd_df.columns:
                cmd_df[col] = pd.to_numeric(cmd_df[col], errors="coerce").astype("Int64")

        cmd_row_idx = len(self.df)
        self.df = pd.concat([self.df, cmd_df], ignore_index=True)
        inserted_indices.append(cmd_row_idx)

        # Insert sub-units
        sub_units = composition.get("sub_units", [])
        for sub in sub_units:
            template_name = sub.get("template", "lvl6_infantry.csv")
            count = sub.get("count", 1)
            template_path = os.path.join(templates_dir, template_name)
            if not os.path.exists(template_path):
                continue

            template_df = pd.read_csv(template_path, encoding="cp1252", dtype=str)
            template_df = self._normalize_columns(template_df)
            for col in HIERARCHY_COLS + INT_COLUMNS:
                if col in template_df.columns:
                    template_df[col] = pd.to_numeric(template_df[col], errors="coerce").astype("Int64")

            for i in range(count):
                if len(template_df) > 0:
                    new_row = template_df.iloc[0].to_dict()
                else:
                    new_row = {col: "" for col in self.df.columns}

                sub_key = list(cmd_key)
                sub_key[child_level_idx + 1] = i + 1 if child_level_idx + 1 < 6 else 1
                for j in range(child_level_idx + 2, 6):
                    sub_key[j] = 0

                for hcol in HIERARCHY_COLS:
                    col_idx = HIERARCHY_COLS.index(hcol)
                    new_row[hcol] = sub_key[col_idx]

                sub_df = pd.DataFrame([new_row])
                for col in HIERARCHY_COLS + INT_COLUMNS:
                    if col in sub_df.columns:
                        sub_df[col] = pd.to_numeric(sub_df[col], errors="coerce").astype("Int64")

                sub_row_idx = len(self.df)
                self.df = pd.concat([self.df, sub_df], ignore_index=True)
                inserted_indices.append(sub_row_idx)

        self._invalidate_caches()
        self._build_adjacency_index()
        return inserted_indices

    def load_templates(self, templates_dir: str) -> List[Dict[str, Any]]:
        """Load all template units from CSV files in templates_dir.

        Each CSV uses the standard OOB header. Hierarchy columns contain 'X'
        to mark the template's valid level. Returns a list of dicts with
        keys: name, level, row, file, id.
        """
        if not os.path.isdir(templates_dir):
            return []

        templates: List[Dict[str, Any]] = []
        saved_headers = self._original_headers
        for fname in sorted(os.listdir(templates_dir)):
            if not fname.endswith(".csv"):
                continue
            fpath = os.path.join(templates_dir, fname)
            try:
                tdf = pd.read_csv(fpath, encoding="cp1252", dtype=str)
                self._original_headers = {}
                tdf = self._normalize_columns(tdf)
            except Exception:
                print(f"Error in loading template file {fname}: {traceback.format_exc()}")
                continue

            for _, row in tdf.iterrows():
                # Determine level from X in hierarchy columns
                level = None
                for li, hcol in enumerate(HIERARCHY_COLS):
                    if hcol in tdf.columns:
                        val = str(row.get(hcol, "")).strip().upper()
                        if val == "X":
                            level = li + 1
                            break
                if level is None:
                    continue

                name = str(row.get("Name", row.get("NAME1", "Unknown")))
                uid = str(row.get("ID", ""))
                row_dict = {col: row.get(col, "") for col in tdf.columns}
                templates.append({
                    "name": name,
                    "level": level,
                    "row": row_dict,
                    "file": fpath,
                    "id": uid,
                })
        self._original_headers = saved_headers
        return templates

    def save_as_template(self, row_index: int, templates_dir: str) -> str:
        """Save a unit as a user template. Creates user_templates.csv if needed.

        Reads headers from templates/headers/oob_headers.csv. Generates ID as
        OOB_USER_# (incrementing from max existing). Sets hierarchy columns:
        all empty except X at the unit's level.

        Returns the new ID string.
        """
        header_path = os.path.join(
            os.path.dirname(templates_dir), "headers", "oob_headers.csv")
        if not os.path.exists(header_path):
            raise FileNotFoundError(f"Header file not found: {header_path}")

        header_df = pd.read_csv(header_path, encoding="cp1252", dtype=str, nrows=0)
        header_cols = list(header_df.columns)

        unit_row = self.df.iloc[row_index]
        unit_level = self.get_level(row_index)
        if unit_level is None:
            raise ValueError("Cannot determine unit level")

        # Build the template row from header columns
        new_row = {}
        for col in header_cols:
            val = unit_row.get(col, "")
            new_row[col] = "" if pd.isna(val) else str(val)

        # Clear hierarchy columns and set X for the unit's level
        for hcol in HIERARCHY_COLS:
            new_row[hcol] = ""
        new_row[HIERARCHY_COLS[unit_level - 1]] = "X"

        # Determine next OOB_USER_LvlX_Y_ ID
        user_path = os.path.join(templates_dir, "user_templates.csv")
        level_count = 0
        if os.path.exists(user_path):
            existing = pd.read_csv(user_path, encoding="cp1252", dtype=str)
            existing = self._normalize_columns(existing)
            if "ID" in existing.columns:
                prefix = f"OOB_USER_Lvl{unit_level}_"
                for val in existing["ID"].dropna():
                    val_str = str(val).strip()
                    if val_str.startswith(prefix):
                        try:
                            num = int(val_str[len(prefix):].rstrip("_"))
                            level_count = max(level_count, num)
                        except ValueError:
                            pass
        new_id = f"OOB_USER_Lvl{unit_level}_{level_count + 1}_"
        new_row["ID"] = new_id

        # Write to file
        new_df = pd.DataFrame([new_row])[header_cols]
        if os.path.exists(user_path):
            existing = pd.read_csv(user_path, encoding="cp1252", dtype=str)
            existing = pd.concat([existing, new_df], ignore_index=True)
            existing.to_csv(user_path, index=False, encoding="cp1252")
        else:
            new_df.to_csv(user_path, index=False, encoding="cp1252")

        return new_id

    def load_pools(self, pools_dir: str) -> None:
        """Load name pools from .txt files in pools_dir.

        Each file becomes a pool keyed by its stem (e.g. 'french_commanders').
        Files are plain text with one entry per line.
        """
        if not os.path.isdir(pools_dir):
            return
        for fname in os.listdir(pools_dir):
            if not fname.endswith(".txt"):
                continue
            pool_name = fname[:-4]
            fpath = os.path.join(pools_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    self._pool_cache[pool_name] = lines
            except Exception:
                continue

    def _resolve_pool(self, pool_name: str) -> str:
        """Pick a random entry from a named pool."""
        entries = self._pool_cache.get(pool_name)
        if not entries:
            return f"{{{pool_name}}}"
        return random.choice(entries)

    def _resolve_seq(self, seq_name: str, parent_row_index: int,
                     suffix_pattern: str = "") -> int:
        """Get the next sequence number for a named sequence under a parent.

        On first call for a (parent, seq_name) combo, scans existing
        children's NAME1 for the suffix pattern to find the max number
        already in use. If no suffix is provided, starts from the child count.

        Args:
            seq_name: The sequence name (e.g. "us_inf").
            parent_row_index: The parent unit's row index.
            suffix_pattern: The resolved literal text after the seq
                placeholder (e.g. "th Regiment" from "{seq:us_inf}th Regiment").
                Used to match existing children and find the max number.
        """
        key = (parent_row_index, seq_name)
        if key not in self._seq_counters:
            max_num = 0
            if suffix_pattern:
                # Scan existing children for matching pattern: "N suffix_pattern"
                escaped = re.escape(suffix_pattern)
                match_re = re.compile(r'^(\d+)\s*' + escaped + r'$', re.IGNORECASE)
                children = self._parent_to_children.get(parent_row_index, [])
                for c in children:
                    name = str(self.df.at[c, "NAME1"])
                    m = match_re.match(name)
                    if m:
                        max_num = max(max_num, int(m.group(1)))
            else:
                children = self._parent_to_children.get(parent_row_index, [])
                max_num = len(children)
            self._seq_counters[key] = max_num + 1
        else:
            self._seq_counters[key] += 1
        return self._seq_counters[key]

    def _resolve_cycle(self, cycle_str: str, parent_row_index: int) -> str:
        """Cycle through a pipe-separated list of values.

        The list itself is the key. On first call for a (parent, list)
        combo, returns the first item. Each subsequent call advances to
        the next item, wrapping around when exhausted.

        Args:
            cycle_str: Pipe-separated values (e.g. "1|1|2|2|3|3" or "1er|2e").
            parent_row_index: The parent unit's row index.
        """
        items = [x.strip() for x in cycle_str.split("|")]
        if not items:
            return f"{{{cycle_str}}}"
        key = (parent_row_index, cycle_str)
        if key not in self._cycle_counters:
            self._cycle_counters[key] = 0
        idx = self._cycle_counters[key]
        result = items[idx % len(items)]
        self._cycle_counters[key] = idx + 1
        return result

    @staticmethod
    def _int_to_ordinal(n: int) -> str:
        """Convert an integer to an English ordinal numeral (e.g. 1→'1st')."""
        if 11 <= (n % 100) <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    def _resolve_rangeord(self, min_val: int, max_val: int) -> str:
        """Pick a random integer in [min, max] and return it as an ordinal."""
        return self._int_to_ordinal(random.randint(min_val, max_val))

    def _resolve_seqord(self, seq_name: str, parent_row_index: int,
                        suffix_pattern: str = "") -> str:
        """Like _resolve_seq but returns the result as an ordinal string."""
        num = self._resolve_seq(seq_name, parent_row_index, suffix_pattern)
        return self._int_to_ordinal(num)

    def _resolve_suffix_modifiers(self, text: str) -> str:
        """Resolve pool, range, rangeord, seq, seqord, and pick modifiers in a suffix string.

        Used to compute the actual match pattern for seq scanning.
        Pool picks use the first option for deterministic matching.
        Range uses 0. Seqord uses "1st" for deterministic matching.
        """
        def replace_pool(m):
            options = m.group(1).split("|")
            return options[0]
        def replace_range(m):
            return "0"
        def replace_rangeord(m):
            return "1st"
        def replace_seqord(m):
            return "1"
        def replace_pick(m):
            options = m.group(1).split("|")
            return options[0]
        text = re.sub(r'\{pool:([^}]+)\}', replace_pool, text)
        text = re.sub(r'\{range:(\d+)-(\d+)\}', replace_range, text)
        text = re.sub(r'\{rangeord:(\d+)-(\d+)\}', replace_rangeord, text)
        text = re.sub(r'\{seqord:([^}]+)\}', replace_seqord, text)
        text = re.sub(r'\{pick:([^}]+)\}', replace_pick, text)
        return text

    def _resolve_modifiers(self, row_dict: dict, parent_row_index: int) -> None:
        """Resolve all {modifier} placeholders in string fields of row_dict.

        Uses a two-pass approach for seq modifiers:
        1. First pass: extract seq names and compute suffix patterns by
           resolving nested modifiers in the raw text after each seq marker.
        2. Second pass: resolve all modifiers, using the precomputed suffix
           patterns for seq scanning.

        Modifiers:
            {seq:name}         - sequential number per (parent, name)
            {seqord:name}      - sequential ordinal per (parent, name) (1st, 2nd, ...)
            {cycle:v1|v2|...}  - cycling list per parent, wraps around
            {pool:name}        - random pick from named pool file
            {range:min-max}    - random integer in range
            {rangeord:min-max} - random ordinal in range (1st, 2nd, ...)
            {pick:a|b|c}       - random pick from list
        """
        seq_pattern = re.compile(r'\{seq(?:ord)?:([^}]+)\}')
        all_mods = re.compile(
            r'\{seqord:([^}]+)\}'
            r'|\{seq:([^}]+)\}'
            r'|\{cycle:([^}]+)\}'
            r'|\{pool:([^}]+)\}'
            r'|\{rangeord:(\d+)-(\d+)\}'
            r'|\{range:(\d+)-(\d+)\}'
            r'|\{pick:([^}]+)\}'
        )

        # First pass: compute suffix patterns for each seq/seqord in each field
        seq_suffixes: Dict[str, str] = {}
        for col in list(row_dict.keys()):
            val = row_dict[col]
            if not isinstance(val, str) or "{seq" not in val:
                continue
            for m in seq_pattern.finditer(val):
                seq_name = m.group(1)
                if seq_name not in seq_suffixes:
                    # Extract raw text after the seq marker to end of string
                    raw_suffix = val[m.end():]
                    # Resolve nested modifiers to get actual text pattern
                    seq_suffixes[seq_name] = self._resolve_suffix_modifiers(raw_suffix)

        # Second pass: resolve all modifiers
        def replacer(m):
            if m.group(1) is not None:
                seq_name = m.group(1)
                suffix = seq_suffixes.get(seq_name, "")
                return self._resolve_seqord(seq_name, parent_row_index, suffix)
            elif m.group(2) is not None:
                seq_name = m.group(2)
                suffix = seq_suffixes.get(seq_name, "")
                return str(self._resolve_seq(seq_name, parent_row_index, suffix))
            elif m.group(3) is not None:
                return self._resolve_cycle(m.group(3), parent_row_index)
            elif m.group(4) is not None:
                return self._resolve_pool(m.group(4))
            elif m.group(5) is not None and m.group(6) is not None:
                return self._resolve_rangeord(int(m.group(5)), int(m.group(6)))
            elif m.group(7) is not None and m.group(8) is not None:
                return str(random.randint(int(m.group(7)), int(m.group(8))))
            elif m.group(9) is not None:
                options = m.group(9).split("|")
                return random.choice(options)
            return m.group(0)

        for col in list(row_dict.keys()):
            val = row_dict[col]
            if isinstance(val, str) and "{" in val:
                row_dict[col] = all_mods.sub(replacer, val)

    def regenerate_hierarchy_indices(self) -> None:
        """Reassign hierarchy indices sequentially under each parent.

        Walks the tree top-down and renumbers children 1, 2, 3, ...
        under each parent.  Subtrees move with their parent.
        """
        self._ensure_built()
        if self.df is None or len(self.df) == 0:
            return

        # Build a mapping from row_index -> parent_key -> children list
        # Start from root nodes (those not in _children_set)
        roots = [i for i in range(len(self.df))
                 if i not in self._children_set and self.get_level(i) is not None]

        # Build a new hierarchy keys array (copy current)
        new_keys = self._hierarchy_keys.copy()

        def renumber_children(parent_idx: int, parent_key: Tuple[int, ...], counter: int = 1):
            """Recursively renumber children under parent_idx."""
            children = self._parent_to_children.get(parent_idx, [])
            # Sort by current hierarchy key for stable ordering
            children.sort(key=lambda idx: tuple(self._hierarchy_keys[idx].tolist()))
            for child_idx in children:
                level = int(self._level_by_row[child_idx])
                level_col_idx = level - 1
                # Update the hierarchy key
                new_key = list(parent_key)
                new_key[level_col_idx] = counter
                # Zero out deeper levels
                for j in range(level_col_idx + 1, 6):
                    new_key[j] = 0
                new_keys[child_idx] = np.array(new_key, dtype=np.int64)
                counter += 1
                # Recurse
                renumber_children(child_idx, tuple(new_key))

        for root_idx in roots:
            root_key = tuple(new_keys[root_idx].tolist())
            renumber_children(root_idx, root_key)

        # Write new keys back to the DataFrame
        for i, hcol in enumerate(HIERARCHY_COLS):
            self.df[hcol] = new_keys[:, i]

        self._invalidate_caches()
        self._build_adjacency_index()


def _copy_templates(scenario_dir: str):
    """Copy template files from the templates/scenario/ folder into the scenario directory."""
    import shutil
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "scenario")
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
