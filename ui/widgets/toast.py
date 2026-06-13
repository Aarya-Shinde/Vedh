from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout, QPushButton, QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen
from core.theme_manager import ThemeManager

class ToastWidget(QWidget):
    dismissed = pyqtSignal(object)

    def __init__(self, message: str, level: str, theme: ThemeManager, parent: QWidget = None):
        super().__init__(parent)
        self.message = message
        self.level = level  # "info", "success", "warning", "error"
        self.theme = theme

        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build_ui()
        
        # Auto-dismiss timer
        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.fade_out)
        self.timer.start()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Icon based on level
        icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌"
        }
        icon_lbl = QLabel(icons.get(self.level, "ℹ️"))
        icon_lbl.setStyleSheet("font-size: 14px; background: transparent;")
        layout.addWidget(icon_lbl)

        # Message
        msg_lbl = QLabel(self.message)
        msg_lbl.setWordWrap(True)
        text_color = self.theme.app("text_primary")
        msg_lbl.setStyleSheet(f"font-size: 12px; color: {text_color}; background: transparent; font-weight: 500;")
        layout.addWidget(msg_lbl, stretch=1)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {self.theme.app("text_muted")};
                font-size: 16px;
                font-weight: bold;
                line-height: 16px;
            }}
            QPushButton:hover {{
                color: {self.theme.app("text_primary")};
            }}
        """)
        close_btn.clicked.connect(self.fade_out)
        layout.addWidget(close_btn)

        self.setFixedWidth(320)
        self.adjustSize()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded background
        bg_color = QColor(self.theme.app("card_bg"))
        border_color = QColor(self.theme.app("card_border"))
        
        # Left accent color
        accent_colors = {
            "info": self.theme.app("accent"),
            "success": self.theme.app("success"),
            "warning": "#E67E22",
            "error": self.theme.app("danger")
        }
        accent_color = QColor(accent_colors.get(self.level, self.theme.app("accent")))

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        # Left color bar
        painter.setBrush(QBrush(accent_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 4, self.height(), 8, 8)
        # Sharp edge clip
        painter.drawRect(2, 0, 2, self.height())

    def fade_out(self):
        self.timer.stop()
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(lambda: self.dismissed.emit(self))
        self.anim.start()


class ToastManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ToastManager()
        return cls._instance

    def __init__(self):
        self.toasts = []
        self.theme = None

    def initialize(self, theme: ThemeManager):
        self.theme = theme

    def show(self, message: str, level: str = "info"):
        main_win = None
        for w in QApplication.topLevelWidgets():
            if w.inherits("QMainWindow"):
                main_win = w
                break
        
        if not main_win or not self.theme:
            print(f"[{level.upper()}] {message}")
            return

        toast = ToastWidget(message, level, self.theme, main_win)
        toast.dismissed.connect(self._on_dismissed)
        
        self.toasts.append(toast)
        self.reposition_toasts(main_win)
        
        # Fade in
        toast.setWindowOpacity(0.0)
        toast.show()
        
        toast.anim_in = QPropertyAnimation(toast, b"windowOpacity")
        toast.anim_in.setDuration(250)
        toast.anim_in.setStartValue(0.0)
        toast.anim_in.setEndValue(1.0)
        toast.anim_in.start()

    def _on_dismissed(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
            toast.deleteLater()
            
            main_win = None
            for w in QApplication.topLevelWidgets():
                if w.inherits("QMainWindow"):
                    main_win = w
                    break
            if main_win:
                self.reposition_toasts(main_win)

    def reposition_toasts(self, main_win: QWidget):
        geom = main_win.geometry()
        x = geom.x() + geom.width() - 340
        y = geom.y() + geom.height() - 40
        
        for toast in reversed(self.toasts):
            y -= toast.height() + 10
            target_pos = QPoint(x, y)
            
            if toast.pos() != target_pos and toast.isVisible():
                anim = QPropertyAnimation(toast, b"pos")
                anim.setDuration(200)
                anim.setStartValue(toast.pos())
                anim.setEndValue(target_pos)
                anim.setEasingCurve(QEasingCurve.Type.OutQuad)
                anim.start()
                toast._pos_anim = anim
            else:
                toast.move(target_pos)
