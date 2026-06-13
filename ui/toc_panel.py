from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea,
    QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QCursor

from core.book_model import Book
from core.theme_manager import ThemeManager


class ChapterItem(QPushButton):

    def __init__(self, title: str, index: int, theme: ThemeManager):
        super().__init__()
        self.chapter_index = index
        self.theme         = theme
        self._active       = False

        self.setText(self._truncate(title, 34))
        self.setFixedHeight(38)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(title)
        self._refresh_style()

    def set_active(self, active: bool):
        self._active = active
        self._refresh_style()

    def _refresh_style(self):
        t = self.theme
        if self._active:
            bg    = t.app("sidebar_hover")
            color = t.app("sidebar_text_active")
            border= f"border-left: 3px solid {t.app('accent')};"
        else:
            bg    = "transparent"
            color = t.app("sidebar_text")
            border= "border-left: 3px solid transparent;"

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                {border}
                color: {color};
                border-radius: 0px;
                text-align: left;
                padding: 0 12px 0 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {t.app('sidebar_hover')};
                color: {t.app('sidebar_text_active')};
            }}
        """)

    def _truncate(self, text: str, n: int) -> str:
        return text if len(text) <= n else text[:n - 1] + "…"


class TocPanel(QWidget):
    """
    Slide-in table of contents panel.
    Lives inside the reader view, overlays on the left.
    """

    chapter_selected = pyqtSignal(int)   # chapter index
    close_requested  = pyqtSignal()

    def __init__(self, theme: ThemeManager, parent=None):
        super().__init__(parent)
        self.theme    = theme
        self._items:  list[ChapterItem] = []
        self._active  = 0

        self.setFixedWidth(260)
        self._build_ui()
        self._apply_theme()
        self.hide()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 12, 0)

        title = QLabel("Contents")
        title.setStyleSheet(
            f"font-size: 14px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')}; "
            f"background: transparent;"
        )

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(self.close_requested.emit)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.app('text_muted')};
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {self.theme.app('sidebar_hover')};
                color: {self.theme.app('text_primary')};
            }}
        """)

        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(close_btn)
        layout.addWidget(header)

        # Divider
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {self.theme.app('divider')};")
        layout.addWidget(div)

        # Chapter list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 8)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_container)
        layout.addWidget(scroll)

    # ── Public API ─────────────────────────────────────────────────────────

    def load_book(self, book: Book):
        self._clear()
        for i, chapter in enumerate(book.chapters):
            item = ChapterItem(chapter.title, i, self.theme)
            item.clicked.connect(
                lambda checked, idx=i: self._on_chapter_click(idx)
            )
            self._items.append(item)
            # Insert before the stretch
            count = self._list_layout.count()
            self._list_layout.insertWidget(count - 1, item)

        if self._items:
            self._items[0].set_active(True)
            self._active = 0

    def set_active_chapter(self, chapter_idx: int):
        for item in self._items:
            item.set_active(item.chapter_index == chapter_idx)
        self._active = chapter_idx

    def toggle(self):
        if self.isVisible():
            self._animate_out()
        else:
            self.show()
            self._animate_in()

    # ── Animation ──────────────────────────────────────────────────────────

    def _animate_in(self):
        self.show()
        anim = QPropertyAnimation(self, b"maximumWidth")
        anim.setDuration(180)
        anim.setStartValue(0)
        anim.setEndValue(260)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim   # keep reference

    def _animate_out(self):
        anim = QPropertyAnimation(self, b"maximumWidth")
        anim.setDuration(160)
        anim.setStartValue(260)
        anim.setEndValue(0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.hide)
        anim.start()
        self._anim = anim

    # ── Helpers ────────────────────────────────────────────────────────────

    def _on_chapter_click(self, index: int):
        self.set_active_chapter(index)
        self.chapter_selected.emit(index)

    def _clear(self):
        for item in self._items:
            item.setParent(None)
            item.deleteLater()
        self._items.clear()

    def _apply_theme(self):
        self.setStyleSheet(f"""
            TocPanel {{
                background: {self.theme.app('sidebar_bg')};
                border-right: 1px solid {self.theme.app('divider')};
            }}
        """)