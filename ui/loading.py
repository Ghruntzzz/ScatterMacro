"""Borderless wine-red identity panel with an animated orbit."""
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget


class LoadingScreen(QWidget):
    def __init__(self, icon_path):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setWindowTitle("ScatterMacro")
        self.setWindowIcon(QIcon(str(icon_path)))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(420, 230)
        self.icon = QIcon(str(icon_path))
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(30)
        screen = QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def advance(self):
        self.angle = (self.angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QRadialGradient(210, 75, 250)
        gradient.setColorAt(0, QColor("#3c1221"))
        gradient.setColorAt(1, QColor("#09080b"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#63273b"), 1))
        painter.drawRoundedRect(QRectF(1, 1, 418, 228), 22, 22)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#502232"), 2))
        painter.drawEllipse(QRectF(178, 28, 64, 64))
        painter.setPen(QPen(QColor("#df8aa5"), 2, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(QRectF(178, 28, 64, 64), -self.angle * 16, 90 * 16)
        painter.drawPixmap(190, 40, self.icon.pixmap(40, 40))
        painter.setPen(QColor("#faf2f5"))
        painter.setFont(QFont("Segoe UI", 22, QFont.DemiBold))
        painter.drawText(QRectF(0, 112, 420, 40), Qt.AlignCenter, "ScatterMacro")
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#c5a8b3"))
        painter.drawText(QRectF(0, 158, 420, 28), Qt.AlignCenter, "Preparing your library")
        for i in range(3):
            painter.setBrush(QColor("#d7809e" if int(self.angle / 120) == i else "#56303f"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(197 + i * 12, 201, 4, 4))

    def finish(self, window):
        self.timer.stop()
        window.show()
        self.close()
