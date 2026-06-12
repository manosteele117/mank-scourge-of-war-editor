"""Template system for unit generation with modifier resolution.

Extracted from OOBData to keep the data model focused on CSV I/O and hierarchy.
Handles template loading, saving, name pools, and modifier resolution
({seq}, {seqord}, {cycle}, {pool}, {range}, {rangeord}, {pick}).
"""

import os
import re
import random
import traceback
from typing import Dict, List, Any, Tuple

import pandas as pd

from core.constants import HIERARCHY_COLS, INT_COLUMNS


class TemplateSystem:
    """Manages unit templates, name pools, and template modifier resolution."""

    def __init__(self, oob_data):
        """
        Args:
            oob_data: OOBData instance for DataFrame/adjacency access.
        """
        self.data = oob_data
        self._pool_cache: Dict[str, List[str]] = {}
        self._seq_counters: Dict[Tuple[int, str], int] = {}
        self._cycle_counters: Dict[Tuple[int, str], int] = {}

    # ── Template loading ─────────────────────────────────────────────

    def load_templates(self, templates_dir: str) -> List[Dict[str, Any]]:
        """Load all template units from CSV files in *templates_dir*.

        Each CSV uses the standard OOB header. Hierarchy columns contain 'X'
        to mark the template's valid level. Returns a list of dicts with
        keys: name, level, row, file, id.
        """
        if not os.path.isdir(templates_dir):
            return []

        templates: List[Dict[str, Any]] = []
        saved_headers = self.data._original_headers
        for fname in sorted(os.listdir(templates_dir)):
            if not fname.endswith(".csv"):
                continue
            fpath = os.path.join(templates_dir, fname)
            try:
                tdf = pd.read_csv(fpath, encoding="utf-8", dtype=str)
                self.data._original_headers = {}
                tdf = self.data._normalize_columns(tdf)
            except Exception:
                print(f"Error in loading template file {fname}: {traceback.format_exc()}")
                continue

            for _, row in tdf.iterrows():
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
        self.data._original_headers = saved_headers
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

        unit_row = self.data.df.iloc[row_index]
        unit_level = self.data.get_level(row_index)
        if unit_level is None:
            raise ValueError("Cannot determine unit level")

        new_row = {}
        for col in header_cols:
            val = unit_row.get(col, "")
            new_row[col] = "" if pd.isna(val) else str(val)

        for hcol in HIERARCHY_COLS:
            new_row[hcol] = ""
        new_row[HIERARCHY_COLS[unit_level - 1]] = "X"

        user_path = os.path.join(templates_dir, "user_templates.csv")
        level_count = 0
        if os.path.exists(user_path):
            existing = pd.read_csv(user_path, encoding="cp1252", dtype=str)
            existing = self.data._normalize_columns(existing)
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

        new_df = pd.DataFrame([new_row])[header_cols]
        if os.path.exists(user_path):
            existing = pd.read_csv(user_path, encoding="cp1252", dtype=str)
            existing = pd.concat([existing, new_df], ignore_index=True)
            existing.to_csv(user_path, index=False, encoding="cp1252")
        else:
            new_df.to_csv(user_path, index=False, encoding="cp1252")

        return new_id

    # ── Pool loading ─────────────────────────────────────────────────

    def load_pools(self, pools_dir: str) -> None:
        """Load name pools from .txt files in *pools_dir*.

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

    # ── Next unique ID ───────────────────────────────────────────────

    def next_unique_id(self, template_id: str) -> str:
        """Return *template_id* with the smallest unused numeric suffix appended."""
        used_indices = set()
        if "ID" in self.data.df.columns:
            for val in self.data.df["ID"].dropna():
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
        return f"{template_id}{idx}"

    # ── Modifier resolution ─────────────────────────────────────────

    def resolve_modifiers(self, row_dict: dict, parent_row_index: int) -> None:
        """Resolve all {modifier} placeholders in string fields of *row_dict*.

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

        seq_suffixes: Dict[str, str] = {}
        for col in list(row_dict.keys()):
            val = row_dict[col]
            if not isinstance(val, str) or "{seq" not in val:
                continue
            for m in seq_pattern.finditer(val):
                seq_name = m.group(1)
                if seq_name not in seq_suffixes:
                    raw_suffix = val[m.end():]
                    seq_suffixes[seq_name] = self._resolve_suffix_modifiers(raw_suffix)

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

    def _resolve_pool(self, pool_name: str) -> str:
        entries = self._pool_cache.get(pool_name)
        if not entries:
            return f"{{{pool_name}}}"
        return random.choice(entries)

    def _resolve_seq(self, seq_name: str, parent_row_index: int,
                     suffix_pattern: str = "") -> int:
        key = (parent_row_index, seq_name)
        if key not in self._seq_counters:
            max_num = 0
            if suffix_pattern:
                escaped = re.escape(suffix_pattern)
                match_re = re.compile(r'^(\d+)\s*' + escaped + r'$', re.IGNORECASE)
                children = self.data._parent_to_children.get(parent_row_index, [])
                for c in children:
                    name = str(self.data.df.at[c, "NAME1"])
                    m = match_re.match(name)
                    if m:
                        max_num = max(max_num, int(m.group(1)))
            else:
                children = self.data._parent_to_children.get(parent_row_index, [])
                max_num = len(children)
            self._seq_counters[key] = max_num + 1
        else:
            self._seq_counters[key] += 1
        return self._seq_counters[key]

    def _resolve_cycle(self, cycle_str: str, parent_row_index: int) -> str:
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
        if 11 <= (n % 100) <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    def _resolve_rangeord(self, min_val: int, max_val: int) -> str:
        return self._int_to_ordinal(random.randint(min_val, max_val))

    def _resolve_seqord(self, seq_name: str, parent_row_index: int,
                        suffix_pattern: str = "") -> str:
        num = self._resolve_seq(seq_name, parent_row_index, suffix_pattern)
        return self._int_to_ordinal(num)

    def _resolve_suffix_modifiers(self, text: str) -> str:
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
