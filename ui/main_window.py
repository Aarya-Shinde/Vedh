from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout,
    QStackedWidget, QGraphicsOpacityEffect, QVBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import QKeySequence, QShortcut, QPainter, QPen, QColor

from core.book_model import Book
from core.theme_manager import ThemeManager
from core.plugin_manager import PluginManager
from ui.sidebar import Sidebar
from ui.library_view import LibraryView
from ui.home_view  import HomeView
from ui.stats_view import StatsView
from ui.settings_view import SettingsView


class FadeStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = None

    def setCurrentIndex(self, index: int):
        if index == self.currentIndex():
            return
        
        super().setCurrentIndex(index)
        new_widget = self.currentWidget()
        if not new_widget:
            return

        eff = QGraphicsOpacityEffect(new_widget)
        new_widget.setGraphicsEffect(eff)

        if self._anim:
            self._anim.stop()

        self._anim = QPropertyAnimation(eff, b"opacity")
        self._anim.setDuration(200)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        def on_finished():
            # Safely remove the graphics effect after animation completes
            new_widget.setGraphicsEffect(None)

        self._anim.finished.connect(on_finished)
        self._anim.start()


class SpinnerWidget(QWidget):
    def __init__(self, parent=None, size=40, color="#E7717D"):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.color = QColor(color)
        self.angle = 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)
        self.timer.start(16)

    def _rotate(self):
        self.angle = (self.angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen = QPen(self.color)
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.drawArc(rect, self.angle * 16, 270 * 16)


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget, theme: ThemeManager):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)
        
        self.spinner = SpinnerWidget(self, size=48, color=theme.app("accent"))
        layout.addWidget(self.spinner)
        
        self.label = QLabel("Loading book...", self)
        self.label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; "
            f"color: {theme.app('text_primary')}; background: transparent;"
        )
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        bg = QColor(self.theme.app("window_bg"))
        bg.setAlpha(220)
        painter.fillRect(self.rect(), bg)


class BookLoadWorker(QThread):
    loaded = pyqtSignal(object)  # Book
    failed = pyqtSignal(str)     # error message

    def __init__(self, book_id: str, file_path: str, fmt: str):
        super().__init__()
        self.book_id = book_id
        self.file_path = file_path
        self.fmt = fmt

    def run(self):
        try:
            from core.book_loader import BookLoader
            import uuid

            book = BookLoader().load(self.file_path, self.fmt)
            book.id = uuid.UUID(self.book_id)
            self.loaded.emit(book)
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):

    def __init__(self, theme: ThemeManager, plugins: PluginManager):
        super().__init__()
        self.theme = theme
        self.plugins = plugins

        self.setWindowTitle("Vedh")
        self.setMinimumSize(QSize(1100, 700))
        self.resize(1300, 800)

        self._build_ui()
        self._connect_signals()
        self._apply_theme()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(self.theme)
        layout.addWidget(self.sidebar)

        self.stack = FadeStackedWidget()
        layout.addWidget(self.stack)

        self.home_view = HomeView(self.theme)
        self.stack.addWidget(self.home_view)               # 0

        self.library_view = LibraryView(self.theme, self.plugins)
        self.stack.addWidget(self.library_view)             # 1

        self.stats_view = StatsView(self.theme)
        self.stack.addWidget(self.stats_view)               # 2

        from ui.reader_view import ReaderView
        self.reader_view = ReaderView(self.theme)
        self.stack.addWidget(self.reader_view)              # 3

        self.settings_view = SettingsView(self.theme)
        self.stack.addWidget(self.settings_view)            # 4

        self.loading_overlay = LoadingOverlay(self, self.theme)
        self.stack.setCurrentIndex(0)

    def _connect_signals(self):
        self.sidebar.nav_clicked.connect(self._on_nav)
        self.sidebar.collection_clicked.connect(self._on_collection_filter)
        self.sidebar.book_dropped.connect(self._on_book_dropped)
        self.library_view.open_book_requested.connect(self._on_open_book_by_id)
        self.home_view.open_book_requested.connect(self._on_open_book_by_id)
        self.reader_view.closed.connect(self._on_reader_closed)

        # Settings signals
        self.settings_view.app_theme_changed.connect(self._on_app_theme)
        self.settings_view.reader_theme_changed.connect(self._on_reader_theme)
        self.settings_view.font_changed.connect(self._on_font_changed)
        self.settings_view.font_size_changed.connect(self._on_font_size)
        self.settings_view.line_spacing_changed.connect(self._on_line_spacing)
        self.settings_view.page_width_changed.connect(self._on_page_width)
        self.settings_view.margin_h_changed.connect(self._on_margin_h)
        self.settings_view.margin_v_changed.connect(self._on_margin_v)
        self.settings_view.profile_updated.connect(self.home_view.refresh)
        self.settings_view.profile_updated.connect(self.library_view._load_library)
        self.settings_view.profile_updated.connect(self.sidebar._load_collections)

    def _on_nav(self, index: int):
        # 0=Home, 1=Library, 2=Statistics, 3=Settings
        # Map sidebar index 3 (Settings) to stacked widget index 4 (SettingsView)
        target = 4 if index == 3 else index
        self.stack.setCurrentIndex(target)
        if index == 0:
            self.home_view.refresh()
        elif index == 1:
            self.library_view.filter_by_collection(None)
        elif index == 2:
            self.stats_view.refresh()

    def _on_collection_filter(self, collection_id: str):
        self.stack.setCurrentIndex(1)   # show library
        self.library_view.filter_by_collection(collection_id)

    def _on_book_dropped(self, book_id: str, collection_id: str):
        from storage.repositories import CollectionRepository
        CollectionRepository().add_book(book_id, collection_id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay"):
            self.loading_overlay.setGeometry(self.rect())

    def _on_open_book_by_id(self, book_id: str):
        """Asynchronously loads the book from DB then opens reader."""
        from storage.repositories import BookRepository
        row = BookRepository().get_by_id(book_id)
        if not row:
            from ui.widgets.toast import ToastManager
            ToastManager.get_instance().show("Book record not found.", "error")
            return
        if row["status"] == "missing":
            from ui.widgets.toast import ToastManager
            ToastManager.get_instance().show(
                f"Cannot open '{row['title']}'. The file has been moved or deleted.", "error"
            )
            return

        title = row["title"]
        file_path = row["file_path"]
        fmt = row["format"]

        self.loading_overlay.label.setText(f"Loading '{title}'...")
        self.loading_overlay.show()

        if hasattr(self, "_load_worker") and self._load_worker.isRunning():
            self._load_worker.terminate()
            self._load_worker.wait()

        self._load_worker = BookLoadWorker(book_id, file_path, fmt)
        self._load_worker.loaded.connect(self._on_async_load_success)
        self._load_worker.failed.connect(lambda err: self._on_async_load_failed(err, title))
        self._load_worker.start()

    def _on_async_load_success(self, book):
        self.loading_overlay.hide()
        self._on_open_book(book)

    def _on_async_load_failed(self, error: str, title: str):
        self.loading_overlay.hide()
        from ui.widgets.toast import ToastManager
        ToastManager.get_instance().show(f"Failed to open '{title}': {error}", "error")

    def _on_open_book(self, book: Book):
        from storage.repositories import SessionRepository
        self._current_session_id    = SessionRepository().start_session(str(book.id))
        self._current_session_start_page = 0
        self.sidebar.setVisible(False)
        self.reader_view.load_book(book)
        self.stack.setCurrentIndex(3)
        self.plugins.emit_book_open(str(book.id))

    def _on_reader_closed(self):
        from storage.repositories import SessionRepository
        if hasattr(self, "_current_session_id"):
            pages = getattr(self.reader_view, "_page", 0)
            start = getattr(self, "_current_session_start_page", 0)
            SessionRepository().end_session(
                self._current_session_id,
                max(0, pages - start)
            )
        self.sidebar.setVisible(True)
        self.home_view.refresh()
        self.stats_view.refresh()
        self.library_view._load_library()
        self.stack.setCurrentIndex(1)

    def _on_app_theme(self, name: str):
        self.theme.load_app_theme(name)
        self.setStyleSheet(self.theme.build_stylesheet())
        self.sidebar._apply_theme()
        self.home_view.refresh()
        self.library_view._apply_theme()
        self.settings_view._apply_theme()
        if hasattr(self, "stats_view"):
            self.stats_view.refresh()

    def _on_reader_theme(self, name: str):
        self.theme.load_reader_theme(name)
        self.reader_view.refresh_settings()

    def _on_font_changed(self, family: str):
        rt = self.theme.reader_theme()
        rt["font_family"] = family
        self.theme._reader_theme = rt
        from core.config_manager import ConfigManager
        ConfigManager().set("font_family", family)
        self.reader_view.refresh_settings()

    def _on_font_size(self, size: float):
        rt = self.theme.reader_theme()
        rt["font_size"] = size
        self.theme._reader_theme = rt
        from core.config_manager import ConfigManager
        ConfigManager().set("font_size", size)
        self.reader_view.refresh_settings()

    def _on_line_spacing(self, spacing: float):
        rt = self.theme.reader_theme()
        rt["line_spacing"] = spacing
        self.theme._reader_theme = rt
        from core.config_manager import ConfigManager
        ConfigManager().set("line_spacing", spacing)
        self.reader_view.refresh_settings()

    def _on_page_width(self, width: float):
        rt = self.theme.reader_theme()
        rt["page_width"] = width
        self.theme._reader_theme = rt
        from core.config_manager import ConfigManager
        ConfigManager().set("page_width", width)
        self.reader_view.refresh_settings()

    def _on_margin_h(self, margin: float):
        rt = self.theme.reader_theme()
        rt["margin_h"] = margin
        self.theme._reader_theme = rt
        from core.config_manager import ConfigManager
        ConfigManager().set("margin_h", margin)
        self.reader_view.refresh_settings()

    def _on_margin_v(self, margin: float):
        rt = self.theme.reader_theme()
        rt["margin_v"] = margin
        self.theme._reader_theme = rt
        from core.config_manager import ConfigManager
        ConfigManager().set("margin_v", margin)
        self.reader_view.refresh_settings()

    # ── Theme ──────────────────────────────────────────────────────────────

    def _apply_theme(self):
        self.setStyleSheet(
            f"QMainWindow {{ background: {self.theme.app('window_bg')}; }}"
        )