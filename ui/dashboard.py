from __future__ import annotations

import configparser
import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QTimer, Qt, QRegularExpression
from PySide6.QtGui import QColor, QFont, QFontDatabase, QKeySequence, QRegularExpressionValidator, QLinearGradient, QPainter, QPainterPath, QPixmap, QRadialGradient, QRegion
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QVBoxLayout, QWidget


ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
ASSETS = BUNDLE_ROOT / "assets"
CONFIG_PATH = ROOT / "Scatter Macro" / "dashboard_config.ini"
if not CONFIG_PATH.exists():
    CONFIG_PATH = ROOT / "dashboard_config.ini"
COMMAND_PATH = CONFIG_PATH.with_name("python_ui_command.ini")
STATUS_PATH = CONFIG_PATH.with_name("python_ui_runtime.ini")
LOG_PATH = CONFIG_PATH.with_name("python_ui_runtime.log")
CHEVRON_PATH = (ASSETS / "dropdown-chevron.svg").as_posix()
ACTIVE_DASHBOARD = None
SINGLE_INSTANCE_HANDLES: dict[str, int] = {}

WINE = "#7e1726"
WINE_DARK = "#4c1019"
PANEL = "#100c0e"
FIELD = "#121113"
OUTLINE = "#4a4348"
TEXT = "#f3eff0"
MUTED = "#a8a1a5"

MODE_MAPS = {
    "Story": ["School Grounds", "Flower Forest", "Rose Kingdom", "Fairy King Forest", "King's Tomb", "East Town"],
    "Challenges": ["Auto"],
    "Raid": ["Spirit City"],
    "Tower": ["Trait Tower", "Traitless Tower"],
    "Expeditions": ["School Grounds", "Flower Forest", "Rose Kingdom", "East Town"],
}
MODE_ACTS = {
    "Story": ["Act 1", "Act 2", "Act 3", "Act 4", "Act 5", "Infinite", "Mastery"],
    "Challenges": ["Auto"],
    "Raid": ["Act 1", "Act 2", "Act 3"],
    "Tower": ["Floors"],
    "Expeditions": ["Expedition"],
}


def acquire_single_instance(screen: str) -> bool:
    """Prevent duplicate helper windows even when the UI executable is launched directly."""
    if "--render-preview" in sys.argv or sys.platform != "win32":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.restype = ctypes.c_void_p
    handle = create_mutex(None, False, f"Local\\ScatterMacro.{screen}.Singleton")
    if not handle:
        return False
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    SINGLE_INSTANCE_HANDLES[screen] = handle
    return True


def release_single_instance(screen: str) -> None:
    handle = SINGLE_INSTANCE_HANDLES.pop(screen, None)
    if handle and sys.platform == "win32":
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(ctypes.c_void_p(handle))


def normalize_hex_color(value: str, fallback: str) -> str:
    candidate = value.strip().lstrip("#")
    if len(candidate) == 6 and all(character in "0123456789abcdefABCDEF" for character in candidate):
        return f"#{candidate.upper()}"
    return fallback


def blend_color(first: str, second: str, amount: float) -> str:
    start = QColor(first)
    end = QColor(second)
    red = round(start.red() + (end.red() - start.red()) * amount)
    green = round(start.green() + (end.green() - start.green()) * amount)
    blue = round(start.blue() + (end.blue() - start.blue()) * amount)
    return f"#{red:02X}{green:02X}{blue:02X}"


def apply_theme_palette(primary: str, accent: str) -> None:
    global WINE, WINE_DARK, PANEL, FIELD, OUTLINE
    primary = normalize_hex_color(primary, "#080809")
    accent = normalize_hex_color(accent, "#5A0F1B")
    WINE = accent
    WINE_DARK = blend_color(accent, "#000000", 0.45)
    PANEL = blend_color(primary, "#FFFFFF", 0.04)
    FIELD = blend_color(primary, "#FFFFFF", 0.07)
    OUTLINE = blend_color(accent, "#FFFFFF", 0.25)


def read_dashboard_values() -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    read_ini(parser, CONFIG_PATH)
    dashboard = parser["Dashboard"] if parser.has_section("Dashboard") else {}
    updates = parser["Updates"] if parser.has_section("Updates") else {}
    discord = parser["Discord"] if parser.has_section("Discord") else {}
    roblox = parser["Roblox"] if parser.has_section("Roblox") else {}
    settings = parser["Settings"] if parser.has_section("Settings") else {}
    notifications = parser["Notifications"] if parser.has_section("Notifications") else {}
    mode = dashboard.get("Mode", "Story")
    map_name = dashboard.get("Map", "School Grounds")
    if mode == "Tower":
        map_name = dashboard.get("TowerType", "Trait Tower")
    elif mode == "Challenges":
        map_name = "Auto"
    return {
        "mode": mode,
        "map": map_name,
        "act": dashboard.get("Act", "Act 1"),
        "difficulty": dashboard.get("ExpeditionDifficulty", dashboard.get("Difficulty", "1")) if mode == "Expeditions" else dashboard.get("Difficulty", "Normal"),
        "expedition_difficulty": dashboard.get("ExpeditionDifficulty", "1"),
        "tower_type": dashboard.get("TowerType", "Trait Tower"),
        "private_server": roblox.get("PrivateServerLink", ""),
        "webhook": discord.get("Webhook", ""),
        "discord_id": discord.get("UserID", ""),
        "automatic_check": updates.get("AutomaticCheck", "1"),
        "primary_color": settings.get("PrimaryColor", "#080809"),
        "accent_color": settings.get("AccentColor", "#5A0F1B"),
        "start_key": settings.get("StartKey", "F1"),
        "stop_key": settings.get("StopKey", "F2"),
        "minimize_to_tray": settings.get("MinimizeToTray", "0"),
        "runtime_on_top": settings.get("RuntimeAlwaysOnTop", "1"),
        "roblox_timeout": settings.get("RobloxTimeoutSeconds", "90"),
        "ping_victory": notifications.get("Victory", "1"),
        "ping_defeat": notifications.get("Defeat", "1"),
        "ping_error": notifications.get("Error", "0"),
    }


def read_ini(parser: configparser.ConfigParser, path: Path) -> None:
    if not path.exists():
        return
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    parser.read_string(raw.decode(encoding))


def write_ini(parser: configparser.ConfigParser, path: Path) -> None:
    from io import StringIO

    stream = StringIO()
    parser.write(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(stream.getvalue(), encoding="utf-16")
    temporary.replace(path)


def send_command(action: str) -> None:
    # No legacy process or command-file bridge is used by the replacement.
    if action in {"Exit", "RuntimeClose", "SettingsSaved"}:
        return
    QMessageBox.information(None, "Python rebuild", "This feature is being rebuilt in Python. No macro has been started.")


def write_runtime_status(hwnd: int, viewport: QRect, window: QWidget) -> None:
    # Window geometry will be consumed by the new in-process controller.
    return


def update_config(section: str, values: dict[str, str]) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    read_ini(parser, CONFIG_PATH)
    if not parser.has_section(section):
        parser.add_section(section)
    for key, value in values.items():
        parser.set(section, key, value)
    write_ini(parser, CONFIG_PATH)


class KeybindEdit(QLineEdit):
    """Captures one key combination in the display format used by the AHK hotkey registry."""

    def keyPressEvent(self, event) -> None:
        if event.key() in {
            Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
            Qt.Key_unknown,
        }:
            event.accept()
            return
        key = QKeySequence(event.key()).toString()
        if not key:
            return super().keyPressEvent(event)
        modifiers = event.modifiers()
        parts: list[str] = []
        if modifiers & Qt.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.MetaModifier:
            parts.append("Win")
        parts.append(key.upper())
        self.setText("+".join(parts))
        event.accept()


def config_segment(value: str) -> str:
    return "_".join(part for part in "".join(char if char.isalnum() else " " for char in value).split())


def active_unit_config(values: dict[str, str]) -> Path:
    mode = values["mode"]
    # The frozen UI runs from PyInstaller's temporary folder. The config passed
    # by the macro is the reliable anchor for the user's real profile files.
    config_root = (CONFIG_PATH.parent.parent if CONFIG_PATH.parent.name.casefold() == "scatter macro" else CONFIG_PATH.parent) / "configs"
    if mode == "Raid":
        return config_root / "Raid" / f"{config_segment(values['map'])}_{config_segment(values.get('act', 'Act 1'))}.ini"
    if mode == "Tower":
        return config_root / "Tower" / config_segment(values["tower_type"]) / "Auto.ini"
    if mode == "Challenges":
        return config_root / "Challenges" / "Auto.ini"
    if mode == "Expeditions":
        return config_root / "Expeditions" / f"{config_segment(values['map'])}.ini"
    return config_root / "Story" / f"{config_segment(values['map'])}.ini"


def load_unit_indexes(values: dict[str, str], count: int = 6) -> list[dict[str, str]]:
    return load_unit_indexes_from_path(active_unit_config(values), count)


def load_unit_indexes_from_path(config_path: Path, count: int = 6) -> list[dict[str, str]]:
    parser = configparser.ConfigParser()
    if config_path.exists():
        for encoding in ("utf-16", "utf-8-sig", "utf-8"):
            try:
                parser.read(config_path, encoding=encoding)
                break
            except UnicodeDecodeError:
                parser.clear()
    section = parser["UnitIndexes"] if parser.has_section("UnitIndexes") else {}
    indexes: list[dict[str, str]] = []
    for index in range(1, count + 1):
        prefix = f"Index{index}"
        indexes.append(
            {
                "unit": section.get(f"{prefix}Unit", "0"),
                "priority": section.get(f"{prefix}Priority", "First"),
                "upgrade": section.get(f"{prefix}Upgrade", "0"),
                "auto_upgrade": section.get(f"{prefix}AutoUpgrade", "0"),
                "x": section.get(f"{prefix}X", ""),
                "y": section.get(f"{prefix}Y", ""),
                "place_at_wave": section.get(f"{prefix}PlaceAtWave", ""),
            }
        )
    return indexes


class UnitSetupDialog(QDialog):
    def __init__(self, values, parent=None, first_index=1, count=6):
        super().__init__(parent)
        self.first_index = first_index
        self.count = count
        self.path = active_unit_config(values)
        self.setWindowTitle("Unit indexes | " + values["map"])
        self.resize(980, 400)
        self.setStyleSheet("QWidget {background:#100c0e;color:#f3eff0;} QComboBox,QSpinBox {background:#24131a;padding:6px;} QPushButton {background:#7e1726;padding:8px;}")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Saved setup only. Coordinates are relative to the Roblox client; no clicks are sent."))
        self.table = QTableWidget(count, 7)
        self.table.setVerticalHeaderLabels([str(i) for i in range(first_index, first_index + count)])
        self.table.setHorizontalHeaderLabels(["Unit slot", "Target", "Upgrade", "Auto upgrade", "X", "Y", "Place at wave"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        for row, entry in enumerate(load_unit_indexes(values, first_index + count - 1)[first_index - 1:]):
            for col, key in enumerate(("unit", "priority", "upgrade", "auto_upgrade", "x", "y", "place_at_wave")):
                if col < 2:
                    widget = QComboBox()
                    widget.addItems([str(i) for i in range(7)] if col == 0 else ["First", "Last", "Closest", "Strongest", "Weakest", "Flying"])
                    value = entry[key]
                    if key == "unit":
                        value = value.removeprefix("Unit ")
                        if value not in [str(n) for n in range(7)]:
                            value = "0"
                    if value not in [widget.itemText(i) for i in range(widget.count())]:
                        widget.addItem(value)
                    widget.setCurrentText(value)
                elif col == 6:
                    widget = QLineEdit(entry[key])
                    widget.setPlaceholderText("Any wave")
                    widget.setValidator(QRegularExpressionValidator(
                        QRegularExpression(r"(?:[1-9][0-9]{0,3})?"), widget
                    ))
                else:
                    widget = QSpinBox()
                    widget.setRange(-1 if col >= 4 else 0, 10000 if col >= 4 else 100)
                    if col >= 4:
                        widget.setSpecialValueText("Not set")
                    widget.setValue(int(entry[key]) if entry[key] else -1 if col >= 4 else 0)
                self.table.setCellWidget(row, col, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        parser = configparser.ConfigParser(interpolation=None)
        read_ini(parser, self.path)
        if not parser.has_section("UnitIndexes"):
            parser.add_section("UnitIndexes")
        for row in range(self.count):
            for col, key in enumerate(("Unit", "Priority", "Upgrade", "AutoUpgrade", "X", "Y", "PlaceAtWave")):
                widget = self.table.cellWidget(row, col)
                value = (widget.currentText() if col < 2
                         else widget.text().strip() if col == 6
                         else "" if widget.value() < 0 else str(widget.value()))
                if col == 6:
                    from python_macro.deployment import requested_wave
                    requested_wave(value)
                parser.set("UnitIndexes", f"Index{self.first_index + row}{key}", value)
        write_ini(parser, self.path)
        self.accept()


class DashboardWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.values = read_dashboard_values()
        self.drag_origin: QPoint | None = None
        self.setWindowTitle("Anime Expeditions | Setup")
        self.setFixedSize(1200, 720)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._build()

    def _build(self) -> None:
        self._header()
        self._route()
        self._configuration()
        self._private_server()
        self._deployment()

    def _card(self, x: int, y: int, width: int, height: int, radius: int = 7) -> QFrame:
        card = QFrame(self)
        card.setGeometry(x, y, width, height)
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card {{ background: {PANEL}; border: 1px solid {WINE_DARK}; border-radius: {radius}px; }}"
        )
        return card

    def _label(self, parent: QWidget, text: str, x: int, y: int, width: int, height: int, style: str) -> QLabel:
        label = QLabel(text, parent)
        label.setGeometry(x, y, width, height)
        label.setStyleSheet(style)
        return label

    def _section_title(self, parent: QWidget, text: str, y: int) -> None:
        self._label(parent, text, 22, y, 260, 24, f"color: {TEXT}; font: 700 14px 'Bahnschrift';")
        line = QFrame(parent)
        line.setGeometry(22, y + 34, parent.width() - 44, 1)
        line.setStyleSheet(f"background: {WINE}; border: none;")

    def _header(self) -> None:
        header = self._card(18, 16, 1164, 108, 9)
        logo_card = self._card(20, 20, 92, 84, 7)
        logo_card.setParent(header)
        logo_card.move(20, 20)
        logo = QLabel(logo_card)
        logo.setGeometry(13, 12, 66, 60)
        logo.setPixmap(QPixmap(str(ASSETS / "sm-logo.png")))
        logo.setScaledContents(True)
        self._label(header, "SCATTERMACRO", 132, 28, 180, 16, f"color: {WINE}; font: 700 8px 'Bahnschrift';")
        self._label(header, "ANIME EXPEDITION", 132, 46, 470, 42, f"color: {TEXT}; font: 700 28px 'Bahnschrift';")
        self._label(header, "\u25cf", 783, 30, 16, 18, "color: #47e887; font: 700 14px 'Segoe UI';")
        self._label(header, "SETUP MODE", 803, 30, 180, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
        discord_card = self._card(1040, 20, 90, 84, 7)
        discord_card.setParent(header)
        discord_card.move(1040, 20)
        discord = QLabel(discord_card)
        discord.setGeometry(10, 13, 70, 58)
        discord.setPixmap(QPixmap(str(ASSETS / "discord-logo.png")))
        discord.setScaledContents(True)

    def _route(self) -> None:
        route = self._card(18, 140, 1164, 52, 7)
        self._label(route, "ACTIVE ROUTE", 22, 16, 110, 18, f"color: {WINE}; font: 700 9px 'Bahnschrift';")
        self.route_value = self._label(route, "", 160, 15, 690, 20, f"color: {TEXT}; font: 700 10px 'Bahnschrift';")
        self.route_value.setText(f"Mode: {self.values['mode']} | Map: {self.values['map']}")

    def _configuration(self) -> None:
        config = self._card(18, 208, 680, 316, 8)
        self._section_title(config, "MATCH SETTINGS", 20)
        self._label(config, "ROUTE CONFIGURATION", 36, 66, 220, 18, f"color: {WINE}; font: 700 9px 'Bahnschrift';")
        self.mode_box = self._combo(config, "MODE", ["Story", "Challenges", "Raid", "Tower", "Expeditions"], self.values["mode"], 36, 97, 240)
        self.map_box = self._combo(config, "MAP", MODE_MAPS["Story"], self.values["map"], 314, 97, 320)
        self.difficulty_box = self._combo(config, "DIFFICULTY", ["Normal", "Hard"], self.values["difficulty"], 36, 187, 240)
        self.act_box = self._combo(config, "ACT", MODE_ACTS["Story"], self.values["act"], 314, 187, 320)
        self.mode_box.currentTextChanged.connect(self._mode_changed)
        for box in (self.map_box, self.difficulty_box):
            box.currentTextChanged.connect(self._save_dashboard)
        self.act_box.currentTextChanged.connect(self._act_changed)
        self.last_expedition_difficulty = self.values["expedition_difficulty"]
        self._refresh_route_controls(initial=True)

    def _private_server(self) -> None:
        side = self._card(714, 208, 468, 316, 8)
        self._section_title(side, "PRIVATE SERVER", 20)
        self.private_server = self._input(side, "", "Enter private server code", self.values["private_server"], 22, 47, 424)
        self._rule(side, 22, 102, 424)
        self._label(side, "NOTIFICATIONS", 22, 120, 260, 24, f"color: {TEXT}; font: 700 14px 'Bahnschrift';")
        self._label(side, "DISCORD WEBHOOK AND SESSION RESULTS", 22, 147, 320, 18, f"color: {WINE}; font: 700 9px 'Bahnschrift';")
        self.webhook = self._input(side, "WEBHOOK URL", "https://discord.com/api/webhooks/...", self.values["webhook"], 22, 181, 424)
        self.discord_id = self._input(side, "DISCORD USER ID", "Enter Discord User ID", self.values["discord_id"], 22, 249, 424)
        # Persist these independently as the user types so closing or updating cannot lose them.
        self.private_server.textChanged.connect(lambda _text: self._save_dashboard())
        self.webhook.textChanged.connect(lambda _text: self._save_dashboard())
        self.discord_id.textChanged.connect(lambda _text: self._save_dashboard())

    def _deployment(self) -> None:
        deploy = self._card(18, 540, 1164, 140, 8)
        self._label(deploy, "DEPLOYMENT", 22, 20, 150, 18, f"color: {WINE}; font: 700 9px 'Bahnschrift';")
        self._label(deploy, "Story test: Play > Story > selected map. Other modes: setup only.", 22, 48, 530, 20, f"color: {TEXT}; font: 700 10px 'Bahnschrift';")
        self._label(deploy, "Match and Discord settings save automatically.", 22, 73, 360, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")
        start = self._button(deploy, "OPEN RUNTIME" if self.mode_box.currentText() == "Story" else "SAVE SETUP", 578, 37, 214, True)
        self.start_button = start
        settings = self._button(deploy, "SETTINGS", 812, 37, 164)
        exit_button = self._button(deploy, "EXIT", 996, 37, 154)
        start.clicked.connect(self._start_macro)
        settings.clicked.connect(self._open_settings)
        exit_button.clicked.connect(self._exit_macro)
        self.status = self._label(deploy, "", 430, 104, 700, 18, f"color: {MUTED}; font: 8px 'Segoe UI';")

    def _combo(self, parent: QWidget, label: str, items: list[str], selected: str, x: int, y: int, width: int) -> QComboBox:
        title = self._label(parent, label, x, y, width, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
        box = QComboBox(parent)
        box.setGeometry(x, y + 22, width, 34)
        box.addItems(items)
        if selected in items:
            box.setCurrentText(selected)
        box.setStyleSheet(self._combo_style())
        box.title_label = title
        return box

    def _input(self, parent: QWidget, label: str, placeholder: str, value: str, x: int, y: int, width: int, keybind: bool = False) -> QLineEdit:
        if label:
            self._label(parent, label, x, y, width, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
            y += 22
        edit = KeybindEdit(parent) if keybind else QLineEdit(parent)
        edit.setGeometry(x, y, width, 38)
        edit.setText(value)
        edit.setPlaceholderText(placeholder)
        edit.setStyleSheet(self._input_style())
        edit.editingFinished.connect(self._save_dashboard)
        return edit

    def _button(self, parent: QWidget, text: str, x: int, y: int, width: int, primary: bool = False) -> QPushButton:
        button = QPushButton(text, parent)
        button.setGeometry(x, y, width, 66)
        button.setCursor(Qt.PointingHandCursor)
        if primary:
            primary_top = blend_color(WINE, "#FFFFFF", 0.28)
            primary_mid = blend_color(WINE, "#000000", 0.08)
            primary_bottom = blend_color(WINE, "#000000", 0.38)
            primary_hover = blend_color(WINE, "#FFFFFF", 0.36)
            button.setObjectName("primary")
            button.setStyleSheet(
                "QPushButton#primary { color: #ffffff; font: 700 11px 'Bahnschrift';"
                f" border: 1px solid {primary_top}; border-radius: 7px;"
                " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                f" stop:0 {primary_top}, stop:0.16 {primary_mid}, stop:0.58 {WINE}, stop:1 {primary_bottom}); }}"
                "QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                f" stop:0 {primary_hover}, stop:0.16 {primary_mid}, stop:0.58 {WINE}, stop:1 {primary_bottom}); }}"
                f"QPushButton#primary:pressed {{ background: {primary_bottom}; }}"
            )
        else:
            button.setStyleSheet(
                f"QPushButton {{ color: {TEXT}; font: 700 11px 'Bahnschrift'; background: {FIELD};"
                f" border: 1px solid {OUTLINE}; border-radius: 7px; }}"
                f"QPushButton:hover {{ background: {blend_color(FIELD, '#FFFFFF', 0.10)}; border-color: {blend_color(OUTLINE, '#FFFFFF', 0.20)}; }}"
                f"QPushButton:pressed {{ background: {blend_color(PANEL, '#000000', 0.20)}; }}"
            )
        return button

    def _rule(self, parent: QWidget, x: int, y: int, width: int) -> None:
        rule = QFrame(parent)
        rule.setGeometry(x, y, width, 1)
        rule.setStyleSheet(f"background: {WINE}; border: none;")

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ color: {TEXT}; background: {FIELD}; border: 1px solid {OUTLINE}; border-radius: 6px;"
            " padding: 0 36px 0 12px; font: 10px 'Segoe UI'; }"
            f"QComboBox:hover, QComboBox:focus {{ border-color: {blend_color(OUTLINE, '#FFFFFF', 0.20)}; background: {blend_color(FIELD, '#FFFFFF', 0.08)}; }}"
            "QComboBox::drop-down { border: none; background: transparent; width: 32px; }"
            f"QComboBox::down-arrow {{ image: url(\"{CHEVRON_PATH}\"); width: 12px; height: 8px; }}"
            f"QComboBox QAbstractItemView {{ color: {TEXT}; background: {FIELD}; border: 1px solid {WINE_DARK}; selection-background-color: {WINE_DARK}; }}"
        )

    def _input_style(self) -> str:
        return (
            f"QLineEdit {{ color: {TEXT}; background: {FIELD}; border: 1px solid {OUTLINE}; border-radius: 6px;"
            " padding: 0 12px; font: 10px 'Segoe UI'; }"
            f"QLineEdit:hover, QLineEdit:focus {{ border-color: {blend_color(OUTLINE, '#FFFFFF', 0.20)}; background: {blend_color(FIELD, '#FFFFFF', 0.08)}; }}"
            "QLineEdit::placeholder { color: #777176; }"
        )

    def _update_route(self) -> None:
        if not hasattr(self, "mode_box"):
            return
        route = f"Mode: {self.mode_box.currentText()}"
        if self.map_box.isVisible():
            route += f" | Map: {self.map_box.currentText()}"
        if self.act_box.isVisible():
            route += f" | Act: {self.act_box.currentText()}"
        if self.difficulty_box.isEnabled():
            route += f" | {self.difficulty_box.currentText()}"
        self.route_value.setText(route)

    @staticmethod
    def _set_combo_items(box: QComboBox, items: list[str], selected: str) -> None:
        box.blockSignals(True)
        box.clear()
        box.addItems(items)
        box.setCurrentText(selected if selected in items else items[0])
        box.blockSignals(False)

    @staticmethod
    def _set_combo_visible(box: QComboBox, visible: bool) -> None:
        box.setVisible(visible)
        box.title_label.setVisible(visible)

    def _mode_changed(self, _mode: str) -> None:
        self._refresh_route_controls()
        self._save_dashboard()
        if hasattr(self, "start_button"):
            self.start_button.setText("OPEN RUNTIME" if _mode == "Story" else "SAVE SETUP")

    def _act_changed(self, _act: str) -> None:
        if self.mode_box.currentText() == "Story":
            self._refresh_route_controls()
        self._save_dashboard()

    def _refresh_route_controls(self, initial: bool = False) -> None:
        mode = self.mode_box.currentText()
        previous_map = self.values["map"] if initial else self.map_box.currentText()
        previous_act = self.values["act"] if initial else self.act_box.currentText()
        previous_difficulty = self.values["difficulty"] if initial else self.difficulty_box.currentText()
        maps = MODE_MAPS[mode]
        acts = MODE_ACTS[mode]
        self._set_combo_items(self.map_box, maps, previous_map)
        self._set_combo_visible(self.map_box, True)
        self._set_combo_items(self.act_box, acts, previous_act)
        self._set_combo_visible(self.act_box, mode in {"Story", "Raid"})

        if mode == "Story":
            difficulties = ["Hard"] if self.act_box.currentText() in {"Infinite", "Mastery"} else ["Normal", "Hard"]
            self._set_combo_items(self.difficulty_box, difficulties, previous_difficulty)
            self.difficulty_box.setEnabled(len(difficulties) > 1)
            self._set_combo_visible(self.difficulty_box, True)
        elif mode == "Expeditions":
            self._set_combo_items(self.difficulty_box, ["1", "2", "3"], previous_difficulty)
            self.difficulty_box.setEnabled(True)
            self._set_combo_visible(self.difficulty_box, True)
        else:
            self._set_combo_items(self.difficulty_box, ["Not applicable"], "Not applicable")
            self.difficulty_box.setEnabled(False)
            self._set_combo_visible(self.difficulty_box, False)
        self._update_route()

    def _save_dashboard(self) -> None:
        if not hasattr(self, "mode_box"):
            return
        mode = self.mode_box.currentText()
        if mode == "Expeditions":
            self.last_expedition_difficulty = self.difficulty_box.currentText()
        update_config(
            "Dashboard",
            {
                "Mode": mode,
                "Map": self.map_box.currentText(),
                "Act": self.act_box.currentText(),
                "Difficulty": self.difficulty_box.currentText() if mode == "Story" else "-",
                "ExpeditionDifficulty": self.last_expedition_difficulty,
                "TowerType": self.map_box.currentText() if mode == "Tower" else self.values["tower_type"],
            },
        )
        update_config("Discord", {"Webhook": self.webhook.text(), "UserID": self.discord_id.text()})
        update_config("Roblox", {"PrivateServerLink": self.private_server.text()})
        self._update_route()

    def _start_macro(self) -> None:
        self._save_dashboard()
        if self.mode_box.currentText() != "Story":
            self._set_status("Setup saved. This mode's automation is not connected yet.")
            return
        self.runtime_window = RuntimeWindow()
        self.runtime_window.setup_dashboard = self
        self.runtime_window.show()
        self.hide()

    def _open_unit_setup(self) -> None:
        if not isinstance(self, RuntimeWindow):
            return
        if self.worker is not None and self.worker.isRunning():
            self.log.appendPlainText("Stop the macro before editing unit indexes.")
            return
        first = (self.unit_page - 1) * 6 + 1
        if UnitSetupDialog(self.values, self, first, min(6, 105 - first)).exec() == QDialog.Accepted:
            self.unit_indexes = load_unit_indexes(self.values, 104)
            self._render_unit_manager_page()

    def _open_settings(self) -> None:
        self._save_dashboard()
        if getattr(self, "settings_window", None) and self.settings_window.isVisible():
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return
        if not acquire_single_instance("settings"):
            return
        self.settings_window = SettingsWindow(self)
        self.settings_window.show()

    def replace_with_fresh_dashboard(self) -> None:
        global ACTIVE_DASHBOARD
        replacement = DashboardWindow()
        ACTIVE_DASHBOARD = replacement
        replacement.show()
        self.close()

    def _exit_macro(self) -> None:
        send_command("Exit")
        self.close()

    def _set_status(self, message: str) -> None:
        self.status.setText(message)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self.drag_origin and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_origin)

    def mouseReleaseEvent(self, event) -> None:
        self.drag_origin = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(blend_color(PANEL, "#000000", 0.45)))
        glow = QRadialGradient(100, 690, 560)
        glow_near = QColor(WINE)
        glow_near.setAlpha(170)
        glow_mid = QColor(WINE_DARK)
        glow_mid.setAlpha(100)
        glow_far = QColor(PANEL)
        glow_far.setAlpha(0)
        glow.setColorAt(0.0, glow_near)
        glow.setColorAt(0.5, glow_mid)
        glow.setColorAt(1.0, glow_far)
        painter.fillRect(self.rect(), glow)
        painter.setPen(QColor(WINE_DARK))
        for offset in range(-720, 1220, 24):
            painter.drawLine(offset, 720, offset + 300, 0)
        painter.end()


class SettingsWindow(DashboardWindow):
    def __init__(self, dashboard: DashboardWindow | None = None) -> None:
        self.dashboard = dashboard
        super().__init__()

    def closeEvent(self, event) -> None:
        release_single_instance("settings")
        super().closeEvent(event)

    def _build(self) -> None:
        header = self._card(18, 16, 1164, 108, 9)
        logo_card = self._card(20, 20, 82, 70, 7)
        logo_card.setParent(header)
        logo_card.move(20, 20)
        logo = QLabel(logo_card)
        logo.setGeometry(12, 8, 58, 54)
        logo.setPixmap(QPixmap(str(ASSETS / "sm-logo.png")))
        logo.setScaledContents(True)
        self._label(header, "SCATTERMACRO", 124, 28, 180, 16, f"color: {WINE}; font: 700 8px 'Bahnschrift';")
        self._label(header, "SETTINGS", 124, 45, 350, 38, f"color: {TEXT}; font: 700 26px 'Bahnschrift';")
        self._label(header, "Personalize controls, behavior, and notifications.", 126, 80, 480, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")
        self._label(header, "\u25cf", 940, 34, 16, 18, "color: #47e887; font: 700 14px 'Segoe UI';")
        self._label(header, "SETUP MODE", 960, 35, 200, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
        self._label(header, "Settings are saved locally", 940, 61, 220, 18, f"color: {MUTED}; font: 8px 'Segoe UI';")

        appearance = self._card(18, 140, 680, 274, 8)
        self._section_title(appearance, "APPEARANCE", 20)
        self._label(appearance, "Choose the colors used across ScatterMacro.", 22, 58, 400, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")
        self._label(appearance, "PRIMARY", 36, 96, 100, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
        self.primary_swatch = self._swatch(appearance, 36, 120, self.values["primary_color"])
        self.primary_color = self._input(appearance, "", "#080809", self.values["primary_color"], 82, 120, 134)
        apply_primary = self._small_button(appearance, "APPLY", 232, 120, 82)
        self._label(appearance, "ACCENT", 36, 171, 100, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
        self.accent_swatch = self._swatch(appearance, 36, 195, self.values["accent_color"])
        self.accent_color = self._input(appearance, "", "#5A0F1B", self.values["accent_color"], 82, 195, 134)
        apply_accent = self._small_button(appearance, "APPLY", 232, 195, 82)
        apply_primary.clicked.connect(self._apply_theme_colors)
        apply_accent.clicked.connect(self._apply_theme_colors)
        reset_theme = self._small_button(appearance, "RESET THEME", 368, 195, 152)
        reset_theme.clicked.connect(self._reset_and_save_theme)

        runtime = self._card(714, 140, 468, 274, 8)
        self._section_title(runtime, "RUNTIME", 20)
        self._label(runtime, "Window behavior and Roblox safety limits.", 22, 58, 350, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")
        self.minimize_to_tray = self._toggle(runtime, "Minimize to tray when closing", 22, 96, self.values["minimize_to_tray"] == "1")
        self.runtime_on_top = self._toggle(runtime, "Keep runtime dashboard on top", 22, 138, self.values["runtime_on_top"] == "1")
        self._label(runtime, "ROBLOX NOT FOUND TIMEOUT", 22, 186, 230, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
        self.roblox_timeout = self._input(runtime, "", "seconds", self.values["roblox_timeout"], 22, 208, 92)
        self._label(runtime, "seconds", 126, 218, 80, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")

        hotkeys = self._card(18, 430, 416, 250, 8)
        self._section_title(hotkeys, "HOTKEYS", 20)
        self._label(hotkeys, "Runtime controls while the dashboard is open.", 22, 58, 350, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")
        self.start_key = self._input(hotkeys, "START KEY", "F1", self.values["start_key"], 22, 94, 154, keybind=True)
        set_start = self._small_button(hotkeys, "SET", 194, 116, 70)
        self.stop_key = self._input(hotkeys, "STOP KEY", "F2", self.values["stop_key"], 22, 165, 154, keybind=True)
        set_stop = self._small_button(hotkeys, "SET", 194, 187, 70)
        set_start.clicked.connect(self.start_key.setFocus)
        set_stop.clicked.connect(self.stop_key.setFocus)

        notifications = self._card(450, 430, 354, 250, 8)
        self._section_title(notifications, "DISCORD NOTIFICATIONS", 20)
        self._label(notifications, "Choose which Discord pings are sent.", 22, 58, 300, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")
        self.ping_victory = self._toggle(notifications, "Victory", 22, 94, self.values["ping_victory"] == "1")
        self.ping_defeat = self._toggle(notifications, "Defeat", 180, 94, self.values["ping_defeat"] == "1")
        self.ping_error = self._toggle(notifications, "Errors", 22, 136, self.values["ping_error"] == "1")

        updates = self._card(820, 430, 362, 250, 8)
        self._section_title(updates, "UPDATES", 20)
        self._label(updates, "Updates are managed by the launcher.", 22, 62, 300, 20, f"color: {TEXT}; font: 700 10px 'Bahnschrift';")
        self._label(updates, "Check Updates in ScatterMacro to install new versions.", 22, 92, 320, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")
        self.automatic_check_toggle = self._toggle(updates, "Automatic update checks", 22, 126, self.values["automatic_check"] == "1")
        check_updates = self._small_button(updates, "CHECK FOR UPDATES", 22, 176, 188)
        check_updates.setEnabled(False)
        save = self._button(updates, "SAVE SETTINGS", 222, 162, 118, True)
        save.setFixedHeight(50)
        save.clicked.connect(self._save_settings)

    def _save_settings(self) -> None:
        self._apply_theme_colors()
        update_config(
            "Settings",
            {
                "PrimaryColor": self.primary_color.text() or "#080809",
                "AccentColor": self.accent_color.text() or "#5A0F1B",
                "StartKey": self.start_key.text() or "F1",
                "StopKey": self.stop_key.text() or "F2",
                "MinimizeToTray": "1" if self.minimize_to_tray.isChecked() else "0",
                "RuntimeAlwaysOnTop": "1" if self.runtime_on_top.isChecked() else "0",
                "RobloxTimeoutSeconds": self.roblox_timeout.text() or "90",
            },
        )
        update_config(
            "Notifications",
            {
                "Victory": "1" if self.ping_victory.isChecked() else "0",
                "Defeat": "1" if self.ping_defeat.isChecked() else "0",
                "Error": "1" if self.ping_error.isChecked() else "0",
            },
        )
        update_config("Updates", {"AutomaticCheck": "1" if self.automatic_check_toggle.isChecked() else "0"})
        send_command("SettingsSaved")
        if self.dashboard:
            self.dashboard.replace_with_fresh_dashboard()
        self.close()

    def _apply_theme_colors(self) -> None:
        primary = normalize_hex_color(self.primary_color.text(), "#080809")
        accent = normalize_hex_color(self.accent_color.text(), "#5A0F1B")
        self.primary_color.setText(primary)
        self.accent_color.setText(accent)
        self.primary_swatch.setStyleSheet(f"background: {primary}; border: 1px solid #686167; border-radius: 5px;")
        self.accent_swatch.setStyleSheet(f"background: {accent}; border: 1px solid #686167; border-radius: 5px;")
        update_config("Settings", {"PrimaryColor": primary, "AccentColor": accent})
        apply_theme_palette(primary, accent)

    def _reset_and_save_theme(self) -> None:
        self.primary_color.setText("#080809")
        self.accent_color.setText("#5A0F1B")
        self._apply_theme_colors()

    def _swatch(self, parent: QWidget, x: int, y: int, color: str) -> QFrame:
        swatch = QFrame(parent)
        swatch.setGeometry(x, y, 30, 30)
        swatch.setStyleSheet(f"background: {color}; border: 1px solid #686167; border-radius: 5px;")
        return swatch

    def _small_button(self, parent: QWidget, text: str, x: int, y: int, width: int) -> QPushButton:
        button = QPushButton(text, parent)
        button.setGeometry(x, y, width, 34)
        button.setStyleSheet(
            f"QPushButton {{ color: {TEXT}; background: {FIELD}; border: 1px solid {OUTLINE}; border-radius: 6px; font: 700 9px 'Bahnschrift'; }}"
            f"QPushButton:hover {{ background: {blend_color(FIELD, '#FFFFFF', 0.10)}; border-color: {blend_color(OUTLINE, '#FFFFFF', 0.20)}; }}"
        )
        return button

    def _toggle(self, parent: QWidget, text: str, x: int, y: int, checked: bool) -> QPushButton:
        toggle = QPushButton(text, parent)
        toggle.setGeometry(x, y, 250, 30)
        toggle.setCheckable(True)
        toggle.setChecked(checked)
        toggle.setStyleSheet(
            f"QPushButton {{ color: {MUTED}; text-align: left; padding-left: 39px; background: transparent; border: none; font: 9px 'Segoe UI'; }}"
            "QPushButton::indicator { width: 0; height: 0; }"
            "QPushButton:checked { color: #f3eff0; }"
        )
        dot = QLabel(toggle)
        dot.setGeometry(0, 5, 24, 20)
        dot.setAttribute(Qt.WA_TransparentForMouseEvents)
        dot.setStyleSheet("background: #2b2529; border: 1px solid #5a5156; border-radius: 10px;")
        knob = QLabel(toggle)
        knob.setAttribute(Qt.WA_TransparentForMouseEvents)
        knob.setObjectName("knob")
        def update_knob(is_checked: bool) -> None:
            knob.setGeometry(7 if is_checked else 3, 8, 14, 14)
            knob.setStyleSheet(("background: #47e887;" if is_checked else "background: #847b80;") + " border-radius: 7px;")

        toggle.toggled.connect(update_knob)
        update_knob(checked)
        return toggle


class RuntimeWindow(DashboardWindow):
    VIEWPORT_X = 305
    VIEWPORT_Y = 60
    VIEWPORT_W = 1060
    VIEWPORT_H = 860

    def __init__(self) -> None:
        super().__init__()
        # This must match the established live Roblox viewport exactly.
        self.setFixedSize(1835, 950)
        # The Roblox client can appear after the first Qt show event. Retry
        # alignment briefly so dragging the runtime window is never required.
        self._embed_attempts = 0
        self._embed_successes = 0
        self._embed_timer = QTimer(self)
        self._embed_timer.setInterval(160)
        self._embed_timer.timeout.connect(self._align_on_launch)

    def _small_button(self, parent: QWidget, text: str, x: int, y: int, width: int) -> QPushButton:
        button = QPushButton(text, parent)
        button.setGeometry(x, y, width, 34)
        button.setStyleSheet(
            f"QPushButton {{ color: {TEXT}; background: {FIELD}; border: 1px solid {OUTLINE}; border-radius: 6px; font: 700 9px 'Bahnschrift'; }}"
            f"QPushButton:hover {{ background: {blend_color(FIELD, '#FFFFFF', 0.10)}; border-color: {blend_color(OUTLINE, '#FFFFFF', 0.20)}; }}"
        )
        return button

    def _build(self) -> None:
        stats_panel = self._card(18, 16, 270, 378, 8)
        self._section_title(stats_panel, "SESSION STATS", 20)
        self._label(stats_panel, "Current macro session", 22, 58, 226, 18,
                    f"color: {MUTED}; font: 9px 'Segoe UI';")
        stats = [("RUNS", "0"), ("AVG RUN", "--:--:--"),
                 ("CURRENT RUN", "WAITING")]
        self.stat_values: dict[str, QLabel] = {}
        for index, (label, value) in enumerate(stats):
            x = 22 + (index % 2) * 116
            y = 91 + (index // 2) * 98
            tile = self._card(0, 0, 110, 86, 6)
            tile.setParent(stats_panel)
            tile.move(x, y)
            self._label(tile, label, 9, 12, 94, 18,
                        f"color: {MUTED}; font: 700 8px 'Bahnschrift';")
            self.stat_values[label] = self._label(
                tile, value, 9, 40, 95, 21,
                f"color: {TEXT}; font: 700 11px 'Bahnschrift';")
        self.runtime_status = self._label(
            stats_panel, "●  READY", 22, 301, 226, 22,
            "color: #47e887; font: 700 10px 'Bahnschrift';")
        self.session_value = self._label(
            stats_panel, "Session  --:--:--", 22, 329, 226, 18,
            f"color: {MUTED}; font: 9px 'Segoe UI';")

        action = self._card(18, 406, 270, 528, 8)
        self._section_title(action, "ACTION OUTPUT", 20)
        self._label(action, "Live macro activity", 22, 58, 200, 18,
                    f"color: {MUTED}; font: 9px 'Segoe UI';")
        self.log = QPlainTextEdit(action)
        self.log.setGeometry(22, 88, 226, 303)
        self.log.setReadOnly(True)
        self.log.setPlainText("Runtime is ready.\n\nWaiting for macro activity...")
        self.log.setStyleSheet(
            f"background: {blend_color(PANEL, '#000000', 0.45)}; "
            f"border: 1px solid {OUTLINE}; border-radius: 6px; "
            f"color: {TEXT}; padding: 8px; font: 9px 'Consolas';")
        self.worker = None
        self.return_pending = False
        self._label(action, "F1: START   |   F2: STOP", 22, 409, 226, 18, f"color: {TEXT}; font: 700 10px 'Bahnschrift';")
        # The F2 emergency stop remains active via RuntimeHotkeys; no extra button.
        return_button = self._small_button(action, "RETURN TO DASHBOARD", 22, 449, 226)
        return_button.clicked.connect(self._return_to_dashboard)
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._refresh_log)
        # Worker signals own Action Output; stale file logs must not overwrite it.
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self._refresh_state)
        self.state_timer.start(500)

        live = self._card(300, 16, 1075, 918, 8)
        viewport = QFrame(live)
        viewport.setGeometry(5, 44, self.VIEWPORT_W, self.VIEWPORT_H)
        viewport.setStyleSheet(f"background: transparent; border: 1px solid {WINE_DARK}; border-radius: 8px;")
        # Keep the Roblox client aligned with this transparent viewport.
        self.viewport_rect = QRect(self.VIEWPORT_X, self.VIEWPORT_Y, self.VIEWPORT_W, self.VIEWPORT_H)
        manager = self._card(1390, 16, 427, 918, 8)
        self.unit_manager = manager
        self.unit_page = 1
        self.unit_indexes = load_unit_indexes(self.values, 104)
        self.unit_config_path = active_unit_config(self.values)
        from ui.unit_manager import UnitManager
        self.index_editor = UnitManager(self.unit_indexes, self._save_runtime_index,
                                       lambda: self.worker is not None and self.worker.isRunning(),
                                       self.log.appendPlainText, manager)
        self.index_editor.setGeometry(12, 12, 403, 894)

    def _save_runtime_index(self, index, entry):
        parser = configparser.ConfigParser(interpolation=None)
        read_ini(parser, self.unit_config_path)
        if not parser.has_section("UnitIndexes"):
            parser.add_section("UnitIndexes")
        from python_macro.deployment import requested_wave
        requested_wave(entry.get("place_at_wave", ""))
        for key, suffix in (("unit", "Unit"), ("priority", "Priority"), ("upgrade", "Upgrade"),
                            ("auto_upgrade", "AutoUpgrade"), ("x", "X"), ("y", "Y"),
                            ("place_at_wave", "PlaceAtWave")):
            parser.set("UnitIndexes", f"Index{index + 1}{suffix}", entry.get(key, ""))
        write_ini(parser, self.unit_config_path)

    def _render_unit_manager_page(self) -> None:
        """Redraw only the Unit Manager so page controls stay responsive."""
        for child in self.unit_manager.findChildren(QWidget):
            child.deleteLater()
        first_index = (self.unit_page - 1) * 6
        indexes = self.unit_indexes[first_index:first_index + 6]
        selected = indexes[0] if indexes else {"unit": "0", "priority": "First", "upgrade": "0", "auto_upgrade": "0", "x": "", "y": ""}
        self._section_title(self.unit_manager, "UNIT MANAGER", 20)
        self._label(self.unit_manager, "Configure unit indexes.", 22, 58, 200, 18, f"color: {MUTED}; font: 9px 'Segoe UI';")
        self._label(self.unit_manager, f"SELECTED: INDEX {first_index + 1}", 22, 92, 220, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
        unit_options = [str(i) for i in range(7)]
        self._combo(self.unit_manager, "UNIT", unit_options, selected["unit"], 22, 122, 175)
        self._combo(self.unit_manager, "TARGET", ["First", "Last", "Closest", "Strongest", "Boss", "Weakest", "Shielded", "Fastest"], selected["priority"], 218, 122, 175)
        self._combo(self.unit_manager, "UPGRADE", [str(level) for level in range(16)], selected["upgrade"], 22, 196, 175)
        self._combo(self.unit_manager, "AUTO UPGRADE", [str(level) for level in range(7)], selected["auto_upgrade"], 218, 196, 175)
        self._label(self.unit_manager, "INDEXES", 22, 276, 120, 18, f"color: {TEXT}; font: 700 9px 'Bahnschrift';")
        edit = self._small_button(self.unit_manager, "EDIT INDEXES", 22, 666, 371)
        edit.clicked.connect(self._open_unit_setup)
        for offset, data in enumerate(indexes):
            x = 22 + (offset % 2) * 196
            y = 304 + (offset // 2) * 112
            card = self._card(x, y, 186, 100, 6)
            card.setParent(self.unit_manager)
            card.move(x, y)
            index = first_index + offset + 1
            self._label(card, f"INDEX {index}", 10, 10, 160, 15, f"color: {TEXT}; font: 700 8px 'Bahnschrift';")
            self._label(card, f"UNIT: {data['unit']}", 10, 29, 166, 12, f"color: {MUTED}; font: 7px 'Segoe UI';")
            self._label(card, f"TARGET: {data['priority']}", 10, 45, 166, 12, f"color: {MUTED}; font: 7px 'Segoe UI';")
            self._label(card, f"UPG: {data['upgrade']}  AUTO: {data['auto_upgrade']}", 10, 62, 166, 12, "color: #47e887; font: 700 7px 'Bahnschrift';" if data["unit"] not in ("None", "0") else f"color: {MUTED}; font: 7px 'Segoe UI';")
            self._label(card, f"POSITION: {data['x']},{data['y']}" if data["x"] else "POSITION: --", 10, 78, 166, 12, f"color: {MUTED}; font: 7px 'Segoe UI';")
        previous = self._small_button(self.unit_manager, "PREVIOUS", 22, 768, 175)
        next_button = self._small_button(self.unit_manager, "NEXT", 218, 768, 175)
        previous.setEnabled(self.unit_page > 1)
        next_button.setEnabled(self.unit_page < 18)
        previous.clicked.connect(lambda: self._change_unit_page(-1))
        next_button.clicked.connect(lambda: self._change_unit_page(1))

    def _change_unit_page(self, direction: int) -> None:
        self.unit_page = max(1, min(18, self.unit_page + direction))
        self._render_unit_manager_page()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        from python_macro.hotkeys import RuntimeHotkeys
        if not hasattr(self, "hotkeys"):
            self.hotkeys = RuntimeHotkeys(int(self.winId()))
        try:
            self.hotkeys.register()
        except RuntimeError as exc:
            self.log.appendPlainText(str(exc))
        QTimer.singleShot(0, self._start_auto_embed)

    def _start_auto_embed(self) -> None:
        if sys.platform != "win32" or not self.isVisible():
            return
        self._embed_attempts = 0
        self._embed_successes = 0
        self._embed_timer.start()
        self._align_on_launch()

    def _align_on_launch(self) -> None:
        if not self.isVisible():
            self._embed_timer.stop()
            return
        aligned = self._publish_viewport()
        self._embed_attempts += 1
        if aligned:
            self._embed_successes += 1
        # Repeated successful alignment accommodates Roblox/Windows resizing
        # itself immediately after runtime opens. No indefinite polling.
        if self._embed_attempts >= 40 or self._embed_successes >= 8:
            self._embed_timer.stop()

    def hideEvent(self, event) -> None:
        self._embed_timer.stop()
        if hasattr(self, "hotkeys"):
            self.hotkeys.close()
        self._stop_story()
        super().hideEvent(event)

    def nativeEvent(self, event_type, message):
        from ctypes import wintypes
        from python_macro.hotkeys import RuntimeHotkeys
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and self.isVisible() and not self.return_pending:
                if msg.wParam == RuntimeHotkeys.START:
                    self._start_story()
                    return True, 0
                if msg.wParam == RuntimeHotkeys.STOP:
                    self._stop_story()
                    return True, 0
        return super().nativeEvent(event_type, message)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._publish_viewport()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._publish_viewport()

    def _publish_viewport(self) -> None:
        if not hasattr(self, "viewport_rect"):
            return
        shape = QRegion(self.rect()).subtracted(QRegion(self.viewport_rect))
        self.setMask(shape)
        write_runtime_status(int(self.winId()), self.viewport_rect, self)
        if not self.isVisible():
            return False
        return self._align_roblox()

    def _align_roblox(self):
        from ctypes import wintypes
        from python_macro.capture import roblox_windows
        windows = roblox_windows()
        if len(windows) != 1:
            return False
        hwnd = windows[0][0]
        user = ctypes.windll.user32
        user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]
        user.IsIconic.argtypes = [wintypes.HWND]
        if user.IsIconic(hwnd):
            # The game must be restored before its client can fill the viewport.
            user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user.ShowWindow(hwnd, 9)  # SW_RESTORE
            return False
        outer, client, origin = wintypes.RECT(), wintypes.RECT(), wintypes.POINT()
        if not (user.GetWindowRect(hwnd, ctypes.byref(outer)) and
                user.GetClientRect(hwnd, ctypes.byref(client)) and
                user.ClientToScreen(hwnd, ctypes.byref(origin))):
            return False
        ratio = self.devicePixelRatioF()
        # Qt global coordinates can be logical on scaled Windows displays.
        runtime_origin = wintypes.POINT()
        if not user.ClientToScreen(int(self.winId()), ctypes.byref(runtime_origin)):
            return False
        x = runtime_origin.x + round(self.viewport_rect.x() * ratio)
        y = runtime_origin.y + round(self.viewport_rect.y() * ratio)
        success = user.MoveWindow(
            hwnd, x - (origin.x - outer.left), y - (origin.y - outer.top),
            round(self.viewport_rect.width() * ratio) + outer.right - outer.left - client.right,
            round(self.viewport_rect.height() * ratio) + outer.bottom - outer.top - client.bottom, True,
        )
        return bool(success)

    def _refresh_log(self) -> None:
        if not LOG_PATH.exists():
            return
        try:
            text = LOG_PATH.read_text(encoding="utf-8")
        except OSError:
            return
        if text != self.log.toPlainText():
            self.log.setPlainText(text)
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _refresh_state(self) -> None:
        # No legacy state-file polling in the Python-only rebuild.
        return

    def _return_to_dashboard(self) -> None:
        self.return_pending = True
        if self.worker is not None and self.worker.isRunning():
            self._stop_story()
            return
        self._restore_setup()
        self.close()

    def _start_story(self) -> None:
        if self.values["mode"] != "Story":
            self.log.appendPlainText("Only Story navigation is available.")
            return
        if self.return_pending or (self.worker is not None and self.worker.isRunning()):
            return
        from ui.story_navigation import StoryWorker
        self._align_roblox()
        self.worker = StoryWorker(self.values["map"], self, act_name=self.values["act"],
                                  difficulty=self.values["difficulty"])
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.finished.connect(self._story_finished)
        self.runtime_status.setText("RUNNING")
        self.worker.start()

    def _stop_story(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop.set()
            self.runtime_status.setText("STOPPING")

    def _story_finished(self) -> None:
        self.runtime_status.setText("READY")
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        if self.return_pending:
            self._restore_setup()
            self.close()

    def _restore_setup(self) -> None:
        if not hasattr(self, "setup_dashboard"):
            self.setup_dashboard = DashboardWindow()
        self.setup_dashboard.show()

    def closeEvent(self, event) -> None:
        if hasattr(self, "hotkeys"):
            self.hotkeys.close()
        if self.worker is not None and self.worker.isRunning():
            self.return_pending = True
            self._stop_story()
            event.ignore()
            return
        self._restore_setup()
        super().closeEvent(event)


def main() -> int:
    global CONFIG_PATH, COMMAND_PATH, STATUS_PATH, LOG_PATH
    if "--config-dir" in sys.argv:
        index = sys.argv.index("--config-dir")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--config-dir requires a folder")
        CONFIG_PATH = Path(sys.argv[index + 1]).resolve() / "dashboard_config.ini"
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists():
            update_config("Dashboard", {"Mode": "Expeditions", "Map": "School Grounds", "ExpeditionDifficulty": "1"})
    if "--config" in sys.argv:
        index = sys.argv.index("--config")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--config requires a path")
        CONFIG_PATH = Path(sys.argv[index + 1]).resolve()
    if "--command" in sys.argv:
        index = sys.argv.index("--command")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--command requires a path")
        COMMAND_PATH = Path(sys.argv[index + 1]).resolve()
    else:
        COMMAND_PATH = CONFIG_PATH.with_name("python_ui_command.ini")
    if "--status" in sys.argv:
        index = sys.argv.index("--status")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--status requires a path")
        STATUS_PATH = Path(sys.argv[index + 1]).resolve()
    else:
        STATUS_PATH = CONFIG_PATH.with_name("python_ui_runtime.ini")
    if "--log" in sys.argv:
        index = sys.argv.index("--log")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--log requires a path")
        LOG_PATH = Path(sys.argv[index + 1]).resolve()
    else:
        LOG_PATH = CONFIG_PATH.with_name("python_ui_runtime.log")
    app = QApplication(sys.argv)
    for font in ("segoeui.ttf", "segoeuib.ttf", "bahnschrift.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font))
    app.setFont(QFont("Segoe UI", 10))
    # Standalone Python dashboard. Mode runners are intentionally unavailable
    # until they are rebuilt; never silently fall back to a legacy executable.
    screen = "dashboard"
    if "--screen" in sys.argv:
        index = sys.argv.index("--screen")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--screen requires dashboard, settings, or runtime")
        screen = sys.argv[index + 1].lower()
    if not acquire_single_instance(screen):
        return 0
    window_type = {
        "dashboard": DashboardWindow,
        "settings": SettingsWindow,
        "runtime": RuntimeWindow,
    }.get(screen)
    if not window_type:
        raise SystemExit("--screen requires dashboard, settings, or runtime")
    saved_theme = read_dashboard_values()
    apply_theme_palette(saved_theme["primary_color"], saved_theme["accent_color"])
    window = window_type()
    render_path: Path | None = None
    unit_manager_render = False
    if "--render-preview" in sys.argv:
        index = sys.argv.index("--render-preview")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--render-preview requires an output path")
        render_path = Path(sys.argv[index + 1]).resolve()
    if "--render-unit-manager" in sys.argv:
        unit_manager_render = True
    if "--preview" in sys.argv:
        window.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    window.show()
    if render_path:
        def capture_preview() -> None:
            render_path.parent.mkdir(parents=True, exist_ok=True)
            if unit_manager_render and isinstance(window, RuntimeWindow):
                window.unit_manager.grab().save(str(render_path))
            else:
                window.grab().save(str(render_path))
            app.quit()

        QTimer.singleShot(250, capture_preview)
    if "--preview" in sys.argv:
        QTimer.singleShot(30000, app.quit)
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        if getattr(sys, "frozen", False):
            import traceback

            Path(sys.executable).with_name("ScatterMacroUI-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
