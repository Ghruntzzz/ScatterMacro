"""AHK-style in-dashboard Unit Manager with per-route auto-saving indexes."""
from math import ceil

from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QRegularExpression
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QDialog, QFrame, QAbstractSpinBox, QLineEdit,
)


EMPTY_INDEX = {
    "unit": "0", "priority": "First", "upgrade": "0",
    "auto_upgrade": "0", "x": "", "y": "", "place_at_wave": "",
    "auto_ability_wave": "",
    "path": "",
}
PAGE_SIZE = 6
TARGETS = ["First", "Last", "Closest", "Strongest", "Boss",
           "Weakest", "Shielded", "Fastest", "Flying"]


def configured_positions(entries, width, height):
    """All saved indexes with a position inside the captured Roblox client."""
    result = []
    for index, entry in enumerate(entries, 1):
        x, y = entry.get("x", ""), entry.get("y", "")
        if str(x).strip() == "" or str(y).strip() == "":
            continue
        try:
            x, y = int(x), int(y)
        except (ValueError, TypeError):
            continue
        if 0 <= x < width and 0 <= y < height:
            result.append((index, x, y))
    return result


class PositionImage(QLabel):
    chosen = Signal(int, int)

    def __init__(self, frame, entries=(), selected=0, read_only=False):
        super().__init__()
        self.height_px, self.width_px = frame.shape[:2]
        self.read_only = read_only
        self.markers = configured_positions(entries, self.width_px, self.height_px)
        image = QImage(frame.data, self.width_px, self.height_px, frame.strides[0],
                       QImage.Format_ARGB32).copy()
        pixmap = QPixmap.fromImage(image).scaled(1000, 650, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        overlaps = {}
        for index, x, y in self.markers:
            px, py = x * pixmap.width() / self.width_px, y * pixmap.height() / self.height_px
            count = overlaps.get((x, y), 0)
            overlaps[(x, y)] = count + 1
            # Offset overlapping labels so multiple indexes at one spot remain legible.
            px += (count % 4) * 32
            py -= (count // 4) * 32
            px = max(17, min(pixmap.width() - 17, px))
            py = max(17, min(pixmap.height() - 17, py))
            selected_marker = index == selected + 1
            painter.setPen(QPen(QColor("#fce8ef"), 2))
            painter.setBrush(QColor("#b12b5e") if selected_marker else QColor("#26202b"))
            painter.drawEllipse(QPointF(px, py), 15, 15)
            painter.setPen(QColor("white"))
            painter.drawText(QRectF(px - 15, py - 15, 30, 30), Qt.AlignCenter, str(index))
        painter.end()
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.setCursor(Qt.ArrowCursor if read_only else Qt.CrossCursor)

    def mousePressEvent(self, event):
        if not self.read_only and event.button() == Qt.LeftButton:
            x = max(0, min(self.width_px - 1, int(event.position().x() * self.width_px / self.width())))
            y = max(0, min(self.height_px - 1, int(event.position().y() * self.height_px / self.height())))
            self.chosen.emit(x, y)


class UnitManager(QWidget):
    """One built-in editor for the 104 saved indexes of the selected route.

    Callbacks deliberately stay compatible with RuntimeWindow's INI persistence:
    save(index_zero_based, entry_dict), busy() and log(message).
    """

    def __init__(self, entries, save, busy, log, parent=None, record=None,slot_count=6):
        super().__init__(parent)
        self.entries, self.save, self.busy, self.log = entries, save, busy, log
        self.selected, self.page, self.loading = 0, 0, False
        self.copied_index = None
        self.record_callback=record
        self.recording=False
        self.slot_count=slot_count

        self.setObjectName("unit-editor")
        self.setStyleSheet("""
            QWidget#unit-editor { background: transparent; color: #f4f0f3; font: 10px 'Segoe UI'; }
            QLabel { background: transparent; color: #f4f0f3; }
            QLabel#title { font: 700 18px 'Segoe UI'; color: #fff7fa; }
            QLabel#subtitle { font: 10px 'Segoe UI'; color: #aea0ab; }
            QLabel#section { font: 700 10px 'Segoe UI'; color: #edc2d1; }
            QLabel#saved { font: 600 9px 'Segoe UI'; color: #8edcbb; }
            QLabel#page { font: 600 9px 'Segoe UI'; color: #c8b5c1; }
            QFrame#editor-card { background: #1b1820; border: 1px solid #4b3845; border-radius: 12px; }
            QComboBox,QSpinBox,QLineEdit {
                background: #100f15; color: #f9eff3; border: 1px solid #564251;
                border-radius: 7px; min-height: 28px; padding: 4px 8px;
            }
            QComboBox:hover,QSpinBox:hover,QLineEdit:hover { border-color: #a46580; }
            QComboBox:focus,QSpinBox:focus,QLineEdit:focus { border-color: #e07f9f; }
            QComboBox QAbstractItemView { background: #28212b; color: #f7eef4; selection-background-color: #873851; }
            QPushButton {
                background: #302631; color: #f2e7ed; border: 1px solid #604555;
                border-radius: 8px; padding: 6px; font: 600 10px 'Segoe UI';
            }
            QPushButton:hover { background: #473044; border-color: #bf708d; }
            QPushButton:disabled { color: #80727b; border-color: #46343e; }
            QPushButton#primary { background: #893651; color: white; border-color: #c56583; }
            QPushButton#primary:hover { background: #a24665; }
            QPushButton#reset { background: #2b2029; color: #e8b5c0; }
            QPushButton#index-card {
                background: #1b171e; color: #ccbfc8; border: 1px solid #493745;
                border-radius: 9px; text-align: left; padding: 6px 10px; font: 9px 'Segoe UI';
            }
            QPushButton#index-card:hover { background: #332330; border-color: #a66080; }
            QPushButton#index-card[selected="true"] {
                background: #452634; color: #fff4f8; border: 2px solid #e183a6;
            }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(9, 7, 9, 7)
        root.setSpacing(8)

        header = QHBoxLayout()
        title_area = QVBoxLayout()
        title_area.setSpacing(2)
        title_area.addWidget(self._text("Unit manager", "title"))
        title_area.addWidget(self._text("Deployments · Configure each step", "subtitle"))
        header.addLayout(title_area, 1)
        header.addWidget(self._text("●  Auto-save", "saved"), 0, Qt.AlignVCenter)
        root.addLayout(header)

        self.editor_card = QFrame()
        self.editor_card.setObjectName("editor-card")
        editor = QVBoxLayout(self.editor_card)
        editor.setContentsMargins(13, 11, 13, 11)
        editor.setSpacing(7)
        editor.addWidget(self._text("SELECTED INDEX", "section"))
        self.heading = self._text("", "title")
        editor.addWidget(self.heading)
        path_row=QHBoxLayout()
        self.record_button=self._button('Record',self.toggle_record,'primary')
        path_row.addWidget(self._text('WASD Auto Path','subtitle'))
        path_row.addWidget(self.record_button)
        editor.addLayout(path_row)
        self.path_note=self._text('Path recording: F3 stops. Reset removes a saved path.','subtitle')
        editor.addWidget(self.path_note)

        self.fields = {}
        labels = [
            ("unit", "Unit slot"), ("priority", "Target priority"),
            ("upgrade", "Upgrade level"), ("auto_upgrade", "Auto upgrade"),
            ("x", "Position X"), ("y", "Position Y"),
            ("place_at_wave", "Place at wave"),
            ("auto_ability_wave", "Auto Ability Check"),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        positions = QGridLayout()
        positions.setHorizontalSpacing(6)
        grid.addLayout(positions, 4, 0, 4, 1, Qt.AlignTop)
        for i, (key, name) in enumerate(labels):
            col, row = i % 2, (i // 2) * 2
            target_grid = grid
            if key in ("x", "y"):
                target_grid, row, col = positions, 0, int(key == "y")
            elif key == "place_at_wave":
                row, col = 4, 1
            elif key == "auto_ability_wave":
                row, col = 6, 1
            target_grid.addWidget(self._text(name, "subtitle"), row, col)
            if key in ("unit", "priority", "upgrade", "auto_upgrade"):
                options = {"unit": [str(n) for n in range(self.slot_count+1)],
                           "priority": TARGETS,
                           "upgrade": [str(n) for n in range(16)],
                           "auto_upgrade": [str(n) for n in range(7)]}
                field = QComboBox()
                field.addItems(options[key])
                field.currentTextChanged.connect(self.changed)
            elif key in ("place_at_wave", "auto_ability_wave"):
                field = QLineEdit()
                field.setObjectName(key.replace("_", "-"))
                field.setPlaceholderText("Any" if key == "place_at_wave" else "Wave (blank = off)")
                field.setToolTip("Wave 1-9999 for an additional ability check. Abilities are also checked when the index completes. Blank disables only the scheduled check." if key == "auto_ability_wave" else "Blank places when ready.")
                field.setValidator(QRegularExpressionValidator(
                    QRegularExpression(r"(?:[1-9][0-9]{0,3})?"), field
                ))
                field.editingFinished.connect(self.changed)
                if key == "place_at_wave":
                    self.wave_input = field
            else:
                field = QSpinBox()
                field.setRange(-1, 10000)
                field.setSpecialValueText("Not set")
                field.setButtonSymbols(QAbstractSpinBox.NoButtons)
                field.setKeyboardTracking(False)
                field.setFixedWidth(80)
                field.valueChanged.connect(self.changed)
            self.fields[key] = field
            target_grid.addWidget(field, row + 1, col)
        editor.addLayout(grid)

        position_actions = QHBoxLayout()
        self.capture_button = self._button("Set position", self.capture_position, "primary")
        self.view_positions_button = self._button("View markers", self.view_positions)
        self.clear_position_button = self._button("Clear", self.clear_position)
        position_actions.addWidget(self.capture_button, 2)
        position_actions.addWidget(self.view_positions_button, 2)
        position_actions.addWidget(self.clear_position_button, 1)
        editor.addLayout(position_actions)

        actions = QHBoxLayout()
        self.copy_button = self._button("Copy", self.copy_index)
        self.paste_button = self._button("Paste", self.paste_index)
        self.clear_button = self._button("Reset", self.clear_index, "reset")
        self.paste_button.setEnabled(False)
        for button in (self.copy_button, self.paste_button, self.clear_button):
            actions.addWidget(button, 1)
        editor.addLayout(actions)
        root.addWidget(self.editor_card)

        card_heading = QHBoxLayout()
        card_heading.addWidget(self._text("Index library", "section"))
        card_heading.addStretch()
        self.page_indicator = self._text("", "page")
        card_heading.addWidget(self.page_indicator)
        card_heading.addWidget(self._text(f"· {len(entries)} indexes", "subtitle"))
        root.addLayout(card_heading)

        self.cards = []
        cards = QGridLayout()
        cards.setSpacing(7)
        for offset in range(PAGE_SIZE):
            button = QPushButton()
            button.setObjectName("index-card")
            button.setFixedHeight(86)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, offset=offset: self.select(self.page * PAGE_SIZE + offset))
            cards.addWidget(button, offset // 2, offset % 2)
            self.cards.append(button)
        root.addLayout(cards)
        root.addStretch()

        nav = QHBoxLayout()
        self.previous = self._button("←  Previous", lambda: self.select((self.page - 1) * PAGE_SIZE))
        self.next = self._button("Next  →", lambda: self.select((self.page + 1) * PAGE_SIZE))
        nav.addWidget(self.previous, 1)
        nav.addWidget(self.next, 1)
        root.addLayout(nav)

        if self.entries:
            self.select(0)

    @staticmethod
    def _text(value, name):
        field = QLabel(value)
        field.setObjectName(name)
        field.setWordWrap(True)
        return field

    @staticmethod
    def _button(value, callback, style=None):
        button = QPushButton(value)
        if style:
            button.setObjectName(style)
        button.clicked.connect(callback)
        return button

    def select(self, index):
        if self.recording or not 0 <= index < len(self.entries):
            return
        self.selected, self.page, self.loading = index, index // PAGE_SIZE, True
        entry = self.entries[index]
        self.heading.setText(f"Index {index + 1:03d}")
        for key, field in self.fields.items():
            value = str(entry.get(key, EMPTY_INDEX[key]))
            if isinstance(field, QComboBox):
                if key == "unit":
                    # Older profiles used None or Unit N; 0 is the empty slot.
                    value = value.removeprefix("Unit ")
                    if value not in {str(n) for n in range(self.slot_count+1)}:
                        value = "0"
                if field.findText(value) < 0:
                    # Retain historical upgrade or target choices.
                    field.addItem(value)
                field.setCurrentText(value)
            elif isinstance(field, QLineEdit):
                field.setText(value)
            else:
                field.setValue(int(value) if value else -1 if key in ("x", "y") else 0)
        self.loading = False
        self.update_path_controls()
        self.refresh_cards()

    def update_path_controls(self):
        path=bool(self.entries[self.selected].get('path'))
        for field in self.fields.values():
            field.setEnabled(not path and not self.recording)
        for button in (self.capture_button,self.clear_position_button):
            button.setEnabled(not path and not self.recording)
        for button in (self.copy_button,self.clear_button,self.previous,self.next,*self.cards):
            button.setEnabled(not self.recording)
        self.paste_button.setEnabled(self.copied_index is not None and not self.recording)
        self.record_button.setText('Stop Recording' if self.recording else 'Record')
        self.path_note.setText('Recording Roblox movement. F3 stops.' if self.recording else
                              'First run only. Reset removes the path.' if path else
                              'WASD only, first run only. F3 stops recording.')

    def toggle_record(self):
        if self.record_callback is None:
            self.log('Path recording is available in the runtime dashboard.')
            return
        if not self.recording and self.busy():
            self.log('Stop the macro before recording a path.')
            return
        self.record_callback(self.selected)

    def recording_changed(self,active):
        self.recording=active
        self.update_path_controls()

    def save_path(self,index,raw):
        self.recording_changed(False)
        if raw:
            self.selected=index
            if self._commit({**EMPTY_INDEX,'path':raw}):
                self.select(index)
                self.log(f'Path saved to Index {index+1}.')

    def refresh_cards(self):
        count = len(self.entries)
        total_pages = max(1, ceil(count / PAGE_SIZE))
        self.page_indicator.setText(f"PAGE {self.page + 1} / {total_pages}")
        for offset, button in enumerate(self.cards):
            index = self.page * PAGE_SIZE + offset
            button.setVisible(index < count)
            if index >= count:
                continue
            entry = self.entries[index]
            coords = (f"{entry['x']}, {entry['y']}"
                      if entry.get("x", "") != "" and entry.get("y", "") != "" else "Not set")
            wave = entry.get("place_at_wave", "")
            wave_label = f"Wave {wave}" if wave else "Any wave"
            ability = entry.get('auto_ability_wave','')
            ability_label = f"Ability: wave {ability}" if ability else "Ability: on completion"
            button.setText(
                f"{index + 1:02d}   Unit {entry['unit']}  ·  {entry['priority']}\n"
                f"Upgrade {entry['upgrade']}  /  Auto {entry['auto_upgrade']}\n"
                f"POS  {coords}  ·  {wave_label}\n{ability_label}"
            )
            if entry.get('path'):
                try:
                    from python_macro.pathing import decode_path
                    path=decode_path(entry['path'])
                    button.setText(f"{index+1:02d}   PATH\nWASD  /  {path['duration']:.1f}s\nFirst run only")
                except ValueError:
                    button.setText(f'{index+1:02d}   PATH\nInvalid recording - please record again')
            button.setProperty("selected", index == self.selected)
            button.style().unpolish(button)
            button.style().polish(button)
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled((self.page + 1) * PAGE_SIZE < count)

    def _commit(self, entry):
        entry = {**EMPTY_INDEX, **entry}
        try:
            from python_macro.deployment import requested_wave
            requested_wave(entry["place_at_wave"])
            requested_wave(entry["auto_ability_wave"])
            if entry.get('path'):
                from python_macro.pathing import decode_path
                decode_path(entry['path'])
                entry={**EMPTY_INDEX,'path':entry['path']}
            self.save(self.selected, entry)
        except (OSError, ValueError) as error:
            self.log(f"Could not save index: {error}")
            return False
        self.entries[self.selected] = dict(entry)
        if self.busy():
            self.log("Settings saved for the next run.")
        self.refresh_cards()
        return True

    def changed(self, *_):
        if self.loading or self.recording or self.entries[self.selected].get('path'):
            return
        entry = {
            key: (field.currentText() if isinstance(field, QComboBox)
                  else field.text().strip() if isinstance(field, QLineEdit)
                  else "" if field.value() < 0 else str(field.value()))
            for key, field in self.fields.items()
        }
        if not self._commit(entry):
            self.select(self.selected)

    def copy_index(self):
        self.copied_index = {**EMPTY_INDEX, **self.entries[self.selected]}
        self.paste_button.setEnabled(True)
        self.log(f"Copied unit index {self.selected + 1}.")

    def paste_index(self):
        if self.copied_index is None:
            return
        if self._commit(dict(self.copied_index)):
            self.select(self.selected)
            self.log(f"Pasted settings into unit index {self.selected + 1}.")

    def clear_index(self):
        if self._commit(dict(EMPTY_INDEX)):
            self.select(self.selected)

    def clear_position(self):
        entry = dict(self.entries[self.selected], x="", y="")
        if self._commit(entry):
            self.select(self.selected)

    def view_positions(self):
        self._position_dialog(read_only=True)

    def capture_position(self):
        self._position_dialog(read_only=False)

    def _position_dialog(self, read_only=False):
        if not read_only and self.busy():
            self.log("Stop the macro before setting a position.")
            return
        from python_macro.capture import roblox_windows, capture_client
        try:
            windows = roblox_windows()
            if len(windows) != 1:
                raise RuntimeError("Open exactly one Roblox window.")
            frame = capture_client(windows[0][0])
            dialog = QDialog(self)
            dialog.setWindowTitle("Saved position markers" if read_only else "Set position")
            layout = QVBoxLayout(dialog)
            instructions = QLabel(
                "Numbered markers show saved index positions; pink is selected. "
                + ("Close to return." if read_only else "Click the screenshot to save a new location.")
            )
            instructions.setWordWrap(True)
            layout.addWidget(instructions)
            image = PositionImage(frame, self.entries, self.selected, read_only=read_only)
            layout.addWidget(image)
            if not read_only:
                def chosen(x, y):
                    entry = dict(self.entries[self.selected], x=str(x), y=str(y))
                    if self._commit(entry):
                        self.select(self.selected)
                        dialog.accept()
                image.chosen.connect(chosen)
            close = QPushButton("Close" if read_only else "Cancel")
            close.clicked.connect(dialog.reject)
            layout.addWidget(close)
            dialog.exec()
        except (OSError, RuntimeError, ValueError) as error:
            self.log(f"Position capture unavailable: {error}")
