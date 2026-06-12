import numpy as np
import pandas as pd
from io import StringIO
from typing import Tuple, List, Optional, Dict, Set, Any, NamedTuple

from core.constants import (
    COLUMN_ALIASES, HIERARCHY_COLS, LEVEL_NAMES, INT_COLUMNS, REQUIRED_COLUMNS,
    SPRITE_SCALE,
)
from core.formation import detect_unit_type
from core.oob_templates import TemplateSystem
from core.oob_scenario import export_scenario


class UnitInfo(NamedTuple):
    """Lightweight view-model for a single OOB row."""
    row_index: int
    name: str
    side: int
    level: Optional[int]
    formation: str
    head_count: int
    class_value: str = ""

    def to_drag_payload(self) -> dict:
        """Compact dict suitable for JSON-serialized drag/drop payloads."""
        return {
            "row_index": self.row_index,
            "name": self.name,
            "side": self.side,
            "level": self.level if self.level is not None else 1,
            "formation": self.formation,
            "head_count": self.head_count,
            "class_value": self.class_value,
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
            class_value=str(payload.get("class_value", "")),
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
        self._original_df: Optional[pd.DataFrame] = None
        self._alias_map = {}
        self._build_alias_map()

        # Caches – invalidated on load / set_cell / delete
        self._subordinate_cache: Dict[int, List[int]] = {}
        self._formation_cache: Dict[Tuple[int, Optional[str]], "ActualFormation"] = {}

        # Adjacency index: built once per load. ``None`` until _ensure_built.
        self._parent_to_children: Optional[Dict[int, List[int]]] = None
        self._children_set: set = set()  # all row indices that appear as a child

        # Template system (extracted module)
        self.templates = TemplateSystem(self)
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

        self._original_df = self.df.copy(deep=True)

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

    def save_scenario(self, scenario_dir: str, map_name: str, oob_filename: str, placed_units, objectives=None, intro_text: str = "", start_time: str = "", victory_conditions: dict = None, oob_names_path: str = None, scenario_name: str = "", inner_scenario_name: str = "", auto_fill_supply: bool = True) -> None:
        export_scenario(self, scenario_dir, map_name, oob_filename,
                        placed_units, objectives, intro_text, start_time,
                        victory_conditions, oob_names_path, scenario_name,
                        inner_scenario_name, auto_fill_supply=auto_fill_supply)

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

    def reset_row_from_original(self, line_number: int) -> bool:
        """Reset a row's field values to the original loaded state, matched by line_number.

        Restores all columns except hierarchy columns (SIDE 1, ARMY 2, CORPS 3,
        DIV 4, BGDE 5, BTN 6) which would require reparenting.
        Returns True if the row was found and reset, False otherwise.
        """
        if self._original_df is None or self.df is None:
            return False
        orig_match = self._original_df[self._original_df["line_number"] == line_number]
        if orig_match.empty:
            return False
        current_match = self.df[self.df["line_number"] == line_number]
        if current_match.empty:
            return False
        orig_idx = orig_match.index[0]
        curr_idx = current_match.index[0]
        cols_to_reset = [c for c in self.df.columns if c not in HIERARCHY_COLS]
        for col in cols_to_reset:
            self.df.at[curr_idx, col] = self._original_df.at[orig_idx, col]
        self._invalidate_caches()
        return True

    def _ensure_df(self) -> pd.DataFrame:
        if self.df is None:
            raise ValueError("No data loaded")
        return self.df

    # ── Hierarchy utilities ────────────────────────────────────────

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

    def get_hierarchy_level_name_and_index(self, hierarchy_key: Tuple[int, ...],
                                             class_value: str = "") -> str:
        for i in range(len(hierarchy_key) - 1, -1, -1):
            if hierarchy_key[i] != 0:
                name = LEVEL_NAMES[i]
                if i == 5:  # Level 6: override based on unit class
                    cv = class_value.upper()
                    if "_CAV_" in cv:
                        name = "Squadron"
                    elif "_ART_" in cv:
                        name = "Gun"
                return f"{name} ({hierarchy_key[i]})"
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
        csv_formation = str(row.get("Formation") if pd.notna(row.get("Formation")) else "")
        resolved_formation = self._resolve_formation(row_index, csv_formation)
        class_raw = row.get("CLASS")
        class_value = str(class_raw) if pd.notna(class_raw) else ""
        return UnitInfo(
            row_index=row_index,
            name=str(row.get("NAME1", f"Unit {row_index}")),
            side=int(row.get("SIDE 1") if pd.notna(row.get("SIDE 1")) else 1),
            level=self.get_level(row_index),
            formation=resolved_formation,
            head_count=int(row.get("Head Count") if pd.notna(row.get("Head Count")) else 0),
            class_value=class_value,
        )

    def _resolve_formation(self, row_index: int, csv_formation: str) -> str:
        """Return the subtype-resolved formation for *row_index* if cached, else *csv_formation*."""
        for (ri, archetype_id, _), af in self._formation_cache.items():
            if ri == row_index and af is not None:
                return archetype_id
        return csv_formation

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
            art_scale = 15 if "Art" in archetype_id else SPRITE_SCALE
            result = ActualFormation(
                archetype_id=archetype_id,
                strength=int(head_count / art_scale),
            )
            self._formation_cache[cache_key] = result
            return result
        direct_children = self.get_direct_children(row_index, exclude_supply=True)
        archetype = FormationArchetype.formations.get(archetype_id) if archetype_id else None
        default_child_form = archetype.sub_form if archetype and archetype.sub_form else None

        # Collect all available slots from the archetype layout (seq >= 3)
        all_slots = []
        if archetype:
            for seq_str, (grid_row, grid_col, pos_info) in archetype.full_strength_layout.items():
                seq_num = int(seq_str)
                if seq_num < 3:
                    continue
                subtype = pos_info.get('subtype')
                per_cell_form = pos_info.get('subformation')
                all_slots.append((seq_str, subtype, per_cell_form))

        # Sort slots by seq number (natural formation order: front rows first)
        all_slots.sort(key=lambda s: int(s[0]))

        # Assign children to slots based on subtype matching
        slot_to_child: Dict[str, int] = {}  # seq_str -> child_idx
        used_children: Set[int] = set()
        used_slot_seqs: Set[str] = set()

        # First pass: fill slots in order (None = wildcard, typed = subtype match)
        for seq_str, subtype, per_cell_form in all_slots:
            if subtype is None:
                for child_idx, child_row_idx in enumerate(direct_children):
                    if child_idx in used_children:
                        continue
                    slot_to_child[seq_str] = child_idx
                    used_children.add(child_idx)
                    used_slot_seqs.add(seq_str)
                    break
                continue
            for child_idx, child_row_idx in enumerate(direct_children):
                if child_idx in used_children:
                    continue
                child_row = self.get_row(child_row_idx)
                child_type = detect_unit_type(str(child_row.get("CLASS", "")))
                if child_type == subtype:
                    slot_to_child[seq_str] = child_idx
                    used_children.add(child_idx)
                    used_slot_seqs.add(seq_str)
                    break

        # Second pass: fill remaining unmatched slots in order
        for seq_str, subtype, per_cell_form in all_slots:
            if seq_str in used_slot_seqs:
                continue
            for child_idx, child_row_idx in enumerate(direct_children):
                if child_idx in used_children:
                    continue
                slot_to_child[seq_str] = child_idx
                used_children.add(child_idx)
                used_slot_seqs.add(seq_str)
                break

        # Build sub_formations list and child_row_indices
        max_seq = max((int(s) for s in used_slot_seqs), default=0)
        sub_formations: List[Optional[ActualFormation]] = [None, None]
        child_row_indices: List[Optional[int]] = [None, None]
        for seq_num in range(3, max_seq + 1):
            seq_str = str(seq_num)
            if seq_str in slot_to_child:
                child_idx = slot_to_child[seq_str]
                child_row_idx = direct_children[child_idx]
                layout_info = archetype.full_strength_layout.get(seq_str) if archetype else None
                per_cell_form = layout_info[2].get('subformation') if layout_info else None
                if level < 3 and allow_top_level_formation_fallback:
                    child_form = archetype_id
                elif per_cell_form and per_cell_form != default_child_form:
                    child_form = per_cell_form
                else:
                    child_form = default_child_form
                sub_formations.append(self.build_strength(child_row_idx, archetype_id=child_form))
                child_row_indices.append(child_row_idx)
            else:
                sub_formations.append(None)
                child_row_indices.append(None)
        result = ActualFormation(archetype_id=archetype_id, strength=sub_formations,
                                 child_row_indices=child_row_indices)
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
        source_rows = set(self.get_subordinate_row_indices(source))
        target_rows = set(self.get_subordinate_row_indices(target))

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
            new_row["line_number"] = -1

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
                new_row["ID"] = self._next_unique_id(template_id)

            new_df = pd.DataFrame([new_row])
            for col in INT_COLUMNS:
                if col in new_df.columns:
                    new_df[col] = pd.to_numeric(new_df[col], errors="coerce").astype("Int64")

            if parent_drop:
                # Collect target's subtree BEFORE insertion (indices will shift)
                subtree_rows = set(self.get_subordinate_row_indices(target_row_index))
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
            subtree_rows = set(self.get_subordinate_row_indices(row_index))
            for r in subtree_rows:
                old_key = self.get_hierarchy_key_by_index(r)
                new_key = new_prefix + [new_l_value] + list(old_key[source_level:])
                for i, hcol in enumerate(HIERARCHY_COLS):
                    self.df.at[r, hcol] = new_key[i]
            self._invalidate_caches()
            self._build_adjacency_index()
            return True

    def add_root_unit(self, template: Dict[str, Any]) -> int:
        """Insert a new root-level (Side) unit from template data.

        Used when the tree is empty or when the user right-clicks empty space
        to create a new Side commander.  Returns the new row index.
        """
        self._ensure_built()
        new_row_data = template["row"]

        # Determine the next Side-level value
        new_side_value = 1
        if self.df is not None and len(self.df) > 0:
            for i in range(len(self.df)):
                lvl = self.get_level(i)
                if lvl == 1:
                    val = self.df.at[i, HIERARCHY_COLS[0]]
                    if pd.notna(val) and val != 0:
                        new_side_value = max(new_side_value, int(val) + 1)

        # Determine columns to use: existing df columns or template keys
        cols = (self.df.columns if self.df is not None and len(self.df) > 0
                else list(new_row_data.keys()))

        # Build the row dict from template data
        new_row = {col: new_row_data.get(col, "") for col in cols}

        # Set hierarchy columns: [new_side_value, 0, 0, 0, 0, 0]
        for i, hcol in enumerate(HIERARCHY_COLS):
            if hcol in new_row:
                new_row[hcol] = new_side_value if i == 0 else 0

        new_row["line_number"] = -1

        # Resolve template modifiers (seq, pool, range, pick)
        self._resolve_modifiers(new_row, 0)

        # Assign a unique ID
        template_id = str(new_row.get("ID", "")).strip()
        if template_id:
            new_row["ID"] = self._next_unique_id(template_id)

        # Create the new row as a single-row DataFrame
        new_df = pd.DataFrame([new_row])
        for col in INT_COLUMNS:
            if col in new_df.columns:
                new_df[col] = pd.to_numeric(new_df[col], errors="coerce").astype("Int64")

        # Append to existing DataFrame or create fresh
        if self.df is not None and len(self.df) > 0:
            self.df = pd.concat([self.df, new_df], ignore_index=True)
        else:
            self.df = new_df

        new_row_idx = len(self.df) - 1

        self._invalidate_caches()
        self._build_adjacency_index()
        return new_row_idx

    def _next_unique_id(self, template_id: str) -> str:
        return self.templates.next_unique_id(template_id)

    def is_descendant_of(self, potential_descendant: int, ancestor: int) -> bool:
        """Check if potential_descendant is in the subtree of ancestor."""
        if potential_descendant == ancestor:
            return False
        return potential_descendant in self.get_subordinate_row_indices(ancestor)

    def load_templates(self, templates_dir: str) -> List[Dict[str, Any]]:
        return self.templates.load_templates(templates_dir)

    def save_as_template(self, row_index: int, templates_dir: str) -> str:
        return self.templates.save_as_template(row_index, templates_dir)

    def load_pools(self, pools_dir: str) -> None:
        self.templates.load_pools(pools_dir)

    def _resolve_modifiers(self, row_dict: dict, parent_row_index: int) -> None:
        self.templates.resolve_modifiers(row_dict, parent_row_index)

    def regenerate_hierarchy_indices(self) -> None:
        """Reassign hierarchy indices sequentially under each parent.

        Walks the tree top-down and renumbers children 1, 2, 3, ...
        under each parent.  Subtrees move with their parent.
        Root (Side-level) nodes are also renumbered sequentially to fill
        any gaps left by deleted sides.
        """
        self._ensure_built()
        if self.df is None or len(self.df) == 0:
            return

        # Start from root nodes (those not in _children_set)
        roots = [i for i in range(len(self.df))
                 if i not in self._children_set and self.get_level(i) is not None]
        # Sort by current hierarchy key for stable ordering
        roots.sort(key=lambda idx: tuple(self._hierarchy_keys[idx].tolist()))

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

        for side_num, root_idx in enumerate(roots, start=1):
            # Renumber the root (Side-level) node itself
            root_level = int(self._level_by_row[root_idx])
            root_level_col_idx = root_level - 1
            new_root_key = list(new_keys[root_idx])
            new_root_key[root_level_col_idx] = side_num
            for j in range(root_level_col_idx + 1, 6):
                new_root_key[j] = 0
            new_keys[root_idx] = np.array(new_root_key, dtype=np.int64)
            renumber_children(root_idx, tuple(new_root_key))

        # Write new keys back to the DataFrame
        for i, hcol in enumerate(HIERARCHY_COLS):
            self.df[hcol] = new_keys[:, i]

        self._invalidate_caches()
        self._build_adjacency_index()


# ── Hierarchy display utilities ──────────────────────────────────

def _display_name(row) -> str:
    """Format a unit's name as 'NAME2, NAME1' or just 'NAME1' if NAME2 is empty."""
    raw_name2 = row.get("NAME2", "")
    raw_name1 = row.get("NAME1", "")
    name2 = "" if pd.isna(raw_name2) else str(raw_name2).strip()
    name1 = "" if pd.isna(raw_name1) else str(raw_name1).strip()
    if name2:
        return f"{name2}, {name1}"
    return name1


def subtree_totals(node):
    """Compute subtree totals for a hierarchy node.

    Returns (regiments, batteries, squadrons, total_men, total_guns).
    """
    reg, bat, sqd, men, guns = 0, 0, 0, 0, 0
    lvl = node["level"]
    if lvl == 6:
        men = node["head_count"]
        ut = detect_unit_type(node["class_val"])
        if ut == "2":
            sqd = 1
        elif ut == "3":
            bat = 1
            guns = 1
        else:
            reg = 1
    else:
        for child in node["children"]:
            c_reg, c_bat, c_sqd, c_men, c_guns = subtree_totals(child)
            reg += c_reg
            bat += c_bat
            sqd += c_sqd
            men += c_men
            guns += c_guns
        # Level 5 nodes are direct units, not just containers
        if lvl == 5:
            men += node["head_count"]
            ut = detect_unit_type(node["class_val"])
            if ut == "2":
                sqd += 1
            elif ut == "3":
                bat += 1
                guns += 1
            else:
                reg += 1
    return reg, bat, sqd, men, guns


def build_forces_hierarchy(oob_data, placed_row_indices=None):
    """Build the side→army→corps→division→brigade→regiment hierarchy.

    If *placed_row_indices* is provided and non-empty, only those rows
    (plus their unplaced ancestor rows) are included so the tree always
    has proper side/army/corps structure.  When no units are placed the
    result is an empty dict.

    Returns:
        ``(sides, subtree_totals_fn)`` where *sides* maps side number to
        a list of army-level node dicts and *subtree_totals_fn* is the
        ``subtree_totals`` callable.
    """
    df = oob_data.df
    if df is None or len(df) == 0:
        return {}, subtree_totals

    if not placed_row_indices:
        return {}, subtree_totals

    rows_to_include = set(placed_row_indices)

    # Walk up ancestors so the hierarchy tree is always complete
    for row_idx in list(placed_row_indices):
        key = oob_data.get_hierarchy_key_by_index(row_idx)
        parent_key = oob_data.get_parent_key(key)
        while not all(v == 0 for v in parent_key):
            parent_idx = oob_data.get_row_index_by_key(parent_key)
            if parent_idx is None or parent_idx in rows_to_include:
                break
            rows_to_include.add(parent_idx)
            parent_key = oob_data.get_parent_key(parent_key)

    # Collect valid rows and sort by hierarchy key
    valid = [(i, oob_data.get_level(i)) for i in rows_to_include]
    valid = [(i, lv) for i, lv in valid if lv is not None]
    valid.sort(key=lambda x: tuple(oob_data._hierarchy_keys[x[0]].tolist()))

    # Build hierarchy: side → army → corps → division → brigade → regiment
    sides = {}
    current = {lv: None for lv in range(1, 7)}

    for idx, level in valid:
        row = df.iloc[idx]
        side_num = int(row.get("SIDE 1", 0) or 0)
        if side_num == 0:
            continue

        raw_class = row.get("CLASS", "")
        class_val = "" if pd.isna(raw_class) else str(raw_class)
        node = {
            "name": _display_name(row),
            "children": [],
            "head_count": int(row.get("Head Count", 0) or 0),
            "class_val": class_val,
            "level": level,
        }

        if level == 1:
            if side_num not in sides:
                sides[side_num] = []
            current[1] = node
            for lv in range(2, 7):
                current[lv] = None
        elif level == 2:
            sides.setdefault(side_num, []).append(node)
            current[2] = node
            for lv in range(3, 7):
                current[lv] = None
        elif level == 3:
            if current[2] is not None:
                current[2]["children"].append(node)
            current[3] = node
            for lv in range(4, 7):
                current[lv] = None
        elif level == 4:
            if current[3] is not None:
                current[3]["children"].append(node)
            elif current[2] is not None:
                current[2]["children"].append(node)
            current[4] = node
            for lv in range(5, 7):
                current[lv] = None
        elif level == 5:
            if current[4] is not None:
                current[4]["children"].append(node)
            elif current[3] is not None:
                current[3]["children"].append(node)
            elif current[2] is not None:
                current[2]["children"].append(node)
            current[5] = node
            current[6] = None
        elif level == 6:
            if current[5] is not None:
                current[5]["children"].append(node)
            elif current[4] is not None:
                current[4]["children"].append(node)
            elif current[3] is not None:
                current[3]["children"].append(node)
            elif current[2] is not None:
                current[2]["children"].append(node)

    return sides, subtree_totals


