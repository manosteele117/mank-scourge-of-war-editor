from typing import List, Dict
from PySide6.QtGui import QColor


# ── Hierarchy definitions ──────────────────────────────────────────
HIERARCHY_COLS: List[str] = ["SIDE 1", "ARMY 2", "CORPS 3", "DIV 4", "BGDE 5", "BTN 6"]
LEVEL_NAMES: List[str] = ["Side", "Army", "Corps", "Division", "Brigade", "Regiment"]

# ── Column metadata ────────────────────────────────────────────────
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

INT_COLUMNS: List[str] = [
    "Head Count", "Experience", "Fatigue", "Morale",
    "Close", "Open", "Edged", "Firearm",
    "Marksmanship", "Horsemanship", "Surgeon", "Calisthenics",
    "Ability", "Command", "Control", "Leadership", "Style",
]

REQUIRED_COLUMNS: List[str] = [
    "NAME1", "Head Count", "SIDE 1", "ARMY 2",
    "CORPS 3", "DIV 4", "BGDE 5", "BTN 6",
]

# ── Side colors (visual/map views) ────────────────────────────────
COLOR_SIDE_1 = QColor("#2c5aa0")
COLOR_SIDE_2 = QColor("#a02c2c")

# ── Border / highlight colors (shared by shapes and map items) ─────
COLOR_BORDER_NORMAL = QColor("#aaaaaa")
COLOR_BORDER_SELECTED = QColor("#ffff00")
COLOR_BORDER_HOVER = QColor("#64b5f6")
COLOR_BORDER_HIGHLIGHTED = QColor("#ffffff")

# ── Tree-view side row colors (muted variants) ────────────────────
TREE_SIDE_1_BG = "#2c2c40"
TREE_SIDE_2_BG = "#402c2c"


def get_border_color(is_selected: bool, is_hovered: bool, is_highlighted: bool) -> QColor:
    """Return the border color based on selection/hover/highlight state."""
    if is_selected:
        return COLOR_BORDER_SELECTED
    elif is_hovered:
        return COLOR_BORDER_HOVER
    elif is_highlighted:
        return COLOR_BORDER_HIGHLIGHTED
    return COLOR_BORDER_NORMAL
