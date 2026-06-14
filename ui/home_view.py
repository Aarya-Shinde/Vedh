from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QGridLayout,
    QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont

from core.theme_manager import ThemeManager
from storage.repositories import (
    BookRepository, ProgressRepository,
    SessionRepository, StatsRepository
)


class StatChip(QWidget):
    """Single stat — icon + value + label."""

    def __init__(self, icon: str, value: str, label: str,
                 theme: ThemeManager):
        super().__init__()
        self.setFixedHeight(80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)

        top = QHBoxLayout()
        icon_l = QLabel(icon)
        icon_l.setStyleSheet("font-size: 18px; background: transparent;")
        val_l  = QLabel(value)
        val_l.setStyleSheet(
            f"font-size: 22px; font-weight: 700; "
            f"color: {theme.app('text_primary')}; background: transparent;"
        )
        top.addWidget(icon_l)
        top.addSpacing(8)
        top.addWidget(val_l)
        top.addStretch()
        layout.addLayout(top)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: 11px; color: {theme.app('text_muted')}; "
            f"background: transparent;"
        )
        layout.addWidget(lbl)

        self.setStyleSheet(f"""
            StatChip {{
                background: {theme.app('card_bg')};
                border: 1px solid {theme.app('card_border')};
                border-radius: 10px;
            }}
            StatChip:hover {{
                background: {theme.app('card_hover')};
                border: 1px solid {theme.app('accent')};
            }}
        """)


class MiniBookCard(QWidget):
    """Compact horizontal book card for recently read."""

    clicked = pyqtSignal(str)   # book_id

    def __init__(self, row, theme: ThemeManager):
        super().__init__()
        self.book_id = row["id"]
        self.theme   = theme
        self.setFixedHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Cover thumbnail
        cover = QLabel()
        cover.setFixedSize(40, 56)
        raw = row["cover"]
        if raw:
            px = QPixmap()
            loaded = False
            if isinstance(raw, bytes):
                loaded = px.loadFromData(raw)
            elif isinstance(raw, str):
                loaded = px.load(raw)
            if loaded:
                cover.setPixmap(px.scaled(
                    40, 56,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            else:
                cover.setPixmap(self._placeholder_cover(row["format"]))
        else:
            cover.setPixmap(self._placeholder_cover(row["format"]))

        # Info
        info = QVBoxLayout()
        info.setSpacing(3)

        title = QLabel(self._truncate(row["title"], 28))
        title.setStyleSheet(
            f"font-size: 13px; font-weight: 600; "
            f"color: {theme.app('text_primary')}; background: transparent;"
        )
        author = QLabel(self._truncate(row["author"] or "Unknown", 30))
        author.setStyleSheet(
            f"font-size: 11px; color: {theme.app('text_secondary')}; "
            f"background: transparent;"
        )

        # Progress bar
        progress_row = ProgressRepository().get(row["id"])
        pct = progress_row["percentage"] if progress_row else 0
        prog_bg = QWidget()
        prog_bg.setFixedHeight(3)
        prog_bg.setStyleSheet(
            f"background: {theme.app('divider')}; border-radius: 2px;"
        )
        prog_fill = QWidget(prog_bg)
        fill_w = max(2, int((pct / 100) * 160))
        prog_fill.setFixedSize(fill_w, 3)
        prog_fill.setStyleSheet(
            f"background: {theme.app('accent')}; border-radius: 2px;"
        )

        info.addWidget(title)
        info.addWidget(author)
        info.addWidget(prog_bg)

        layout.addWidget(cover)
        layout.addLayout(info)
        layout.addStretch()

        self.setStyleSheet(f"""
            MiniBookCard {{
                background: {theme.app('card_bg')};
                border: 1px solid {theme.app('card_border')};
                border-radius: 8px;
            }}
            MiniBookCard:hover {{
                background: {theme.app('card_hover')};
                border: 1px solid {theme.app('accent')};
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.book_id)

    def _placeholder_cover(self, fmt: str) -> QPixmap:
        from ui.book_card import FORMAT_COLORS
        color = FORMAT_COLORS.get(fmt, "#555555")
        px    = QPixmap(40, 56)
        px.fill(QColor(color).darker(150))
        p = QPainter(px)
        p.setPen(QColor("#FFFFFF"))
        f = QFont(); f.setPointSize(8); f.setBold(True)
        p.setFont(f)
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, fmt.upper()[:3])
        p.end()
        return px

    def _truncate(self, text: str, n: int) -> str:
        return text if len(text) <= n else text[:n - 1] + "…"


class StreakWidget(QWidget):
    """Visual reading streak display."""

    def __init__(self, streak: int, theme: ThemeManager):
        super().__init__()
        self.setFixedHeight(90)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(16)

        flame = QLabel("★")
        flame.setStyleSheet("font-size: 36px; background: transparent;")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        streak_val = QLabel(f"{streak} day{'s' if streak != 1 else ''}")
        streak_val.setStyleSheet(
            f"font-size: 28px; font-weight: 700; "
            f"color: {theme.app('text_primary')}; background: transparent;"
        )
        streak_lbl = QLabel("Reading streak — keep it going!")
        streak_lbl.setStyleSheet(
            f"font-size: 12px; color: {theme.app('text_muted')}; "
            f"background: transparent;"
        )
        text_col.addWidget(streak_val)
        text_col.addWidget(streak_lbl)

        layout.addWidget(flame)
        layout.addLayout(text_col)
        layout.addStretch()

        self.setStyleSheet(f"""
            StreakWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {theme.app('card_bg')},
                    stop:1 {theme.app('window_bg')}
                );
                border: 1px solid {theme.app('card_border')};
                border-radius: 12px;
            }}
        """)


class HeroBanner(QWidget):
    """Stunning welcome banner with gradient background."""

    def __init__(self, theme: ThemeManager):
        super().__init__()
        self.setFixedHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        from core.config_manager import ConfigManager
        user = ConfigManager().get("username", "Reader")
        is_dark = "Dark" in theme.app("name", "dark")
        if is_dark:
            bg = f"""
                qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2A241F,
                    stop:1 #161412
                )
            """
            border = f"1px solid {theme.app('accent')}"
            text_color = "#FFFFFF"
            subtext_color = "rgba(255, 255, 255, 0.85)"
        else:
            bg = """
                qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #FAF9F5,
                    stop:1 #FCEEF0
                )
            """
            border = f"1px solid {theme.app('card_border')}"
            text_color = "#181614"  # Use the bg color of dark mode for that font
            subtext_color = "#5C6661"

        welcome = QLabel(f"Welcome back, {user}")
        welcome.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 700;
            color: {text_color};
            background: transparent;
        """)

        subtext = QLabel("What do you want to read today?")
        subtext.setStyleSheet(f"""
            font-size: 13px;
            color: {subtext_color};
            background: transparent;
        """)

        layout.addWidget(welcome)
        layout.addWidget(subtext)
        layout.addStretch()

        self.setStyleSheet(f"""
            HeroBanner {{
                background: {bg};
                border: {border};
                border-radius: 12px;
            }}
        """)


class HomeView(QWidget):

    open_book_requested = pyqtSignal(str)   # book_id

    def __init__(self, theme: ThemeManager):
        super().__init__()
        self.theme      = theme
        self.book_repo  = BookRepository()
        self.stats_repo = StatsRepository()
        self.session_repo = SessionRepository()

        self._build_ui()
        self._apply_theme()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = self._build_header()
        outer.addWidget(header)

        div = QWidget(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: {self.theme.app('divider')};")
        outer.addWidget(div)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 28, 32, 32)
        content_layout.setSpacing(24)

        # Hero Banner
        banner = HeroBanner(self.theme)
        content_layout.addWidget(banner)

        # Content blocks
        currently = self._build_currently_reading()
        recent    = self._build_recent()

        content_layout.addWidget(currently)
        content_layout.addWidget(recent)
        content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(60)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        title = QLabel("Home")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')};"
        )
        layout.addWidget(title)
        layout.addStretch()
        return bar

    def _build_overview(self) -> QWidget:
        overview = self.stats_repo.get_overview()
        streak   = StatsRepository().get_streak()

        minutes  = overview.get("total_minutes", 0)
        hours    = minutes // 60
        time_str = f"{hours}h" if hours else f"{minutes}m"

        chips_data = [
            ("■", str(overview.get("total_books",   0)), "Total books"),
            ("✓", str(overview.get("completed",      0)), "Completed"),
            ("▸", str(overview.get("in_progress",   0)), "In progress"),
            ("≡", str(overview.get("total_pages",   0)), "Pages read"),
            ("○",  time_str,                              "Time spent"),
            ("▲", str(streak),                           "Day streak"),
        ]

        container = QWidget()
        grid      = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        for i, (icon, val, lbl) in enumerate(chips_data):
            chip = StatChip(icon, val, lbl, self.theme)
            grid.addWidget(chip, i // 3, i % 3)

        return container

    def _build_streak(self) -> QWidget:
        streak = StatsRepository().get_streak()
        return StreakWidget(streak, self.theme)

    def _build_currently_reading(self) -> QWidget:
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        lbl = self._section_label("Currently Reading")
        layout.addWidget(lbl)

        # Books with progress > 0 and < 100
        conn = __import__(
            'storage.database', fromlist=['get_connection']
        ).get_connection()
        rows = conn.execute("""
            SELECT b.* FROM books b
            JOIN reading_progress rp ON rp.book_id = b.id
            WHERE rp.percentage > 0 AND rp.percentage < 100
              AND b.status = 'ok'
            ORDER BY rp.updated_at DESC
            LIMIT 6
        """).fetchall()
        conn.close()

        if not rows:
            empty = QLabel("Nothing in progress yet.")
            empty.setStyleSheet(
                f"font-size: 13px; color: {self.theme.app('text_muted')}; "
                f"padding: 8px 0;"
            )
            layout.addWidget(empty)
            return container

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, row in enumerate(rows):
            card = MiniBookCard(row, self.theme)
            card.clicked.connect(self.open_book_requested.emit)
            grid.addWidget(card, i // 2, i % 2)

        layout.addLayout(grid)
        return container

    def _build_recent(self) -> QWidget:
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        lbl = self._section_label("Recently Added")
        layout.addWidget(lbl)

        from core.config_manager import ConfigManager
        limit = ConfigManager().get("recently_added_limit", 4)
        rows = self.book_repo.get_all()[:limit]

        if not rows:
            empty = QLabel("Import some books to get started.")
            empty.setStyleSheet(
                f"font-size: 13px; color: {self.theme.app('text_muted')}; "
                f"padding: 8px 0;"
            )
            layout.addWidget(empty)
            return container

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, row in enumerate(rows):
            card = MiniBookCard(row, self.theme)
            card.clicked.connect(self.open_book_requested.emit)
            grid.addWidget(card, i // 2, i % 2)

        layout.addLayout(grid)
        return container

    # ── Helpers ────────────────────────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')};"
        )
        return lbl

    def _apply_theme(self):
        self.setStyleSheet(
            f"HomeView {{ background: {self.theme.app('window_bg')}; }}"
        )

    def refresh(self):
        """Call after importing books or finishing a session."""
        # Rebuild UI with fresh data
        old_layout = self.layout()
        if old_layout:
            QWidget().setLayout(old_layout)
        self._build_ui()
        self._apply_theme()