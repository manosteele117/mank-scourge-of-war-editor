import pandas as pd
from typing import List
from core.oob_model import OOBData


class OOBValidator:
    """Validates Order of Battle data for consistency and correctness."""

    def __init__(self, data: OOBData):
        self.data = data

    def check_unit_stats_conflict(self) -> List[str]:
        if self.data.df is None:
            return []

        maneuver_stats = ["Fatigue", "Morale", "Close", "Open", "Edged", "Firearm",
                          "Marksmanship", "Horsemanship", "Surgeon", "Calisthenics"]
        command_stats = ["Ability", "Command", "Control", "Leadership", "Style"]

        maneuver_cols = [col for col in maneuver_stats if col in self.data.df.columns]
        command_cols = [col for col in command_stats if col in self.data.df.columns]

        errors = []
        for idx, row in self.data.df.iterrows():
            has_some_maneuver = any(pd.notna(row.get(col)) for col in maneuver_cols)
            has_some_command = any(pd.notna(row.get(col)) for col in command_cols)
            has_all_maneuver = all(pd.notna(row.get(col)) for col in maneuver_cols)
            has_all_command = all(pd.notna(row.get(col)) for col in command_cols)

            if (has_some_maneuver and has_some_command) or not (has_all_maneuver or has_all_command or
                                                                  (str(row.get("Formation", "")) == "DRIL_SupplyWagon")):
                unit_name = str(row.get("NAME1", "Unknown"))
                line_num = int(row.get("line_number", idx + 2))
                errors.append(
                    f"Line {line_num}: '{unit_name}' has both maneuver and command stats.\n"
                    f"Maneuver stats present: {has_some_maneuver}, Command stats present: {has_some_command}.\n"
                    f"Maneuver stats complete: {has_all_maneuver}, Command stats complete: {has_all_command}.\n"
                    f"Units should have either maneuver stats (Fatigue, Morale, Close, Open, Edged, Firearm, "
                    f"Marksmanship, Horsemanship, Surgeon, Calisthenics) or command stats (Ability, Command, "
                    f"Control, Leadership, Style), but not both."
                )
        return errors

    def check_hierarchy_conflicts(self) -> List[str]:
        if self.data.df is None:
            return []

        errors = []
        for idx, row in self.data.df.iterrows():
            level = self.data.get_level_from_hierarchy(row)
            expected_level = max(3, level) if level else None
            if level is None:
                continue

            formation = str(row.get("Formation", ""))
            unit_name = str(row.get("NAME1", "Unknown"))
            line_num = int(row.get("line_number", idx + 2))

            if formation == "DRIL_SupplyWagon":
                continue

            expected_formation_str = f"Lvl{expected_level}"
            if expected_formation_str not in formation:
                errors.append(
                    f"Line {line_num}: '{unit_name}' is level {level} but Formation doesn't contain "
                    f"'{expected_formation_str}'. Formation listed: {formation}"
                )
        return errors

    def validate_unit_stats(self) -> List[str]:
        warnings = []
        warnings.extend(self.check_unit_stats_conflict())
        warnings.extend(self.check_hierarchy_conflicts())
        return warnings
