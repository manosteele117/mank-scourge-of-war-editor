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

        # ── Scenario metadata ──
        name = tab.get_scenario_name() or "Untitled Scenario"
        map_name = tab.map_name_edit.text() or "Unknown Map"
        type_val = tab.get_type()
        hour, minute = tab.get_start_time()
        start_time = f"{hour:02d}:{minute:02d}"
        victory = tab.get_victory_conditions()

        from core.oob_model import build_forces_hierarchy

        placed_row_indices = tab.map_viewer.placed_row_indices or None
        sides, subtree_totals = build_forces_hierarchy(oob, placed_row_indices)

        if not sides:
            return ""

        # ── Generate output ──
        lines = []

        # Title
        lines.append(f"<p align='center'><h1>{name}</h1></p>")
        lines.append("<p></p>")

        # Scenario info
        lines.append(f"<p><h2><color value='#631B5E'>Map:</color> <color value='#000000'>{map_name}</h2></p>")
        lines.append(f"<p><h2><color value='#631B5E'>Type:</color> <color value='#000000'>{type_val}</h2></p>")
        lines.append(f"<p><h2><color value='#631B5E'>Start Time:</color> <color value='#000000'>{start_time}</h2></p>")
        lines.append("<p></p>")

        # Situation placeholder
        lines.append("<p><h2><color value='#631B5E'>Situation:</color> <color value='#000000'>Insert situation text here</color></h2></p>")
        lines.append("<p></p>")

        # Gameplay placeholder
        lines.append("<p><h2><color value='#631B5E'>Gameplay:</color> <color value='#000000'>Insert gameplay details here</color></h2></p>")
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
