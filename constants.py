from typing import List, Dict
from PySide6.QtGui import QBrush, QColor


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

# ── Shared toolbar filter button colors ────────────────────────────
FILTER_ACTIVE_COLOR = QColor("#b388ff")         # light purple (non-default filter)

# ── Game design constants ─────────────────────────────────────────
SPRITE_SCALE: int = 6  # Head Count / SPRITE_SCALE = number of subunit sprites in a level-6 unit

# ── Commander map shape constants ────────────────────────────────
CMD_CONCENTRIC_GAP: int = 120      # gap between concentric shape outlines (world units)
CMD_FACING_ARROW_LEN: int = 300    # length of the facing indicator arrow (world units)
CMD_FACING_ARROW_HEAD: int = 120   # width of the arrowhead base (world units)

# ── Level-6 unit accent constants ────────────────────────────────
WAGON_HATCH_SPACING: int = 200     # spacing between horizontal hatch lines (world units)
WAGON_HATCH_WIDTH: int = 30        # width of hatch lines
ART_CANNON_BARREL_LEN: int = 500   # barrel length (world units), half of CMD_SIZE
# Layout-view cannon proportions at BASE_SIZE=200: barrel=15x60, wheels=10x25, connectors=5x16
# Total aspect: 45 wide x 60 tall (3:4)
ART_CANNON_TOTAL_W: int = 375      # total cannon width derived from barrel length (500 * 45/60)
ART_CANNON_TOTAL_H: int = 500      # total cannon height = barrel length


def get_border_color(is_selected: bool, is_hovered: bool, is_highlighted: bool) -> QColor:
    """Return the border color based on selection/hover/highlight state."""
    if is_selected:
        return COLOR_BORDER_SELECTED
    elif is_hovered:
        return COLOR_BORDER_HOVER
    elif is_highlighted:
        return COLOR_BORDER_HIGHLIGHTED
    return COLOR_BORDER_NORMAL


def get_side_color(side: int, is_selected: bool = False, is_hovered: bool = False,
                   is_highlighted: bool = False) -> QColor:
    """Return the side (fill) color, brightened by interaction state."""
    base = COLOR_SIDE_1 if side == 1 else COLOR_SIDE_2
    if is_selected:
        return base.lighter(170 if is_highlighted else 150)
    if is_hovered:
        return base.lighter(120)
    if is_highlighted:
        return base.lighter(130)
    return base


def apply_side_colors_to_item(item, side: int) -> None:
    """Set background/foreground colors on all columns of a QTreeWidgetItem."""
    if side == 1:
        bg = QColor(TREE_SIDE_1_BG)
    elif side == 2:
        bg = QColor(TREE_SIDE_2_BG)
    else:
        return
    fg = QColor("#ffffff")
    for col in range(item.columnCount()):
        item.setBackground(col, QBrush(bg))
        item.setForeground(col, QBrush(fg))
