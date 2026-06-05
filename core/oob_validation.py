import numpy as np
import pandas as pd
from typing import List
from core.oob_model import OOBData


MANEUVER_STATS = ("Fatigue", "Morale", "Close", "Open", "Edged", "Firearm",
                  "Marksmanship", "Horsemanship", "Surgeon", "Calisthenics")
COMMAND_STATS = ("Ability", "Command", "Control", "Leadership", "Style")


class OOBValidator:
    """Validates Order of Battle data for consistency and correctness."""

    def __init__(self, data: OOBData):
        self.data = data
        # Resolve the actual columns that exist in the dataframe once.
        self._maneuver_cols: List[str] = []
        self._command_cols: List[str] = []
        self._refresh_columns()

    def _refresh_columns(self) -> None:
        if self.data.df is None:
            return
        df_cols = set(self.data.df.columns)
        self._maneuver_cols = [c for c in MANEUVER_STATS if c in df_cols]
        self._command_cols = [c for c in COMMAND_STATS if c in df_cols]

    def check_unit_stats_conflict(self) -> List[str]:
        if self.data.df is None or not (self._maneuver_cols or self._command_cols):
            return []
        if not (self._maneuver_cols and self._command_cols):
            return []
        df = self.data.df
        man = df[self._maneuver_cols]
        cmd = df[self._command_cols]
        man_notna = man.notna()
        cmd_notna = cmd.notna()
        has_some_man = man_notna.any(axis=1)
        has_some_cmd = cmd_notna.any(axis=1)
        has_all_man = man_notna.all(axis=1)
        has_all_cmd = cmd_notna.all(axis=1)
        is_supply = df.get("Formation", pd.Series(dtype=object)).fillna("") == "DRIL_SupplyWagon"
        bad = (has_some_man & has_some_cmd) | ~(has_all_man | has_all_cmd | is_supply)
        if not bad.any():
            return []
        bad_idx = df.index[bad]
        names = df.loc[bad_idx, "NAME1"].fillna("Unknown").astype(str)
        line_nums = df.loc[bad_idx, "line_number"].astype(int)
        return [
            f"Line {int(ln)}: '{nm}' has both maneuver and command stats.\n"
            f"Units should have either maneuver stats (Fatigue, Morale, Close, Open, Edged, Firearm, "
            f"Marksmanship, Horsemanship, Surgeon, Calisthenics) or command stats (Ability, Command, "
            f"Control, Leadership, Style), but not both."
            for ln, nm in zip(line_nums.tolist(), names.tolist())
        ]

    def check_hierarchy_conflicts(self) -> List[str]:
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
            f"Line {int(ln)}: '{nm}' is level {int(lvl)} but Formation doesn't contain "
            f"'Lvl{int(el)}'. Formation listed: {str(fm)}"
            for ln, nm, lvl, el, fm in zip(
                line_nums[bad].tolist(),
                names[bad].tolist(),
                level_arr[bad].tolist(),
                expected_level[bad].tolist(),
                formation[bad].tolist(),
            )
        ]

    def validate_unit_stats(self) -> List[str]:
        self._refresh_columns()
        warnings: List[str] = []
        warnings.extend(self.check_unit_stats_conflict())
        warnings.extend(self.check_hierarchy_conflicts())
        return warnings
