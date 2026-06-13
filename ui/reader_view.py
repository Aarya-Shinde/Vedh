from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider,
    QSizePolicy, QStackedLayout
)
from PyQt6.QtGui import (
    QPainter, QKeySequence, QShortcut,
    QColor, QCursor, QPixmap, QPainterPath, QLinearGradient, QBrush, QPen
)
from PyQt6.QtCore import (
    Qt, QRectF, pyqtSignal, QSize,
    QVariantAnimation, QEasingCurve, QPoint, QPointF
)

from core.book_model import Book
from core.theme_manager import ThemeManager
from rendering.layout import LayoutEngine
from storage.repositories import ProgressRepository
from ui.toc_panel import TocPanel


class ReaderCanvas(QWidget):
    resized = pyqtSignal()

    def __init__(self, layout_engine: LayoutEngine, parent=None):
        super().__init__(parent)
        self._engine        = layout_engine
        self._page_num      = 0
        self._double_page   = False
        self._manga_mode    = False
        self._old_pixmap    = None
        self._animation_offset = 0.0
        self._animation_direction = 1
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(QSize(400, 500))

    def set_page(self, page_num: int, animate: bool = True):
        old_page = self._page_num
        self._page_num = page_num

        if animate and old_page != page_num and self.width() > 0:
            # Determine direction: next (slides left, i.e. offset goes negative)
            # prev (slides right, i.e. offset goes positive)
            direction = -1 if page_num > old_page else 1

            # Capture current screen state
            self._old_pixmap = QPixmap(self.size())
            self._old_pixmap.fill(Qt.GlobalColor.transparent)
            old_painter = QPainter(self._old_pixmap)
            old_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            old_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            if self._double_page and self._engine.total_pages > 0:
                self._paint_double(old_painter, old_page)
            else:
                self._engine.paint_page(old_painter, old_page)
            old_painter.end()

            # Set up the animation
            if hasattr(self, "_animation"):
                self._animation.stop()

            self._animation_offset = 0.0
            self._animation_direction = direction

            self._animation = QVariantAnimation(self)
            self._animation.setDuration(400)  # slightly slower for stunning page curl
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(float(self.width()))
            self._animation.setEasingCurve(QEasingCurve.Type.OutQuad)

            def on_value_changed(val):
                self._animation_offset = val
                self.update()

            def on_finished():
                self._old_pixmap = None
                self._animation_offset = 0.0
                self.update()

            self._animation.valueChanged.connect(on_value_changed)
            self._animation.finished.connect(on_finished)
            self._animation.start()
        else:
            self._old_pixmap = None
            self._animation_offset = 0.0
            self.update()

    def set_double_page(self, enabled: bool):
        self._double_page = enabled
        self.update()

    def set_manga_mode(self, enabled: bool):
        self._manga_mode = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        if self._old_pixmap is not None and self._animation_offset > 0:
            offset = self._animation_offset
            dir = self._animation_direction
            w = float(self.width())
            h = float(self.height())
            t = offset / w  # fraction from 0.0 to 1.0

            # Calculate fold line top (x1) and bottom (x2)
            if dir == -1: # next page (right-to-left)
                x1 = w - t * (w + 300)
                x2 = w - t * (w + 450)
            else: # prev page (left-to-right)
                x1 = t * (w + 300)
                x2 = t * (w + 450)

            # Paths for clipping
            path_left = QPainterPath()
            path_left.moveTo(0, 0)
            path_left.lineTo(x1, 0)
            path_left.lineTo(x2, h)
            path_left.lineTo(0, h)
            path_left.closeSubpath()

            path_right = QPainterPath()
            path_right.moveTo(w, 0)
            path_right.lineTo(x1, 0)
            path_right.lineTo(x2, h)
            path_right.lineTo(w, h)
            path_right.closeSubpath()

            # Determine which path belongs to old and new
            if dir == -1:
                path_old = path_left
                path_new = path_right
            else:
                path_old = path_right
                path_new = path_left

            # 1. Paint new page (underneath/revealed)
            painter.save()
            painter.setClipPath(path_new)
            if self._double_page and self._engine.total_pages > 0:
                self._paint_double(painter)
            else:
                self._engine.paint_page(painter, self._page_num)
            painter.restore()

            # 2. Paint old page (captured pixmap)
            painter.save()
            painter.setClipPath(path_old)
            painter.drawPixmap(QPoint(0, 0), self._old_pixmap)
            painter.restore()

            # 3. Draw Drop Shadow and Curl Flap
            Wf = 60.0
            Ws = 40.0

            # Build polygons
            if dir == -1:
                # Flap polygon
                flap_path = QPainterPath()
                flap_path.moveTo(x1 - Wf, 0)
                flap_path.lineTo(x1, 0)
                flap_path.lineTo(x2, h)
                flap_path.lineTo(x2 - Wf, h)
                flap_path.closeSubpath()

                # Shadow polygon
                shadow_path = QPainterPath()
                shadow_path.moveTo(x1 - Wf - Ws, 0)
                shadow_path.lineTo(x1 - Wf, 0)
                shadow_path.lineTo(x2 - Wf, h)
                shadow_path.lineTo(x2 - Wf - Ws, h)
                shadow_path.closeSubpath()

                # Gradients
                grad = QLinearGradient(QPointF(x1 - Wf, 0), QPointF(x1, 0))
                grad.setColorAt(0.0, QColor(0, 0, 0, 20))
                grad.setColorAt(0.2, QColor(0, 0, 0, 0))
                grad.setColorAt(0.6, QColor(255, 255, 255, 180))
                grad.setColorAt(0.8, QColor(255, 255, 255, 240))
                grad.setColorAt(1.0, QColor(0, 0, 0, 60))

                shadow_grad = QLinearGradient(QPointF(x1 - Wf - Ws, 0), QPointF(x1 - Wf, 0))
                shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
                shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 45))
            else:
                # Flap polygon
                flap_path = QPainterPath()
                flap_path.moveTo(x1, 0)
                flap_path.lineTo(x1 + Wf, 0)
                flap_path.lineTo(x2 + Wf, h)
                flap_path.lineTo(x2, h)
                flap_path.closeSubpath()

                # Shadow polygon
                shadow_path = QPainterPath()
                shadow_path.moveTo(x1 + Wf, 0)
                shadow_path.lineTo(x1 + Wf + Ws, 0)
                shadow_path.lineTo(x2 + Wf + Ws, h)
                shadow_path.lineTo(x2 + Wf, h)
                shadow_path.closeSubpath()

                # Gradients
                grad = QLinearGradient(QPointF(x1 + Wf, 0), QPointF(x1, 0))
                grad.setColorAt(0.0, QColor(0, 0, 0, 20))
                grad.setColorAt(0.2, QColor(0, 0, 0, 0))
                grad.setColorAt(0.6, QColor(255, 255, 255, 180))
                grad.setColorAt(0.8, QColor(255, 255, 255, 240))
                grad.setColorAt(1.0, QColor(0, 0, 0, 60))

                shadow_grad = QLinearGradient(QPointF(x1 + Wf + Ws, 0), QPointF(x1 + Wf, 0))
                shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
                shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 45))

            # Draw shadow
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(shadow_grad))
            painter.drawPath(shadow_path)
            painter.restore()

            # Draw flap
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPath(flap_path)
            
            # Draw a subtle edge line for the page boundary
            painter.setPen(QPen(QColor(0, 0, 0, 40), 1))
            painter.drawLine(QPointF(x1, 0), QPointF(x2, h))
            painter.restore()
        else:
            if self._double_page and self._engine.total_pages > 0:
                self._paint_double(painter)
            else:
                self._engine.paint_page(painter, self._page_num)

        painter.end()

    def _paint_double(self, painter: QPainter, page_num: int = None):
        """
        Paint two pages side by side.
        In manga mode, right page is painted first (right-to-left).
        """
        if page_num is None:
            page_num = self._page_num
        w  = self.width()
        h  = self.height()
        hw = w // 2

        if self._manga_mode:
            left_page  = page_num
            right_page = max(0, page_num - 1)
        else:
            left_page  = page_num
            right_page = min(page_num + 1, self._engine.total_pages - 1)

        # Left half
        painter.save()
        painter.setClipRect(0, 0, hw, h)
        self._engine.paint_page(painter, left_page)
        painter.restore()

        # Divider line
        painter.setPen(QColor(self._engine._theme.get("quote_border", "#444")))
        painter.drawLine(hw, 0, hw, h)

        # Right half
        painter.save()
        painter.translate(hw, 0)
        painter.setClipRect(0, 0, hw, h)
        self._engine.paint_page(painter, right_page)
        painter.restore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class ReaderView(QWidget):

    closed = pyqtSignal()

    def __init__(self, theme: ThemeManager, parent=None):
        super().__init__(parent)
        self.theme        = theme
        self._layout      = LayoutEngine()
        self._progress    = ProgressRepository()
        self._book:  Book | None = None
        self._page:  int         = 0
        self._total: int         = 0
        self._is_fullscreen      = False
        self._double_page        = False
        self._manga_mode         = False

        self._build_ui()
        self._build_shortcuts()
        self._apply_theme()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        self._topbar = self._build_topbar()
        root.addWidget(self._topbar)

        # Middle — TOC panel + canvas side by side
        middle = QWidget()
        self._middle_layout = QHBoxLayout(middle)
        self._middle_layout.setContentsMargins(0, 0, 0, 0)
        self._middle_layout.setSpacing(0)

        # TOC panel
        self._toc = TocPanel(self.theme, parent=middle)
        self._toc.chapter_selected.connect(self.go_to_chapter)
        self._toc.close_requested.connect(self._toc.toggle)
        self._middle_layout.addWidget(self._toc)

        # Canvas
        self._canvas = ReaderCanvas(self._layout, parent=self)
        self._canvas.resized.connect(self._on_canvas_resize)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._middle_layout.addWidget(self._canvas)

        root.addWidget(middle)

        # Bottom bar
        self._bottombar = self._build_bottombar()
        root.addWidget(self._bottombar)

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        # Back
        self._back_btn = QPushButton("← Library")
        self._back_btn.setFixedHeight(32)
        self._back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._back_btn.clicked.connect(self._on_close)
        self._style_ghost(self._back_btn)

        # TOC toggle
        self._toc_btn = QPushButton("☰ Contents")
        self._toc_btn.setFixedHeight(32)
        self._toc_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._toc_btn.clicked.connect(self._toggle_toc)
        self._style_ghost(self._toc_btn)

        # Title
        self._title_label = QLabel("")
        self._title_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')};"
        )

        # Font size controls
        self._font_down = QPushButton("A−")
        self._font_up   = QPushButton("A+")
        for btn in (self._font_down, self._font_up):
            btn.setFixedSize(36, 30)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self._style_ghost(btn)
        self._font_down.clicked.connect(lambda: self._change_font_size(-1))
        self._font_up.clicked.connect(lambda:   self._change_font_size(+1))

        # Reader theme toggles
        self._theme_btns = []
        for name in ["Default", "Sepia", "Night"]:
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setFixedWidth(56)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.clicked.connect(
                lambda checked, n=name.lower(): self._on_reader_theme(n)
            )
            self._style_ghost(btn)
            self._theme_btns.append(btn)

        # Fullscreen
        self._fs_btn = QPushButton("⛶")
        self._fs_btn.setFixedSize(32, 32)
        self._fs_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._fs_btn.clicked.connect(self._toggle_fullscreen)
        self._style_ghost(self._fs_btn)

        # Double page (comics)
        self._double_btn = QPushButton("⧉ Double")
        self._double_btn.setFixedHeight(28)
        self._double_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._double_btn.clicked.connect(self._toggle_double_page)
        self._style_ghost(self._double_btn)
        self._double_btn.hide()

        # Manga mode
        self._manga_btn = QPushButton("↩ Manga")
        self._manga_btn.setFixedHeight(28)
        self._manga_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._manga_btn.clicked.connect(self._toggle_manga_mode)
        self._style_ghost(self._manga_btn)
        self._manga_btn.hide()

        # Fit mode (comics)
        self._fit_btn = QPushButton("Fit Width")
        self._fit_btn.setFixedHeight(28)
        self._fit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._fit_btn.clicked.connect(self._cycle_fit_mode)
        self._style_ghost(self._fit_btn)
        self._fit_btn.hide()

        layout.addWidget(self._back_btn)
        layout.addWidget(self._toc_btn)
        layout.addSpacing(8)
        layout.addWidget(self._title_label)
        layout.addStretch()
        layout.addWidget(self._font_down)
        layout.addWidget(self._font_up)
        layout.addSpacing(8)
        for btn in self._theme_btns:
            layout.addWidget(btn)
        layout.addSpacing(8)
        layout.addWidget(self._double_btn)
        layout.addWidget(self._manga_btn)
        layout.addWidget(self._fit_btn)
        layout.addSpacing(4)
        layout.addWidget(self._fs_btn)

        return bar

    def _build_bottombar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self._prev_btn = QPushButton("←")
        self._prev_btn.setFixedSize(QSize(36, 36))
        self._prev_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._prev_btn.clicked.connect(self.prev_page)
        self._style_nav(self._prev_btn)

        self._page_label = QLabel("0 / 0")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setFixedWidth(90)
        self._page_label.setStyleSheet(
            f"font-size: 13px; color: {self.theme.app('text_secondary')};"
        )

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(1)
        self._slider.setValue(0)
        self._slider.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._slider.valueChanged.connect(self._on_slider)
        self._style_slider()

        self._next_btn = QPushButton("→")
        self._next_btn.setFixedSize(QSize(36, 36))
        self._next_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._next_btn.clicked.connect(self.next_page)
        self._style_nav(self._next_btn)

        layout.addWidget(self._prev_btn)
        layout.addWidget(self._page_label)
        layout.addWidget(self._slider)
        layout.addWidget(self._next_btn)

        return bar

    # ── Load ───────────────────────────────────────────────────────────────

    def load_book(self, book: Book):
        self._book = book
        self._reconfigure_layout()
        self._layout.load_book(book)
        self._total = self._layout.total_pages

        self._toc.load_book(book)

        saved      = self._progress.get(str(book.id))
        start_page = saved["page"] if saved else 0
        start_page = max(0, min(start_page, self._total - 1))

        self._title_label.setText(book.metadata.title)
        self._slider.setMaximum(max(1, self._total - 1))

        # Show comic controls
        comic_formats = {"cbz", "cbr", "cb7", "cbt"}
        is_comic = book.format in comic_formats
        self._fit_btn.setVisible(is_comic)
        self._double_btn.setVisible(is_comic)
        self._manga_btn.setVisible(is_comic)

        # Text reader controls hidden for comics
        for btn in self._theme_btns:
            btn.setVisible(not is_comic)
        self._font_down.setVisible(not is_comic)
        self._font_up.setVisible(not is_comic)

        self._go_to_page(start_page, animate=False)

    # ── Navigation ─────────────────────────────────────────────────────────

    def next_page(self):
        step = 2 if self._double_page else 1
        if self._manga_mode:
            if self._page > 0:
                self._go_to_page(max(0, self._page - step))
        else:
            if self._page < self._total - 1:
                self._go_to_page(min(self._total - 1, self._page + step))

    def prev_page(self):
        step = 2 if self._double_page else 1
        if self._manga_mode:
            if self._page < self._total - 1:
                self._go_to_page(min(self._total - 1, self._page + step))
        else:
            if self._page > 0:
                self._go_to_page(max(0, self._page - step))

    def go_to_chapter(self, chapter_idx: int):
        page = self._layout.page_for_chapter(chapter_idx)
        self._go_to_page(page, animate=False)

    def _go_to_page(self, page_num: int, animate: bool = True):
        self._page = page_num
        self._canvas.set_page(page_num, animate=animate)
        self._update_controls()
        self._save_progress()

        # Sync TOC
        chapter = self._layout.chapter_for_page(page_num)
        self._toc.set_active_chapter(chapter)

    def _on_slider(self, value: int):
        if value != self._page:
            self._go_to_page(value, animate=False)

    # ── Resize ─────────────────────────────────────────────────────────────

    def _on_canvas_resize(self):
        if not self._book:
            return
        self._reconfigure_layout()
        self._layout.load_book(self._book)
        self._total = self._layout.total_pages
        self._slider.setMaximum(max(1, self._total - 1))
        self._go_to_page(min(self._page, self._total - 1), animate=False)

    def _reconfigure_layout(self):
        if not self._book:
            return
        vw = self._canvas.width() or 800
        if self._double_page:
            vw = vw // 2

        is_comic = self._book.format in {"cbz", "cbr", "cb7", "cbt"}
        self._layout.configure(
            theme=self.theme.reader_theme(),
            viewport_width=vw,
            viewport_height=self._canvas.height() or 900,
            is_comic=is_comic,
        )

    # ── Fullscreen ─────────────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        if self._is_fullscreen:
            self._topbar.hide()
            self._bottombar.hide()
            self._fs_btn_float = self._build_float_exit()
            self._fs_btn_float.show()
        else:
            self._topbar.show()
            self._bottombar.show()
            if hasattr(self, "_fs_btn_float"):
                self._fs_btn_float.hide()
        self._on_canvas_resize()

    def _build_float_exit(self) -> QPushButton:
        btn = QPushButton("✕ Exit Fullscreen", self)
        btn.setFixedHeight(32)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.move(16, 16)
        btn.clicked.connect(self._toggle_fullscreen)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,0,0,0.6);
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: rgba(0,0,0,0.85);
            }}
        """)
        return btn

    # ── Double page ────────────────────────────────────────────────────────

    def _toggle_double_page(self):
        self._double_page = not self._double_page
        self._canvas.set_double_page(self._double_page)
        label = "⧉ Single" if self._double_page else "⧉ Double"
        self._double_btn.setText(label)
        self._on_canvas_resize()

    # ── Manga mode ─────────────────────────────────────────────────────────

    def _toggle_manga_mode(self):
        self._manga_mode = not self._manga_mode
        self._canvas.set_manga_mode(self._manga_mode)
        label = "↩ Normal" if self._manga_mode else "↩ Manga"
        self._manga_btn.setText(label)
        # Flip arrow directions
        self._prev_btn.setText("→" if self._manga_mode else "←")
        self._next_btn.setText("←" if self._manga_mode else "→")
        self._canvas.update()

    # ── TOC ────────────────────────────────────────────────────────────────

    def _toggle_toc(self):
        self._toc.toggle()

    # ── Font size ──────────────────────────────────────────────────────────

    def _change_font_size(self, delta: int):
        rt   = self.theme.reader_theme()
        size = float(rt.get("font_size", 18)) + delta
        size = max(10, min(32, size))
        rt["font_size"] = size
        self.theme._reader_theme = rt
        if self._book:
            self._reconfigure_layout()
            self._layout.load_book(self._book)
            self._total = self._layout.total_pages
            self._canvas.update()

    def refresh_settings(self):
        if self._book:
            self._reconfigure_layout()
            self._layout.load_book(self._book)
            self._total = self._layout.total_pages
            self._canvas.update()

    # ── Reader theme ───────────────────────────────────────────────────────

    def _on_reader_theme(self, name: str):
        try:
            self.theme.load_reader_theme(name)
        except FileNotFoundError:
            return
        self.refresh_settings()

    # ── Fit mode ───────────────────────────────────────────────────────────

    _FIT_CYCLE  = ["fit_width", "fit_page", "original"]
    _FIT_LABELS = {
        "fit_width": "Fit Width",
        "fit_page":  "Fit Page",
        "original":  "Original",
    }
    _fit_index = 0

    def _cycle_fit_mode(self):
        self._fit_index = (self._fit_index + 1) % len(self._FIT_CYCLE)
        mode = self._FIT_CYCLE[self._fit_index]
        self._layout.set_fit_mode(mode)
        self._fit_btn.setText(self._FIT_LABELS[mode])
        self._canvas.update()

    # ── Progress ───────────────────────────────────────────────────────────

    def _save_progress(self):
        if not self._book or self._total == 0:
            return
        pct     = (self._page / max(self._total - 1, 1)) * 100
        chapter = self._layout.chapter_for_page(self._page)
        self._progress.save(
            book_id=str(self._book.id),
            chapter=chapter,
            page=self._page,
            position=float(self._page),
            percentage=pct,
        )

    # ── Controls ───────────────────────────────────────────────────────────

    def _update_controls(self):
        self._page_label.setText(f"{self._page + 1} / {self._total}")
        self._slider.blockSignals(True)
        self._slider.setValue(self._page)
        self._slider.blockSignals(False)
        self._prev_btn.setEnabled(self._page > 0)
        self._next_btn.setEnabled(self._page < self._total - 1)

    # ── Shortcuts ──────────────────────────────────────────────────────────

    def _build_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Right),
                  self).activated.connect(self.next_page)
        QShortcut(QKeySequence(Qt.Key.Key_Left),
                  self).activated.connect(self.prev_page)
        QShortcut(QKeySequence(Qt.Key.Key_Space),
                  self).activated.connect(self.next_page)
        QShortcut(QKeySequence(Qt.Key.Key_Escape),
                  self).activated.connect(self._on_escape)
        QShortcut(QKeySequence("F"),
                  self).activated.connect(self._toggle_fullscreen)
        QShortcut(QKeySequence("T"),
                  self).activated.connect(self._toggle_toc)
        QShortcut(QKeySequence(Qt.Key.Key_BracketLeft),
                  self).activated.connect(lambda: self._change_font_size(-1))
        QShortcut(QKeySequence(Qt.Key.Key_BracketRight),
                  self).activated.connect(lambda: self._change_font_size(+1))

    def _on_escape(self):
        if self._is_fullscreen:
            self._toggle_fullscreen()
        else:
            self._on_close()

    # ── Close ──────────────────────────────────────────────────────────────

    def _on_close(self):
        self._save_progress()
        self.closed.emit()

    # ── Styling ────────────────────────────────────────────────────────────

    def _style_ghost(self, btn: QPushButton):
        t = self.theme
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {t.app('text_secondary')};
                border: 1px solid {t.app('divider')};
                border-radius: 5px;
                padding: 0 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {t.app('sidebar_hover')};
                color: {t.app('text_primary')};
            }}
            QPushButton:checked {{
                background: {t.app('accent')};
                color: #FFFFFF;
                border-color: {t.app('accent')};
            }}
        """)

    def _style_nav(self, btn: QPushButton):
        t = self.theme
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.app('card_bg')};
                color: {t.app('text_primary')};
                border: 1px solid {t.app('divider')};
                border-radius: 6px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {t.app('accent')};
                color: #FFFFFF;
                border-color: {t.app('accent')};
            }}
            QPushButton:disabled {{
                color: {t.app('text_muted')};
                background: transparent;
                border-color: {t.app('divider')};
            }}
        """)

    def _style_slider(self):
        t = self.theme
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 3px;
                background: {t.app('divider')};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {t.app('accent')};
                width: 14px; height: 14px;
                margin: -6px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {t.app('accent')};
                border-radius: 2px;
            }}
        """)

    def _apply_theme(self):
        t = self.theme
        self.setStyleSheet(
            f"ReaderView {{ background: {t.app('window_bg')}; }}"
        )
        self._topbar.setStyleSheet(
            f"QWidget {{ background: {t.app('sidebar_bg')}; "
            f"border-bottom: 1px solid {t.app('divider')}; }}"
        )
        self._bottombar.setStyleSheet(
            f"QWidget {{ background: {t.app('sidebar_bg')}; "
            f"border-top: 1px solid {t.app('divider')}; }}"
        )