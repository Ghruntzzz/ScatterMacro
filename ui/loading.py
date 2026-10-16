"""Compact launcher startup screen."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget


class LoadingScreen(QWidget):
    def __init__(self, icon_path):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setWindowTitle("ScatterMacro")
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setFixedSize(360, 170)
        self.setObjectName("loading")
        self.setStyleSheet("""
            QWidget#loading { background:#100c0e; border:1px solid #642238; }
            QLabel { background:transparent; border:0; color:#f3eff0;
                     font-family:'Segoe UI'; }
            QLabel#brand { font-size:23px; font-weight:700; }
            QLabel#status { font-size:12px; color:#b2a4aa; }
            QProgressBar { background:#29131b; border:0; }
            QProgressBar::chunk { background:#a74359; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 25, 28, 25)
        brand = QLabel("ScatterMacro")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        status = QLabel("Opening your library...")
        status.setObjectName("status")
        layout.addWidget(status)
        layout.addStretch()
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setFixedHeight(4)
        layout.addWidget(progress)
        screen = QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def finish(self, window):
        window.show()
        self.close()
