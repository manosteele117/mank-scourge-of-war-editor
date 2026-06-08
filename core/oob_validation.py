import numpy as np
import pandas as pd
from typing import List, NamedTuple
from core.oob_model import OOBData


MANEUVER_STATS = ("Fatigue", "Morale", "Close", "Open", "Edged", "Firearm",
                  "Marksmanship", "Horsemanship", "Surgeon", "Calisthenics")
COMMAND_STATS = ("Ability", "Command", "Control", "Leadership", "Style")


class ValidationIssue(NamedTuple):
    check_name: str
    line_number: int
    unit_name: str
    message: str


class OOBValidator:
    """Validates Order of Battle data for consistency and correctness."""

    def __init__(self, data: OOBData):
        self.data = data
        self._maneuver_cols: List[str] = []
        self._command_cols: List[str] = []
        self._refresh_columns()

    def _refresh_columns(self) -> None:
        if self.data.df is None:
            return
        df_cols = set(self.data.df.columns)
        self._maneuver_cols = [c for c in MANEUVER_STATS if c in df_cols]
        self._command_cols = [c for c in COMMAND_STATS if c in df_cols]

    @staticmethod
    def _format_stats_row(cols, row) -> str:
        parts = []
        for c in cols:
            val = row.get(c)
            if pd.notna(val):
                parts.append(f"{c}={val}")
        return ", ".join(parts) if parts else "(none)"

    def check_unit_stats_conflict(self) -> List[ValidationIssue]:
        if self.data.df is None:
            return []
        if not (self._maneuver_cols and self._command_cols):
            return []
        df = self.data.df
        self.data._ensure_built()
        level_arr = self.data._level_by_row
        if level_arr is None or len(level_arr) == 0:
            return []
        names = df["NAME1"].fillna("Unknown").astype(str).to_numpy()
        line_nums = df["line_number"].to_numpy()
        supply_mask = (df.get("Formation", pd.Series(dtype=object)).fillna("") == "DRIL_SupplyWagon")
        all_stat_cols = list(self._maneuver_cols) + list(self._command_cols)

        issues: List[ValidationIssue] = []
        for i in range(len(df)):
            if supply_mask.iloc[i]:
                continue
            lvl = int(level_arr[i])
            if lvl <= 0:
                continue
            nm = str(names[i])
            ln = int(line_nums[i])
            row = df.iloc[i]

            man_present = [(c, str(row[c])) for c in self._maneuver_cols if pd.notna(row.get(c))]
            cmd_present = [(c, str(row[c])) for c in self._command_cols if pd.notna(row.get(c))]
            stats_ref = self._format_stats_row(all_stat_cols, row)

            if lvl == 6:
                if cmd_present:
                    bad_stats = ", ".join(f"{c}={v}" for c, v in cmd_present)
                    man_stats = ", ".join(f"{c}={v}" for c, v in man_present)
                    msg = (
                        f"Level 6 unit has command stats defined (should not).\n"
                        f"  Command stats present: {bad_stats}\n"
                        f"  Maneuver stats present: {man_stats}"
                    )
                    issues.append(ValidationIssue("Stats Conflict", ln, nm, msg))
                man_cols = [c for c, _ in man_present]
                missing_man = [c for c in self._maneuver_cols if c not in man_cols]
                if missing_man:
                    msg = (
                        f"Level 6 unit has maneuver stats but not all defined.\n"
                        f"  Present: {stats_ref}\n"
                        f"  Missing: {', '.join(missing_man)}"
                    )
                    issues.append(ValidationIssue("Stats Conflict", ln, nm, msg))
            else:
                if man_present:
                    bad_stats = ", ".join(f"{c}={v}" for c, v in man_present)
                    cmd_stats = ", ".join(f"{c}={v}" for c, v in cmd_present)
                    msg = (
                        f"Level {lvl} unit has maneuver stats defined (should not).\n"
                        f"  Maneuver stats present: {bad_stats}\n"
                        f"  Command stats present: {cmd_stats}"
                    )
                    issues.append(ValidationIssue("Stats Conflict", ln, nm, msg))
                cmd_cols = [c for c, _ in cmd_present]
                missing_cmd = [c for c in self._command_cols if c not in cmd_cols]
                if missing_cmd:
                    msg = (
                        f"Level {lvl} unit has command stats but not all defined.\n"
                        f"  Present: {stats_ref}\n"
                        f"  Missing: {', '.join(missing_cmd)}"
                    )
                    issues.append(ValidationIssue("Stats Conflict", ln, nm, msg))

        return issues

    def check_hierarchy_conflicts(self) -> List[ValidationIssue]:
        if self.data.df is None:
            return []
        df = self.data.df
        self.data._ensure_built()
        level_arr = self.data._level_by_row
        if level_arr is None or len(level_arr) == 0:
            return []
        expected_level = np.maximum(level_arr, 3)
        expected_str = np.char.mod("Lvl%d", expected_level)
        formation = df["Formation"].fillna("").to_numpy(dtype=object)
        names = df["NAME1"].fillna("Unknown").astype(str).to_numpy()
        line_nums = df["line_number"].to_numpy()
        bad = (level_arr > 0) & ~np.array([s in str(f) for s, f in zip(expected_str, formation)])
        if not bad.any():
            return []
        supply_mask = (formation == "DRIL_SupplyWagon")
        bad = bad & ~supply_mask
        if not bad.any():
            return []
        return [
            ValidationIssue(
                check_name="Hierarchy Mismatch",
                line_number=int(ln),
                unit_name=str(nm),
                message=(
                    f"Unit is level {int(lvl)} but Formation column contains "
                    f"'{str(fm)}' instead of expected 'Lvl{int(el)}'."
                ),
            )
            for ln, nm, lvl, el, fm in zip(
                line_nums[bad].tolist(),
                names[bad].tolist(),
                level_arr[bad].tolist(),
                expected_level[bad].tolist(),
                formation[bad].tolist(),
            )
        ]

    def check_duplicate_ids(self) -> List[ValidationIssue]:
        if self.data.df is None or "ID" not in self.data.df.columns:
            return []
        df = self.data.df
        ids = df["ID"].fillna("").astype(str)
        dup_mask = ids.duplicated(keep=False) & (ids != "")
        if not dup_mask.any():
            return []
        issues: List[ValidationIssue] = []
        for i in df.index[dup_mask]:
            issues.append(ValidationIssue(
                check_name="Duplicate ID",
                line_number=int(df.at[i, "line_number"]),
                unit_name=str(df.at[i, "NAME1"]),
                message=f"ID '{ids.at[i]}' is not unique.",
            ))
        return issues

    def validate(self) -> List[ValidationIssue]:
        self._refresh_columns()
        issues: List[ValidationIssue] = []
        issues.extend(self.check_unit_stats_conflict())
        issues.extend(self.check_hierarchy_conflicts())
        issues.extend(self.check_duplicate_ids())
        issues.sort(key=lambda i: i.line_number)
        return issues
