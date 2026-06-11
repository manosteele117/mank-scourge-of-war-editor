from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QToolBar,
    QComboBox, QColorDialog, QSizePolicy, QToolButton,
)
from PySide6.QtGui import QAction, QFont, QTextCharFormat, QColor
from PySide6.QtCore import Qt

from core.text_converter import game_text_to_html, html_to_game_text


class RichTextEditor(QWidget):
    """A QTextEdit with a formatting toolbar for rich text editing.

    Provides bold, italic, underline, text color, highlight, and font size.
    Content can be loaded/saved in the game's custom HTML-like format.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # ── Formatting toolbar ──
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar { spacing: 4px; padding: 2px; }
            QToolButton {
                background-color: #1f1f1f;
                color: #ffffff;
                border: 1px solid #333333;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QToolButton:hover { background-color: #2d2d2d; }
            QToolButton:pressed { background-color: #383838; }
            QToolButton:checked {
                background-color: #2979ff;
                border-color: #2979ff;
                color: #ffffff;
            }
            QToolButton:disabled {
                color: #555555;
                background-color: #1a1a1a;
                border-color: #2a2a2a;
            }
        """)

        # Bold
        self._bold_action = toolbar.addAction("B")
        self._bold_action.setCheckable(True)
        self._bold_action.setToolTip("Stylized Font (not bold)")
        font = self._bold_action.font()
        font.setBold(True)
        self._bold_action.setFont(font)
        self._bold_action.triggered.connect(self._on_bold)

        # Italic
        self._italic_action = toolbar.addAction("I")
        self._italic_action.setCheckable(True)
        self._italic_action.setToolTip("Italic (Ctrl+I)")
        font = self._italic_action.font()
        font.setItalic(True)
        self._italic_action.setFont(font)
        self._italic_action.triggered.connect(self._on_italic)

        # Underline
        self._underline_action = toolbar.addAction("U")
        self._underline_action.setCheckable(True)
        self._underline_action.setToolTip("Underline (Ctrl+U)")
        font = self._underline_action.font()
        font.setUnderline(True)
        self._underline_action.setFont(font)
        self._underline_action.triggered.connect(self._on_underline)

        toolbar.addSeparator()

        # Heading combo
        from PySide6.QtWidgets import QLabel, QHBoxLayout as _HL
        heading_widget = QWidget()
        heading_layout = _HL(heading_widget)
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(2)
        hd_label = QLabel("Heading:")
        hd_label.setStyleSheet("font-size: 10px;")
        heading_layout.addWidget(hd_label)

        self._heading_combo = QComboBox()
        self._heading_combo.addItems(["Normal", "H1", "H2", "H3"])
        self._heading_combo.setCurrentText("Normal")
        self._heading_combo.setMaximumWidth(70)
        self._heading_combo.currentTextChanged.connect(self._on_heading)
        heading_layout.addWidget(self._heading_combo)
        toolbar.addWidget(heading_widget)

        # Alignment combo
        align_widget = QWidget()
        align_layout = _HL(align_widget)
        align_layout.setContentsMargins(0, 0, 0, 0)
        align_layout.setSpacing(2)
        al_label = QLabel("Align:")
        al_label.setStyleSheet("font-size: 10px;")
        align_layout.addWidget(al_label)

        self._align_combo = QComboBox()
        self._align_combo.addItems(["Left", "Center", "Right"])
        self._align_combo.setCurrentText("Left")
        self._align_combo.setMaximumWidth(65)
        self._align_combo.currentTextChanged.connect(self._on_align)
        align_layout.addWidget(self._align_combo)
        toolbar.addWidget(align_widget)

        toolbar.addSeparator()

        # Insert Scenario Details
        self._insert_details_btn = QToolButton()
        self._insert_details_btn.setText("Details")
        self._insert_details_btn.setToolTip("Insert formatted scenario details from current settings and OOB data")
        self._insert_details_btn.clicked.connect(self._on_insert_details)
        toolbar.addWidget(self._insert_details_btn)

        toolbar.addSeparator()

        # Text Color
        self._color_btn = QToolButton()
        self._color_btn.setText("A")
        self._color_btn.setToolTip("Text Color")
        font = self._color_btn.font()
        font.setBold(True)
        self._color_btn.setFont(font)
        self._color_btn.setStyleSheet("QToolButton { color: #ff0000; }")
        self._color_btn.clicked.connect(self._on_text_color)
        toolbar.addWidget(self._color_btn)

        # Image (disabled - not yet implemented)
        self._image_action = toolbar.addAction("Img")
        self._image_action.setEnabled(False)
        self._image_action.setToolTip("This is a feature of the game's scenario intro screen but I haven't figured out accessing the available images yet")

        layout.addWidget(toolbar)

        # ── Text editor ──
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.editor.setPlaceholderText("Enter scenario intro text here...")
        self.editor.currentCharFormatChanged.connect(self._on_format_changed)
        self.editor.cursorPositionChanged.connect(self._on_cursor_changed)
        layout.addWidget(self.editor)

    # ── Public API ────────────────────────────────────────────────

    def get_game_text(self) -> str:
        """Return the editor content converted to game-format text."""
        html = self.editor.toHtml()
        return html_to_game_text(html)

    def set_game_text(self, text: str):
        """Load game-format text into the editor."""
        html = game_text_to_html(text)
        self.editor.setHtml(html)

    def clear_editor(self):
        """Clear all editor content."""
        self.editor.clear()

    # ── Formatting actions ────────────────────────────────────────

    def _on_bold(self, checked):
        self.editor.setFontWeight(QFont.Weight.Bold if checked else QFont.Weight.Normal)

    def _on_italic(self, checked):
        self.editor.setFontItalic(checked)

    def _on_underline(self, checked):
        self.editor.setFontUnderline(checked)

    def _on_text_color(self):
        color = QColorDialog.getColor(self.editor.textColor(), self, "Text Color")
        if color.isValid():
            self.editor.setTextColor(color)

    def _on_heading(self, text):
        cursor = self.editor.textCursor()
        block_fmt = cursor.blockFormat()
        if text == "Normal":
            block_fmt.setHeadingLevel(0)
            cursor.setBlockFormat(block_fmt)
            cursor.mergeCharFormat(self._make_format_for_size(12))
        else:
            level = int(text[1])
            block_fmt.setHeadingLevel(level)
            cursor.setBlockFormat(block_fmt)
            sizes = {1: 24, 2: 18, 3: 14}
            cursor.mergeCharFormat(self._make_format_for_size(sizes.get(level, 12)))
        self.editor.setTextCursor(cursor)

    def _on_align(self, text):
        cursor = self.editor.textCursor()
        block_fmt = cursor.blockFormat()
        align_map = {
            "Left": Qt.AlignmentFlag.AlignLeft,
            "Center": Qt.AlignmentFlag.AlignHCenter,
            "Right": Qt.AlignmentFlag.AlignRight,
        }
        block_fmt.setAlignment(align_map.get(text, Qt.AlignmentFlag.AlignLeft))
        cursor.setBlockFormat(block_fmt)
        self.editor.setTextCursor(cursor)

    def _make_format_for_size(self, size):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        return fmt

    # ── Insert Scenario Details ───────────────────────────────────

    def _find_scenario_tab(self):
        """Walk up the widget tree to find the ScenarioTab parent."""
        from gui.oob_scenario_tab import ScenarioTab
        widget = self
        while widget is not None:
            if isinstance(widget, ScenarioTab):
                return widget
            widget = widget.parentWidget()
        return None

    def _on_insert_details(self):
        """Replace editor content with formatted scenario details."""
        from core.text_converter import game_text_to_html
        game_text = self._generate_scenario_details()
        html = game_text_to_html(game_text)
        self.editor.setHtml(html)

    def _generate_scenario_details(self) -> str:
        """Generate game-format HTML with scenario details from settings and OOB data."""
        tab = self._find_scenario_tab()
        if tab is None:
            return ""

        oob = tab.map_viewer.oob_data
        if oob is None or oob.df is None or len(oob.df) == 0:
            return "<p>No OOB data loaded.</p>"

        from core.formation import detect_unit_type

        # ── Scenario metadata ──
        name = tab.get_scenario_name() or "Untitled Scenario"
        map_name = tab.map_name_edit.text() or "Unknown Map"
        type_val = tab.get_type()
        hour, minute = tab.get_start_time()
        start_time = f"{hour:02d}:{minute:02d}"
        victory = tab.get_victory_conditions()

        df = oob.df
        import pandas as pd

        # ── Collect all valid rows sorted by hierarchy key (same order as tree view) ──
        valid = [(i, oob.get_level(i)) for i in range(len(df))]
        valid = [(i, lv) for i, lv in valid if lv is not None]
        valid.sort(key=lambda x: tuple(oob._hierarchy_keys[x[0]].tolist()))

        # ── Build hierarchy: side → army → corps → division → brigade ──
        # Each entry: {"name": str, "children": [...], "head_count": int, "class_val": str}
        sides = {}  # side_num → list of army dicts
        current = {lv: None for lv in range(1, 7)}  # track current parent at each level

        for idx, level in valid:
            row = df.iloc[idx]
            side_num = int(row.get("SIDE 1", 0) or 0)
            army_num = int(row.get("ARMY 2", 0) or 0)
            corps_num = int(row.get("CORPS 3", 0) or 0)
            div_num = int(row.get("DIV 4", 0) or 0)
            bgde_num = int(row.get("BGDE 5", 0) or 0)
            btn_num = int(row.get("BTN 6", 0) or 0)

            if side_num == 0:
                continue

            raw_class = row.get("CLASS", "")
            class_val = "" if pd.isna(raw_class) else str(raw_class)
            node = {
                "name": self._display_name(row),
                "children": [],
                "head_count": int(row.get("Head Count", 0) or 0),
                "class_val": class_val,
                "level": level,
            }

            if level == 1:
                # Side
                if side_num not in sides:
                    sides[side_num] = []
                current[1] = node
                for lv in range(2, 7):
                    current[lv] = None
            elif level == 2:
                # Army
                sides.setdefault(side_num, []).append(node)
                current[2] = node
                for lv in range(3, 7):
                    current[lv] = None
            elif level == 3:
                # Corps
                if current[2] is not None:
                    current[2]["children"].append(node)
                current[3] = node
                for lv in range(4, 7):
                    current[lv] = None
            elif level == 4:
                # Division
                if current[3] is not None:
                    current[3]["children"].append(node)
                elif current[2] is not None:
                    current[2]["children"].append(node)
                current[4] = node
                for lv in range(5, 7):
                    current[lv] = None
            elif level == 5:
                # Brigade
                if current[4] is not None:
                    current[4]["children"].append(node)
                elif current[3] is not None:
                    current[3]["children"].append(node)
                elif current[2] is not None:
                    current[2]["children"].append(node)
                current[5] = node
                current[6] = None
            elif level == 6:
                # Regiment
                if current[5] is not None:
                    current[5]["children"].append(node)
                elif current[4] is not None:
                    current[4]["children"].append(node)
                elif current[3] is not None:
                    current[3]["children"].append(node)
                elif current[2] is not None:
                    current[2]["children"].append(node)

        # ── Compute subtree totals for army roundups ──
        def subtree_totals(node):
            """Returns (regiments, batteries, squadrons, total_men, total_guns)."""
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
                # Also count this node itself if it's level 5 (direct unit, not just a folder)
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

        # ── Generate output ──
        lines = []

        # Title
        lines.append(f"<p align='center'><h1>{name}</h1></p>")
        lines.append("<p></p>")

        # Scenario info
        lines.append(f"<p><h2><color value='#631B5E'>Map:</color> <color value='#ffffff'>{map_name}</h2></p>")
        lines.append(f"<p><h2><color value='#631B5E'>Type:</color> <color value='#ffffff'>{type_val}</h2></p>")
        lines.append(f"<p><h2><color value='#631B5E'>Start Time:</color> <color value='#ffffff'>{start_time}</h2></p>")
        lines.append("<p></p>")

        # Situation placeholder
        lines.append("<p><h2><color value='#631B5E'>Situation:</color> <color value='#ffffff'>Insert situation text here</color></h2></p>")
        lines.append("<p></p>")

        # Gameplay placeholder
        lines.append("<p><h2><color value='#631B5E'>Gameplay:</color> <color value='#ffffff'>Insert gameplay details here</color></h2></p>")
        lines.append("<p></p>")

        # Forces by side
        for side_num in sorted(sides.keys()):
            side_label = f"Side {side_num} forces available"
            color = "#00298B" if side_num == 1 else "#C60C30"
            lines.append(f"<p align='center'><h3><color value='{color}'>-------{side_label}-------:</color></h3></p>")

            for army_idx, army in enumerate(sides[side_num]):
                lines.append(f"<p align='center'><b><color value='{color}'>{army['name']}</b></p>")

                # Recursively print hierarchy under this army
                self._append_hierarchy(lines, army, depth=1)

                # Army roundup at the bottom
                reg, bat, sqd, men, guns = subtree_totals(army)
                parts = []
                if reg > 0:
                    parts.append(f"{reg} regiment{'s' if reg != 1 else ''}")
                if bat > 0:
                    parts.append(f"{bat} artillery batter{'ies' if bat != 1 else 'y'}")
                if sqd > 0:
                    parts.append(f"{sqd} squadron{'s' if sqd != 1 else ''}")
                parts.append(f"{men:,} men")
                if guns > 0:
                    parts.append(f"{guns} gun{'s' if guns != 1 else ''}")
                lines.append(f"<p><i>{', '.join(parts)}</i></p>")

                # Two line breaks between armies
                if army_idx < len(sides[side_num]) - 1:
                    lines.append("<p></p>")
                    lines.append("<p></p>")

            lines.append("<p></p>")

        # Victory conditions
        lines.append("<p><h2><color value='#631B5E'>Victory Conditions:</color></h2></p>")
        vc_order = ["Major Victory", "Minor Victory", "Draw", "Minor Defeat", "Major Defeat"]
        for label in vc_order:
            value = victory.get(label, "0")
            lines.append(f"<p>{value} = {label}</p>")
        lines.append("<p></p>")

        # Scenario author
        lines.append("<p><h2><color value='#631B5E'>Scenario Author:</color> <color value='#000000'>Mank Scourge of War Editor</color></h2></p>")

        return "\n".join(lines)

    def _append_hierarchy(self, lines, node, depth):
        """Recursively append formatted hierarchy lines for children of a node."""
        for i, child in enumerate(node["children"]):
            level = child["level"]
            if level == 3:
                # Corps — show name and total men
                sub = self._subordinate_men(child)
                lines.append(f"<p>{child['name']} - {sub:,} men</p>")
            elif level == 4:
                # Division — show name and total men
                sub = self._subordinate_men(child)
                lines.append(f"<p>{child['name']} - {sub:,} men</p>")
            elif level == 5:
                # Brigade — name only (no headcount)
                lines.append(f"<p>{child['name']}</p>")
            # Level 6 (regiments) are counted in the roundup, not listed individually
            # Recurse into children
            if child["children"]:
                self._append_hierarchy(lines, child, depth + 1)
            # Line break between corps (level 3 siblings)
            if level == 3 and i < len(node["children"]) - 1:
                lines.append("<p></p>")

    def _display_name(self, row) -> str:
        """Format a unit's name as 'NAME2, NAME1' or just 'NAME1' if NAME2 is empty."""
        import pandas as _pd
        raw_name2 = row.get("NAME2", "")
        raw_name1 = row.get("NAME1", "")
        name2 = "" if _pd.isna(raw_name2) else str(raw_name2).strip()
        name1 = "" if _pd.isna(raw_name1) else str(raw_name1).strip()
        if name2:
            return f"{name2}, {name1}"
        return name1

    def _subordinate_men(self, node):
        """Count total head count of all descendants of a node (not including the node itself)."""
        total = 0
        for child in node["children"]:
            total += child["head_count"]
            total += self._subordinate_men(child)
        return total

    # ── Format state sync ─────────────────────────────────────────

    def _on_format_changed(self, fmt):
        self._bold_action.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        self._italic_action.setChecked(fmt.fontItalic())
        self._underline_action.setChecked(fmt.fontUnderline())

    def _on_cursor_changed(self):
        cursor = self.editor.textCursor()

        block_fmt = cursor.blockFormat()
        level = block_fmt.headingLevel()
        if level == 0:
            self._heading_combo.blockSignals(True)
            self._heading_combo.setCurrentText("Normal")
            self._heading_combo.blockSignals(False)
        else:
            self._heading_combo.blockSignals(True)
            self._heading_combo.setCurrentText("H%d" % level)
            self._heading_combo.blockSignals(False)

        align = block_fmt.alignment()
        if align & Qt.AlignmentFlag.AlignHCenter:
            align_text = "Center"
        elif align & Qt.AlignmentFlag.AlignRight:
            align_text = "Right"
        else:
            align_text = "Left"
        self._align_combo.blockSignals(True)
        self._align_combo.setCurrentText(align_text)
        self._align_combo.blockSignals(False)
