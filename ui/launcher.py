"""Install-first ScatterMacro library with one unified Updates tab."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizeGrip, QSizePolicy, QVBoxLayout, QWidget,
)
from python_macro.library import (
    Library, VERSION, CATALOG_URL, fetch_json, validate_catalog,
    validate_update_feed, version_tuple,
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


class TitleBar(QFrame):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.window()
            window.showNormal() if window.isMaximized() else window.showMaximized()


class Launcher(QMainWindow):
    def __init__(self, library=None):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("ScatterMacro | Library")
        self.setWindowIcon(QIcon(str(ROOT / "assets/scattermacro.ico")))
        self.resize(1180, 780)
        self.setMinimumSize(850, 620)
        self.library = library or Library()
        self.catalog = validate_catalog(json.loads((ROOT / "catalog.json").read_text(encoding="utf-8")))
        self.release = None
        self.updates_checked = False
        self.processes = {}
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.page = "Home"
        outer = QWidget()
        self.setCentralWidget(outer)
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = TitleBar()
        header.setObjectName("header")
        nav = QHBoxLayout(header)
        nav.setContentsMargins(24, 16, 16, 16)
        brand = label("SCATTER / MACRO", "eyebrow")
        brand.setAttribute(Qt.WA_TransparentForMouseEvents)
        nav.addWidget(brand)
        nav.addStretch()
        self.nav = {}
        self.check_buttons = []
        for name in ("Home", "Installed", "Updates"):
            button = QPushButton(name)
            button.setCheckable(True)
            button.clicked.connect(lambda _, page=name: self.show_page(page))
            nav.addWidget(button)
            self.nav[name] = button
        minimize = QPushButton("-")
        minimize.setToolTip("Minimize")
        minimize.clicked.connect(self.showMinimized)
        nav.addWidget(minimize)
        close = QPushButton("X")
        close.setToolTip("Close")
        close.clicked.connect(self.close)
        nav.addWidget(close)
        layout.addWidget(header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(24, 12, 16, 16)
        self.status = label("ScatterMacro " + VERSION, "muted")
        footer.addWidget(self.status, 1)
        folder = QPushButton("Macro configs")
        folder.clicked.connect(lambda: self.open_folder(self.library.root))
        footer.addWidget(folder)
        footer.addWidget(QSizeGrip(self))
        layout.addLayout(footer)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll_job)
        self.show_page("Home")

    def open_folder(self, path):
        try:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except OSError as error:
            self.status.setText("Could not open config folder: " + str(error))

    def has_update(self, macro):
        state = self.library.installed(macro["id"])
        return bool(state and macro.get("version") and
                    version_tuple(macro["version"]) > version_tuple(state["version"]))

    def show_page(self, page):
        self.page = page
        self.check_buttons = []
        updates = sum(self.has_update(m) for m in self.catalog)
        launcher_update = bool(self.release and version_tuple(self.release["version"]) > version_tuple(VERSION))
        for name, button in self.nav.items():
            button.setChecked(name == page)
            button.setText(f"Updates ({updates + int(launcher_update)})" if name == "Updates" and updates + int(launcher_update) else name)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(34, 30, 34, 30)
        column.setSpacing(18)
        column.addWidget(label("YOUR LIBRARY", "eyebrow"))
        column.addWidget(label("Choose your next session." if page == "Home" else page, "title"))
        if page == "Updates":
            column.addWidget(label("One updater checks the launcher and all macros. Each update installs separately; saved configurations remain in place.", "muted"))
            check = QPushButton("Check for updates")
            check.clicked.connect(lambda: self.check_updates())
            self.check_buttons.append(check)
            column.addWidget(check, alignment=Qt.AlignLeft)
            column.addWidget(label("SCATTERMACRO LAUNCHER", "eyebrow"))
            column.addWidget(label("Installed: " + VERSION, "muted"))
            if launcher_update:
                column.addWidget(label("Update available: " + self.release["version"], "eyebrow"))
                button = QPushButton("Update launcher to " + self.release["version"])
                button.setObjectName("primary")
                button.clicked.connect(self.update_launcher)
                column.addWidget(button, alignment=Qt.AlignLeft)
            else:
                column.addWidget(label("Launcher up to date." if self.updates_checked else "Check for updates to see the latest launcher version.", "muted"))
            column.addWidget(label("MACRO UPDATES", "eyebrow"))
        else:
            row = QHBoxLayout()
            row.addWidget(label("Install the macros you want. Each has its own saved configuration.", "muted"), 1)
            check = QPushButton("Check for updates")
            check.clicked.connect(lambda: self.check_updates())
            self.check_buttons.append(check)
            row.addWidget(check)
            column.addLayout(row)
        search = QLineEdit()
        search.setPlaceholderText("Search your macros")
        column.addWidget(search)
        cards = []
        for macro in self.catalog:
            state = self.library.installed(macro["id"])
            if page == "Installed" and not state:
                continue
            if page == "Updates" and not self.has_update(macro):
                continue
            card = QFrame()
            card.setObjectName("hero")
            row = QHBoxLayout(card)
            row.setContentsMargins(26, 26, 26, 26)
            if macro["id"] == "anime-expeditions":
                art = QLabel()
                art.setPixmap(QPixmap(str(ROOT / "assets/anime-expeditions.png")).scaled(400, 225, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                art.setAlignment(Qt.AlignCenter)
                art.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                row.addWidget(art, 2)
            copy = QVBoxLayout()
            copy.addWidget(label(macro["name"], "title"))
            copy.addWidget(label(macro.get("description", ""), "muted"))
            if macro.get("setup_only"):
                copy.addWidget(label("Setup available / automation not connected", "eyebrow"))
            copy.addWidget(label("Installed: " + state["version"] if state else "Not installed", "eyebrow"))
            if self.has_update(macro):
                copy.addWidget(label("Update available: " + macro["version"], "eyebrow"))
            action = QPushButton("Update" if self.has_update(macro) else "Open" if state else "Install" if macro.get("version") else "Not released yet")
            action.setObjectName("primary")
            action.setEnabled(bool(state or macro.get("version")))
            action.clicked.connect(lambda _, m=macro: self.macro_action(m))
            copy.addWidget(action, alignment=Qt.AlignLeft)
            if state:
                configs = QPushButton("Open configs")
                configs.clicked.connect(lambda _, mid=macro["id"]: self.open_folder(self.library.config_dir(mid)))
                copy.addWidget(configs, alignment=Qt.AlignLeft)
            row.addLayout(copy, 3)
            column.addWidget(card)
            cards.append((macro["name"].lower(), card))
        empty = label("No matching macros." if cards else "All installed macros are up to date." if page == "Updates" and self.updates_checked else "Check for updates to see available macro releases." if page == "Updates" else "No macros installed yet.", "muted")
        empty.setVisible(not cards)
        column.addWidget(empty)
        def filter_cards(text):
            found = False
            for name, card in cards:
                match = text.lower().strip() in name
                card.setVisible(match)
                found = found or match
            empty.setVisible(not found)
        search.textChanged.connect(filter_cards)
        column.addStretch()
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(content)

    def start_job(self, message, work, done, failed=None):
        if self.future is not None:
            self.status.setText("Please wait for the current operation to finish.")
            return
        self.status.setText(message)
        for button in self.check_buttons:
            button.setEnabled(False)
        self.on_done, self.on_failed = done, failed
        self.future = self.executor.submit(work)
        self.timer.start()

    def poll_job(self):
        if self.future is None or not self.future.done():
            return
        future, done, failed = self.future, self.on_done, self.on_failed
        self.future = None
        self.timer.stop()
        for button in self.check_buttons:
            button.setEnabled(True)
        try:
            done(future.result())
        except Exception as error:
            self.status.setText("Could not finish: " + str(error))
            if failed:
                failed(error)

    def check_updates(self):
        def done(feed):
            self.catalog = feed["macros"]
            self.release = feed["launcher"]
            self.updates_checked = True
            self.show_page(self.page)
            count = sum(self.has_update(m) for m in self.catalog)
            count += int(version_tuple(self.release["version"]) > version_tuple(VERSION))
            self.status.setText(f"Update check complete. {count} update(s) available in Updates.")
        self.start_job("Checking launcher and macro updates...",
                       lambda: validate_update_feed(fetch_json(CATALOG_URL)), done)

    def macro_action(self, macro):
        if self.future is not None:
            self.status.setText("Please wait for the current operation to finish.")
            return
        process = self.processes.get(macro["id"])
        if process and process.poll() is None:
            self.status.setText("This macro is already running. Close it before updating.")
            return
        if not self.library.installed(macro["id"]):
            self.install_macro(macro)
            return
        if self.has_update(macro):
            self.install_macro(macro)
            return
        def checked(feed):
            self.catalog = feed["macros"]
            self.release = feed["launcher"]
            self.updates_checked = True
            latest = next((m for m in self.catalog if m["id"] == macro["id"]), None)
            self.show_page(self.page)
            if latest and self.has_update(latest):
                answer = QMessageBox.question(self, "Macro update", latest["name"] + " has an update. Install it before opening?")
                if answer == QMessageBox.Yes:
                    self.install_macro(latest, launch=True)
                else:
                    self.launch_macro(macro)
            else:
                self.launch_macro(macro)
        def failed(error):
            if QMessageBox.question(self, "Update check unavailable", "Could not check for updates. Open the installed version anyway?") == QMessageBox.Yes:
                self.launch_macro(macro)
        self.start_job("Checking for updates...", lambda: validate_update_feed(fetch_json(CATALOG_URL)), checked, failed)

    def install_macro(self, macro, launch=False):
        def done(_):
            self.show_page(self.page)
            self.status.setText(macro["name"] + " installed. Your configurations are preserved.")
            if launch:
                self.launch_macro(macro)
        self.start_job("Downloading " + macro["name"] + "...", lambda: self.library.download_install(macro), done)

    def launch_macro(self, macro):
        executable = self.library.executable(macro["id"])
        self.processes[macro["id"]] = subprocess.Popen(
            [str(executable), "--config-dir", str(self.library.config_dir(macro["id"]))],
            cwd=executable.parent, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.status.setText(macro["name"] + " opened.")
        self.showMinimized()

    def update_launcher(self):
        if not self.release or version_tuple(self.release["version"]) <= version_tuple(VERSION):
            self.status.setText("No newer launcher release is available.")
            return
        if not getattr(sys, "frozen", False):
            self.status.setText("Launcher installation updates are available in the packaged Windows app.")
            return
        from python_macro.updater import prepare_update
        target = Path(sys.executable).parent
        def ready(package):
            # Probe installation access before closing the current launcher.
            import tempfile
            with tempfile.TemporaryFile(dir=target.parent):
                pass
            subprocess.Popen([str(package / "ScatterLauncher.exe"), "--apply-update",
                              "--target", str(target), "--pid", str(os.getpid())], cwd=package,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.close()
        self.start_job("Downloading launcher update. The launcher will restart...", lambda: prepare_update(self.release), ready)

    def closeEvent(self, event):
        if self.future is not None:
            self.status.setText("Please wait for the current operation to finish before closing.")
            event.ignore()
            return
        self.executor.shutdown(wait=False)
        event.accept()


def main():
    app = QApplication(sys.argv)
    from ui.loading import LoadingScreen
    for font in ("segoeui.ttf", "segoeuib.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    splash = LoadingScreen(ROOT / "assets/scattermacro.ico")
    splash.show()
    window = Launcher()
    def ready():
        splash.finish(window)
        if "--render-preview" in sys.argv:
            path = Path(sys.argv[sys.argv.index("--render-preview") + 1]).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            def render():
                window.grab().save(str(path))
                app.quit()
            QTimer.singleShot(300, render)
        else:
            window.check_updates()
    # Let the event loop paint and animate the splash, rather than hiding it
    # within the same startup call before users can see it.
    QTimer.singleShot(900, ready)
    return app.exec()
