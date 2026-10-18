"""Runtime index editor with client-relative screenshot position capture."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton,
                               QComboBox, QSpinBox, QDialog)


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
            self.chosen.emit(min(self.width_px - 1, int(event.position().x() * self.width_px / self.width())),
                             min(self.height_px - 1, int(event.position().y() * self.height_px / self.height())))


class UnitManager(QWidget):
    def __init__(self, entries, save, busy, log, parent=None):
        super().__init__(parent)
        self.entries, self.save, self.busy, self.log = entries, save, busy, log
        self.selected, self.page, self.loading = 0, 0, False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("UNIT MANAGER"))
        self.heading = QLabel()
        layout.addWidget(self.heading)
        grid = QGridLayout()
        layout.addLayout(grid)
        self.fields = {}
        options = {"unit": ["None"] + [str(i) for i in range(1, 11)],
                   "priority": ["First", "Last", "Closest", "Strongest", "Boss", "Weakest", "Shielded", "Fastest", "Flying"]}
        labels = {"unit": "Unit slot", "priority": "Target", "upgrade": "Upgrade level",
                  "auto_upgrade": "Auto-upgrade priority", "x": "Position X", "y": "Position Y"}
        for i, key in enumerate(labels):
            grid.addWidget(QLabel(labels[key]), (i // 2) * 2, i % 2)
            if key in options:
                field = QComboBox()
                field.addItems(options[key])
                field.currentTextChanged.connect(self.changed)
            else:
                field = QSpinBox()
                field.setRange(-1 if key in ("x", "y") else 0, 10000 if key in ("x", "y") else 100)
                if key in ("x", "y"):
                    field.setSpecialValueText("Not set")
                field.setKeyboardTracking(False)
                field.valueChanged.connect(self.changed)
            self.fields[key] = field
            grid.addWidget(field, (i // 2) * 2 + 1, i % 2)
        capture = QPushButton("SET POSITION")
        capture.clicked.connect(self.capture_position)
        layout.addWidget(capture)
        clear = QPushButton("CLEAR SELECTED INDEX")
        clear.clicked.connect(self.clear_index)
        layout.addWidget(clear)
        cards = QGridLayout()
        layout.addLayout(cards)
        self.cards = []
        for offset in range(6):
            button = QPushButton()
            button.setMinimumHeight(105)
            button.clicked.connect(lambda checked=False, offset=offset: self.select(self.page * 6 + offset))
            cards.addWidget(button, offset // 2, offset % 2)
            self.cards.append(button)
        layout.addStretch()
        nav = QGridLayout()
        layout.addLayout(nav)
        self.previous, self.next = QPushButton("PREVIOUS"), QPushButton("NEXT")
        self.previous.clicked.connect(lambda: self.select((self.page - 1) * 6))
        self.next.clicked.connect(lambda: self.select((self.page + 1) * 6))
        nav.addWidget(self.previous, 0, 0)
        nav.addWidget(self.next, 0, 1)
        self.setStyleSheet("QWidget {color:#f3eff0;font:10px 'Segoe UI';} QComboBox,QSpinBox,QPushButton {background:#201318;border:1px solid #7e1726;padding:6px;} QPushButton:disabled {color:#776b70;} QPushButton:hover {background:#4c1019;}")
        self.select(0)

    def select(self, index):
        if not 0 <= index < len(self.entries):
            return
        self.selected, self.page, self.loading = index, index // 6, True
        entry = self.entries[index]
        self.heading.setText(f"INDEX {index + 1}  |  Changes save automatically")
        for key, field in self.fields.items():
            value = entry[key]
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
        for offset, button in enumerate(self.cards):
            index = self.page * 6 + offset
            button.setVisible(index < len(self.entries))
            if index >= len(self.entries):
                continue
            e = self.entries[index]
            position = f"{e['x']}, {e['y']}" if e['x'] and e['y'] else "Not set"
            button.setText(f"{'[Selected] ' if index == self.selected else ''}INDEX {index + 1}\nUnit: {e['unit']} | {e['priority']}\nUpg: {e['upgrade']} | Auto: {e['auto_upgrade']}\nPosition: {position}")
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled((self.page + 1) * 6 < len(self.entries))

    def changed(self, *_):
        if self.loading:
            return
        if self.busy():
            self.log("Stop the macro before editing indexes.")
            self.select(self.selected)
            return
        entry = {key: field.currentText() if isinstance(field, QComboBox) else
                 "" if field.value() < 0 else str(field.value()) for key, field in self.fields.items()}
        try:
            self.save(self.selected, entry)
        except OSError as exc:
            self.log(f"Could not save index: {exc}")
            self.select(self.selected)
            return
        self.entries[self.selected] = entry
        self.refresh_cards()

    def clear_index(self):
        if self.busy():
            self.log("Stop the macro before clearing indexes.")
            return
        self.loading = True
        for key, field in self.fields.items():
            if isinstance(field, QComboBox):
                field.setCurrentIndex(0)
            else:
                field.setValue(-1 if key in ("x", "y") else 0)
        self.loading = False
        self.changed()

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
            dialog.setWindowTitle("Click a placement position on the Roblox snapshot - Esc cancels")
            layout = QVBoxLayout(dialog)
            image = PositionImage(frame)
            layout.addWidget(image)
            def chosen(x, y):
                self.loading = True
                self.fields['x'].setValue(x)
                self.fields['y'].setValue(y)
                self.loading = False
                self.changed()
                dialog.accept()
            image.chosen.connect(chosen)
            dialog.exec()
        except (OSError, RuntimeError) as exc:
            self.log(f"Position capture unavailable: {exc}")
