"""Key entry UI; no launcher is constructed until verification succeeds."""
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from python_macro import licensing
from python_macro.library import VERSION


class KeyAccess(QWidget):
    unlocked = Signal(object)

    def __init__(self, icon_path, verifier=None, website=None, discord=None):
        super().__init__()
        self.verifier = verifier or licensing.verify_key
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.closed = False
        self.setWindowTitle("ScatterMacro | Unlock")
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(520, 520)
        self.resize(580, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(38, 32, 38, 26)
        layout.setSpacing(18)

        def text(value, name=None):
            widget = QLabel(value)
            widget.setWordWrap(True)
            if name:
                widget.setObjectName(name)
            return widget

        layout.addWidget(text("SCATTER / MACRO", "eyebrow"))
        layout.addStretch()
        card = QFrame()
        card.setObjectName("hero")
        content = QVBoxLayout(card)
        content.setContentsMargins(28, 28, 28, 28)
        content.setSpacing(16)
        content.addWidget(text("Unlock your library.", "title"))
        content.addWidget(text("Enter your key to access the launcher and your macros on this device.", "muted"))
        content.addWidget(text("ACCESS KEY", "eyebrow"))
        self.key = QLineEdit()
        self.key.setAccessibleName("Access key")
        self.key.setPlaceholderText("Enter your key")
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setMaxLength(512)
        self.key.returnPressed.connect(self.submit)
        content.addWidget(self.key)
        self.reveal = QCheckBox("Show key")
        self.reveal.toggled.connect(lambda visible: self.key.setEchoMode(
            QLineEdit.Normal if visible else QLineEdit.Password))
        content.addWidget(self.reveal)
        self.unlock = QPushButton("Activate Key")
        self.unlock.setObjectName("primary")
        self.unlock.clicked.connect(self.submit)
        content.addWidget(self.unlock)
        self.status = text("A valid key is required to continue.", "muted")
        self.status.setTextFormat(Qt.PlainText)
        content.addWidget(self.status)
        links = QHBoxLayout()
        for caption, url in (("Get Key", licensing.KEY_WEBSITE if website is None else website),
                             ("Discord", licensing.DISCORD_URL if discord is None else discord)):
            button = QPushButton(caption)
            target = QUrl(url)
            configured = target.isValid() and target.scheme() == "https" and bool(target.host()) and not target.userInfo()
            button.setEnabled(configured)
            button.setToolTip("Open in your browser" if configured else "Link awaiting service setup")
            button.clicked.connect(lambda _, destination=target: self.open_link(destination))
            links.addWidget(button)
        content.addLayout(links)
        layout.addWidget(card)
        layout.addStretch()
        layout.addWidget(text("ScatterMacro " + VERSION + "  |  Device access", "muted"))
        self.timer = QTimer(self)
        self.timer.setInterval(75)
        self.timer.timeout.connect(self.poll)
        self.key.setFocus()

    def open_link(self, destination):
        if not QDesktopServices.openUrl(destination):
            self.status.setText("Could not open your browser. Please try again.")

    def submit(self):
        if self.future is not None or self.closed:
            return
        key = self.key.text().strip()
        if not key:
            self.status.setText("Please enter your key first.")
            self.key.setFocus()
            return
        self.unlock.setEnabled(False)
        self.key.setEnabled(False)
        self.status.setText("Verifying your key...")
        self.future = self.executor.submit(self.verifier, key)
        self.timer.start()

    def poll(self):
        if self.closed or self.future is None or not self.future.done():
            return
        self.timer.stop()
        future, self.future = self.future, None
        try:
            result = future.result()
            if not isinstance(result, licensing.VerifiedLicense) or not result.session:
                raise licensing.LicenseError("Key verification failed. Please check your key and try again.")
        except licensing.LicenseError as error:
            self.status.setText(str(error))
        except Exception:
            self.status.setText("Unable to verify your key. Check your connection and try again.")
        else:
            self.key.clear()
            self.status.setText("Access verified. Opening your library...")
            self.unlocked.emit(result)
            self.close()
            return
        self.key.setEnabled(True)
        self.unlock.setEnabled(True)
        self.key.setFocus()

    def closeEvent(self, event):
        self.closed = True
        self.timer.stop()
        self.key.clear()
        self.executor.shutdown(wait=False, cancel_futures=True)
        event.accept()
