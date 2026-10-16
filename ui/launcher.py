"""Standalone library and read-only capture diagnostics for the Python rebuild."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

ROOT = Path(__file__).resolve().parents[1]
STYLE = """
QWidget {background:#080809;color:#f3eff0;font-family:'Segoe UI';font-size:13px;}
QFrame#header {background:#100c0e;border-bottom:1px solid #642238;}
QLabel {background:transparent;}
QLabel#muted {color:#b2a4aa;}
QLabel#eyebrow {color:#d58a9c;font-size:10px;letter-spacing:2px;font-weight:700;}
QLabel#title {font-size:32px;font-weight:700;}
QFrame#card {background:#100d0f;border:1px solid #39212a;border-radius:14px;}
QFrame#hero {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #380f1b,stop:0.6 #170d12,stop:1 #080809);border:1px solid #642238;border-radius:16px;}
QPushButton {background:#191115;border:1px solid #45232e;border-radius:8px;padding:11px 17px;font-weight:600;}
QPushButton:hover {background:#32131f;border-color:#8c334d;}
QPushButton:checked {background:#4c101f;border:1px solid #923550;color:#fff0f4;}
QPushButton#primary {background:#7e1726;color:#fff4f6;border:1px solid #a74359;}
QPushButton#primary:hover {background:#991e35;}
QPushButton:disabled {color:#8f8187;background:#1b1518;border-color:#34252b;}
QLineEdit,QComboBox {background:#100d0f;border:1px solid #42232e;border-radius:8px;padding:10px;}
QLineEdit:focus,QComboBox:focus {border-color:#a74359;}
QScrollArea {border:0;}
"""


def label(text, name=None):
    item = QLabel(text)
    item.setWordWrap(True)
    if name:
        item.setObjectName(name)
    return item


class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ScatterMacro | Library")
        self.setWindowIcon(QIcon(str(ROOT / "assets/scattermacro.ico")))
        self.resize(1180, 780)
        self.setMinimumSize(850, 620)
        self.dashboard = None
        outer = QWidget()
        self.setCentralWidget(outer)
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        nav = QHBoxLayout(header)
        nav.setContentsMargins(30, 20, 30, 20)
        nav.addWidget(label("SCATTER / MACRO", "eyebrow"))
        nav.addStretch()
        self.nav = {}
        for name in ("Home", "Installed", "Updates", "Diagnostics"):
            button = QPushButton(name)
            button.setCheckable(True)
            button.clicked.connect(lambda _, page=name: self.show_page(page))
            nav.addWidget(button)
            self.nav[name] = button
        layout.addWidget(header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(34, 12, 34, 18)
        footer.addWidget(label("LOCAL WORKSPACE  /  PYTHON EDITION", "eyebrow"))
        footer.addStretch()
        folder = QPushButton("Project folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT))))
        footer.addWidget(folder)
        layout.addLayout(footer)
        self.show_page("Home")

    def show_page(self, page):
        for name, button in self.nav.items():
            button.setChecked(name == page)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(34, 30, 34, 30)
        column.setSpacing(18)
        column.addWidget(label("YOUR WORKSPACE", "eyebrow"))
        column.addWidget(label("Choose your next session." if page == "Home" else page, "title"))
        if page == "Home":
            column.addWidget(label("Your games, configurations, and tools. One place to begin.", "muted"))
            search = QLineEdit()
            search.setPlaceholderText("Search macros by name or game")
            column.addWidget(search)
            hero = QFrame()
            hero.setObjectName("hero")
            hero_layout = QHBoxLayout(hero)
            hero_layout.setContentsMargins(28, 28, 28, 28)
            copy = QVBoxLayout()
            copy.addWidget(label("01 / ROBLOX", "eyebrow"))
            copy.addWidget(label("Anime Expeditions", "title"))
            copy.addWidget(label("Your saved setup, ready for the next chapter.\nAutomation is being rebuilt in Python.", "muted"))
            copy.addSpacing(22)
            preview = QPushButton("Preview dashboard")
            preview.setObjectName("primary")
            preview.clicked.connect(self.open_dashboard)
            copy.addWidget(preview, alignment=Qt.AlignLeft)
            art = QLabel()
            art.setPixmap(QPixmap(str(ROOT / "assets/anime-expeditions.png")).scaled(400, 225, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            art.setAlignment(Qt.AlignCenter)
            art.setMinimumWidth(0)
            art.setScaledContents(False)
            art.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            hero_layout.addWidget(art, 2)
            hero_layout.addLayout(copy, 3)
            install = QPushButton("Install available after release")
            install.setEnabled(False)
            copy.addWidget(install, alignment=Qt.AlignLeft)
            column.addWidget(hero)
            tools = QHBoxLayout()
            tools.addWidget(label("CHECK BEFORE YOU START\nVerify the Roblox window in Diagnostics.", "muted"), 1)
            diagnostics = QPushButton("Open Diagnostics")
            diagnostics.clicked.connect(lambda: self.show_page("Diagnostics"))
            tools.addWidget(diagnostics)
            column.addLayout(tools)
            empty = label("No matching macros.", "muted")
            empty.hide()
            column.addWidget(empty)
            def filter_cards(text):
                match = text.lower().strip() in "anime expeditions roblox strategy automation"
                hero.setVisible(match)
                empty.setVisible(not match)
            search.textChanged.connect(filter_cards)
        elif page in ("Installed", "Updates"):
            column.addWidget(label("No released macros installed yet." if page == "Installed" else "No installed packages to update.", "muted"))
            column.addWidget(label("The dashboard preview is a development tool, not an installed macro. Your saved settings and unit configurations are preserved."))
        else:
            self.build_diagnostics(column)
        column.addStretch()
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(content)

    def open_dashboard(self):
        if self.dashboard and self.dashboard.poll() is None:
            return
        command = ([sys.executable, "--dashboard"] if getattr(sys, "frozen", False)
                   else [sys.executable, str(ROOT / "main.py"), "--dashboard"])
        self.dashboard = subprocess.Popen(command, cwd=Path(sys.executable).parent if getattr(sys, "frozen", False) else ROOT)

    def build_diagnostics(self, column):
        import cv2
        column.addWidget(label("Read-only capture. No clicks, key presses, or process-memory access.", "muted"))
        ocr = "available; integration pending" if importlib.util.find_spec("rapidocr_onnxruntime") else "not installed"
        column.addWidget(label(f"OpenCV {cv2.__version__}  /  OCR: {ocr}", "eyebrow"))
        row = QHBoxLayout()
        windows = QComboBox()
        row.addWidget(windows, 1)
        refresh = QPushButton("Find Roblox")
        capture = QPushButton("Capture client")
        row.addWidget(refresh)
        row.addWidget(capture)
        column.addLayout(row)
        status = label("Keep Roblox visible and unobstructed. This captures desktop pixels inside its client area.", "muted")
        column.addWidget(status)
        preview = QLabel("Your Roblox capture will appear here")
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumHeight(270)
        preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        preview.setStyleSheet("background:#100d0f;border:1px dashed #642238;border-radius:12px;")
        column.addWidget(preview, 1)
        def discover():
            from python_macro.capture import roblox_windows
            windows.clear()
            for hwnd, title in roblox_windows():
                windows.addItem(f"{title} / {hwnd}", hwnd)
            capture.setEnabled(windows.count() > 0)
            if not windows.count():
                status.setText("No visible Roblox window found. Open Roblox, then choose Find Roblox.")
        def snapshot():
            from python_macro.capture import capture_client
            try:
                started = time.perf_counter()
                frame = capture_client(windows.currentData())
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
                image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888).copy()
                preview.setPixmap(QPixmap.fromImage(image).scaled(preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                status.setText(f"Captured {rgb.shape[1]} × {rgb.shape[0]} pixels in {(time.perf_counter()-started)*1000:.0f} ms. No input sent.")
            except Exception as error:
                status.setText(str(error))
        refresh.clicked.connect(discover)
        capture.clicked.connect(snapshot)
        discover()


def main():
    app = QApplication(sys.argv)
    from ui.loading import LoadingScreen
    splash = LoadingScreen(ROOT / "assets/scattermacro.ico")
    splash.show()
    app.processEvents()
    for font in ("segoeui.ttf", "segoeuib.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    try:
        window = Launcher()
    except Exception:
        splash.close()
        raise
    splash.finish(window)
    if "--render-preview" in sys.argv:
        path = Path(sys.argv[sys.argv.index("--render-preview") + 1]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        def render():
            window.grab().save(str(path))
            app.quit()
        QTimer.singleShot(300, render)
    return app.exec()
