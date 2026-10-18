"""AHK-style in-dashboard Unit Manager with per-route auto-saving indexes."""
from math import ceil

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QDialog, QFrame,
)


EMPTY_INDEX = {
    "unit": "None", "priority": "First", "upgrade": "0",
    "auto_upgrade": "0", "x": "", "y": "",
}
PAGE_SIZE = 6
TARGETS = ["First", "Last", "Closest", "Strongest", "Boss",
           "Weakest", "Shielded", "Fastest", "Flying"]


class PositionImage(QLabel):
    chosen = Signal(int, int)

    def __init__(self, frame):
        super().__init__()
        self.height_px, self.width_px = frame.shape[:2]
        image = QImage(frame.data, self.width_px, self.height_px, frame.strides[0],
                       QImage.Format_ARGB32).copy()
        pixmap = QPixmap.fromImage(image).scaled(1000, 650, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            x = max(0, min(self.width_px - 1, int(event.position().x() * self.width_px / self.width())))
            y = max(0, min(self.height_px - 1, int(event.position().y() * self.height_px / self.height())))
            self.chosen.emit(x, y)


class UnitManager(QWidget):
    """One built-in editor for the 104 saved indexes of the selected route.

    Callbacks deliberately stay compatible with RuntimeWindow's INI persistence:
    save(index_zero_based, entry_dict), busy() and log(message).
    """

    def __init__(self, entries, save, busy, log, parent=None):
        super().__init__(parent)
        self.entries, self.save, self.busy, self.log = entries, save, busy, log
        self.selected, self.page, self.loading = 0, 0, False
        self.copied_index = None
        self.setObjectName("unit-editor")
        self.setStyleSheet("""
            QWidget#unit-editor { background: transparent; color:#f3eff0; font: 10px 'Segoe UI'; }
            QLabel { color:#f3eff0; background:transparent; }
            QLabel#muted { color:#af999f; }
            QLabel#kicker { color:#e29caf; font:700 9px 'Bahnschrift'; }
            QLabel#section { color:#f5e6ea; font:700 13px 'Bahnschrift'; }
            QFrame#separator { background:#632336; max-height:1px; border:0; }
            QComboBox,QSpinBox {
                background:#1b1015; color:#f5e9eb; border:1px solid #5b2838;
                border-radius:6px; padding:4px 7px; min-height:26px;
            }
            QComboBox:focus,QSpinBox:focus { border-color:#d25e83; }
            QComboBox QAbstractItemView {
                background:#211218; color:#f5e9eb; selection-background-color:#7e1726;
            }
            QPushButton {
                background:#25131a; color:#f7e9ec; border:1px solid #673041;
                border-radius:6px; padding:6px 5px; font:700 9px 'Bahnschrift';
            }
            QPushButton:hover { background:#4a1a2b; border-color:#b04b6b; }
            QPushButton:disabled { color:#82727a; border-color:#422a33; }
            QPushButton#primary { background:#7e1726; border-color:#b44462; }
            QPushButton#index-card {
                text-align:left; padding:7px 10px;
                background:#160f12; border:1px solid #432733;
                font:9px 'Segoe UI'; border-radius:8px;
            }
            QPushButton#index-card[selected="true"] {
                background:#441521; border:2px solid #d25e83;
            }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 7)
        root.setSpacing(7)

        root.addWidget(self._text("UNIT MANAGER", "section"))
        root.addWidget(self._text("Select, configure and save unit indexes for this route.", "muted"))

        header = QHBoxLayout()
        header.addWidget(self._text("JUMP TO INDEX", "kicker"))
        self.index_picker = QSpinBox()
        self.index_picker.setObjectName("index-picker")
        self.index_picker.setRange(1, max(1, len(entries)))
        self.index_picker.setFixedWidth(82)
        self.index_picker.valueChanged.connect(lambda value: self.select(value - 1))
        header.addWidget(self.index_picker)
        header.addStretch()
        self.page_indicator = self._text("", "muted")
        header.addWidget(self.page_indicator)
        root.addLayout(header)

        divider = QFrame()
        divider.setObjectName("separator")
        root.addWidget(divider)
        self.heading = self._text("", "kicker")
        root.addWidget(self.heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        root.addLayout(grid)
        self.fields = {}
        labels = [
            ("unit", "UNIT SLOT"), ("priority", "TARGET PRIORITY"),
            ("upgrade", "UPGRADE LEVEL"), ("auto_upgrade", "AUTO UPGRADE"),
            ("x", "POSITION X"), ("y", "POSITION Y"),
        ]
        for index, (key, name) in enumerate(labels):
            column, row = index % 2, (index // 2) * 2
            grid.addWidget(self._text(name, "kicker"), row, column)
            if key in ("unit", "priority"):
                field = QComboBox()
                field.addItems(["None"] + [str(i) for i in range(1, 11)] if key == "unit" else TARGETS)
                field.currentTextChanged.connect(self.changed)
            else:
                field = QSpinBox()
                field.setRange(-1 if key in ("x", "y") else 0,
                               10000 if key in ("x", "y") else 100)
                if key in ("x", "y"):
                    field.setSpecialValueText("Not set")
                field.setKeyboardTracking(False)
                field.valueChanged.connect(self.changed)
            self.fields[key] = field
            grid.addWidget(field, row + 1, column)

        coordinate_actions = QHBoxLayout()
        self.capture_button = self._button("SET POSITION", self.capture_position, "primary")
        self.clear_position_button = self._button("CLEAR POSITION", self.clear_position)
        coordinate_actions.addWidget(self.capture_button)
        coordinate_actions.addWidget(self.clear_position_button)
        root.addLayout(coordinate_actions)

        index_actions = QHBoxLayout()
        self.copy_button = self._button("COPY INDEX", self.copy_index)
        self.paste_button = self._button("PASTE INDEX", self.paste_index)
        self.clear_button = self._button("CLEAR INDEX", self.clear_index)
        index_actions.addWidget(self.copy_button)
        index_actions.addWidget(self.paste_button)
        index_actions.addWidget(self.clear_button)
        root.addLayout(index_actions)
        self.paste_button.setEnabled(False)

        root.addWidget(self._text("SAVED INDEXES • Click a card to edit", "kicker"))
        self.cards = []
        cards = QGridLayout()
        cards.setSpacing(7)
        root.addLayout(cards)
        for offset in range(PAGE_SIZE):
            card = QPushButton()
            card.setObjectName("index-card")
            card.setMinimumHeight(84)
            card.clicked.connect(lambda checked=False, offset=offset:
                                 self.select(self.page * PAGE_SIZE + offset))
            cards.addWidget(card, offset // 2, offset % 2)
            self.cards.append(card)

        root.addStretch()
        navigation = QHBoxLayout()
        self.previous = self._button("← PREVIOUS", lambda: self.select((self.page - 1) * PAGE_SIZE))
        self.next = self._button("NEXT →", lambda: self.select((self.page + 1) * PAGE_SIZE))
        navigation.addWidget(self.previous)
        navigation.addWidget(self.next)
        root.addLayout(navigation)

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
        if not 0 <= index < len(self.entries):
            return
        self.selected, self.page, self.loading = index, index // PAGE_SIZE, True
        entry = self.entries[index]
        self.heading.setText(f"EDIT INDEX {index + 1:03d}  •  AUTO SAVE")
        self.index_picker.setValue(index + 1)
        for key, field in self.fields.items():
            value = str(entry.get(key, EMPTY_INDEX[key]))
            if isinstance(field, QComboBox):
                if key == "unit":
                    value = value.removeprefix("Unit ")
                if field.findText(value) < 0:
                    field.addItem(value)
                field.setCurrentText(value)
            else:
                field.setValue(int(value) if value else -1 if key in ("x", "y") else 0)
        self.loading = False
        self.refresh_cards()

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
            button.setText(
                f"INDEX {index + 1:03d}  •  {entry['unit']}\n"
                f"TARGET  {entry['priority']}\n"
                f"UPG  {entry['upgrade']}  /  AUTO  {entry['auto_upgrade']}\n"
                f"POS  {coords}"
            )
            button.setProperty("selected", index == self.selected)
            button.style().unpolish(button)
            button.style().polish(button)
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled((self.page + 1) * PAGE_SIZE < count)

    def _commit(self, entry):
        if self.busy():
            self.log("Stop the macro before editing unit indexes.")
            return False
        try:
            self.save(self.selected, entry)
        except (OSError, ValueError) as error:
            self.log(f"Could not save index: {error}")
            return False
        self.entries[self.selected] = dict(entry)
        self.refresh_cards()
        return True

    def changed(self, *_):
        if self.loading:
            return
        entry = {
            key: field.currentText() if isinstance(field, QComboBox)
            else ("" if field.value() < 0 else str(field.value()))
            for key, field in self.fields.items()
        }
        if not self._commit(entry):
            self.select(self.selected)

    def copy_index(self):
        self.copied_index = dict(self.entries[self.selected])
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

    def capture_position(self):
        if self.busy():
            self.log("Stop the macro before setting a position.")
            return
        from python_macro.capture import roblox_windows, capture_client
        try:
            windows = roblox_windows()
            if len(windows) != 1:
                raise RuntimeError("Open exactly one Roblox window.")
            frame = capture_client(windows[0][0])
            dialog = QDialog(self)
            dialog.setWindowTitle("Choose a placement position on the Roblox snapshot • Esc cancels")
            layout = QVBoxLayout(dialog)
            image = PositionImage(frame)
            layout.addWidget(image)

            def chosen(x, y):
                entry = dict(self.entries[self.selected], x=str(x), y=str(y))
                if self._commit(entry):
                    self.select(self.selected)
                    dialog.accept()

            image.chosen.connect(chosen)
            dialog.exec()
        except (OSError, RuntimeError, ValueError) as error:
            self.log(f"Position capture unavailable: {error}")
