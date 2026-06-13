from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QGridLayout,
    QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush

from core.theme_manager import ThemeManager
from storage.repositories import StatsRepository


# ── Bar chart widget ───────────────────────────────────────────────────────

class BarChart(QWidget):
    """
    Pure QPainter bar chart.
    Takes a list of (label, value) pairs.
    """

    def __init__(
        self,
        data:   list[tuple[str, int]],
        theme:  ThemeManager,
        color:  str   = None,
        height: int   = 180,
    ):
        super().__init__()
        self._data  = data
        self._theme = theme
        self._color = color or theme.app("accent")
        self.setFixedHeight(height)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    def paintEvent(self, event):
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w        = self.width()
        h        = self.height()
        padding  = 8
        label_h  = 20
        chart_h  = h - label_h - padding

        max_val  = max(v for _, v in self._data) or 1
        n        = len(self._data)
        bar_w    = max(4, (w - padding * 2) // n - 4)

        for i, (label, value) in enumerate(self._data):
            x       = padding + i * ((w - padding * 2) // n)
            bar_h   = int((value / max_val) * chart_h)
            y       = chart_h - bar_h + padding

            # Bar
            painter.setBrush(QBrush(QColor(self._color)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bar_w, bar_h, 3, 3)

            # Label
            font = QFont()
            font.setPointSizeF(8)
            painter.setFont(font)
            painter.setPen(QColor(self._theme.app("text_muted")))
            painter.drawText(
                x, h - label_h, bar_w, label_h,
                Qt.AlignmentFlag.AlignCenter,
                label[:3],
            )

        painter.end()


# ── Horizontal bar (for breakdowns) ───────────────────────────────────────

class HorizBar(QWidget):
    """Single labeled horizontal progress bar."""

    def __init__(
        self,
        label:    str,
        value:    int,
        total:    int,
        color:    str,
        theme:    ThemeManager,
    ):
        super().__init__()
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)

        lbl = QLabel(label.title())
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(
            f"font-size: 12px; color: {theme.app('text_secondary')}; "
            f"background: transparent;"
        )

        # Bar container
        bar_bg = QWidget()
        bar_bg.setFixedHeight(6)
        bar_bg.setStyleSheet(
            f"background: {theme.app('divider')}; border-radius: 3px;"
        )
        pct = int((value / total * 100)) if total else 0
        bar_fill = QWidget(bar_bg)
        bar_fill.setFixedHeight(6)
        bar_fill.setStyleSheet(
            f"background: {color}; border-radius: 3px;"
        )

        count_lbl = QLabel(str(value))
        count_lbl.setFixedWidth(36)
        count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        count_lbl.setStyleSheet(
            f"font-size: 12px; color: {theme.app('text_muted')}; "
            f"background: transparent;"
        )

        layout.addWidget(lbl)
        layout.addWidget(bar_bg, stretch=1)
        layout.addWidget(count_lbl)

        # Set fill width after layout
        def _resize_fill():
            total_w = bar_bg.width()
            fill_w  = max(4, int(total_w * pct / 100))
            bar_fill.setFixedWidth(fill_w)

        bar_bg.resizeEvent = lambda e: _resize_fill()


# ── Section card ───────────────────────────────────────────────────────────

class SectionCard(QWidget):

    def __init__(self, title: str, theme: ThemeManager):
        super().__init__()
        self.theme = theme
        self._layout = QVBoxLayout(self)
        if title:
            self._layout.setContentsMargins(20, 16, 20, 16)
            self._layout.setSpacing(12)
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"font-size: 13px; font-weight: 600; "
                f"color: {self.theme.app('text_secondary')}; "
                f"text-transform: uppercase; letter-spacing: 0.5px; "
                f"background: transparent;"
            )
            self._layout.addWidget(lbl)
        else:
            self._layout.setContentsMargins(16, 12, 16, 12)
            self._layout.setSpacing(0)

        self.setStyleSheet(f"""
            SectionCard {{
                background: {theme.app('card_bg')};
                border: 1px solid {theme.app('card_border')};
                border-radius: 12px;
            }}
        """)

    def add(self, widget: QWidget):
        self._layout.addWidget(widget)

    def add_row(self, left: str, right: str):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl  = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)

        lbl_l = QLabel(left)
        lbl_l.setStyleSheet(
            f"font-size: 13px; color: {self.theme.app('text_secondary')}; "
            f"background: transparent;"
        )
        lbl_r = QLabel(right)
        lbl_r.setStyleSheet(
            f"font-size: 13px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')}; "
            f"background: transparent;"
        )
        lbl_r.setAlignment(Qt.AlignmentFlag.AlignRight)
        rl.addWidget(lbl_l)
        rl.addStretch()
        rl.addWidget(lbl_r)
        self._layout.addWidget(row)


# ── Stats view ─────────────────────────────────────────────────────────────

class StatsView(QWidget):

    def __init__(self, theme: ThemeManager):
        super().__init__()
        self.theme      = theme
        self.stats_repo = StatsRepository()
        self._build_ui()
        self._apply_theme()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        div = QWidget(); div.setFixedHeight(1)
        div.setStyleSheet(f"background: {self.theme.app('divider')};")
        outer.addWidget(div)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content        = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 28, 32, 32)
        content_layout.setSpacing(20)

        overview = self.stats_repo.get_overview()
        streak   = self.stats_repo.get_streak()
        active   = self.stats_repo.get_most_active_day()
        daily    = self.stats_repo.get_daily_pages(30)

        content_layout.addWidget(self._build_overview_row(overview, streak))
        content_layout.addWidget(self._build_activity_chart(daily))
        content_layout.addWidget(self._build_reading_habits(overview, active))
        content_layout.addLayout(self._build_bottom_row(overview))
        content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(60)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(32, 0, 32, 0)
        title = QLabel("Statistics")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')};"
        )
        layout.addWidget(title)
        layout.addStretch()
        return bar

    def _build_overview_row(self, overview: dict, streak: int) -> QWidget:
        container = QWidget()
        grid      = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        minutes  = overview.get("total_minutes", 0)
        hours    = minutes // 60
        mins_rem = minutes % 60
        time_str = f"{hours}h {mins_rem}m" if hours else f"{minutes}m"

        total = max(overview.get("total_books", 1), 1)

        chips = [
            ("■", str(overview.get("total_books",  0)), "Total Books"),
            ("✓", str(overview.get("completed",     0)), "Completed"),
            ("▸", str(overview.get("in_progress",  0)), "In Progress"),
            ("≡", str(overview.get("total_pages",  0)), "Pages Read"),
            ("○",  time_str,                             "Time Spent"),
            ("▲", f"{streak}d",                         "Current Streak"),
        ]

        for i, (icon, val, lbl) in enumerate(chips):
            card = SectionCard("", self.theme)
            card.setFixedHeight(92)

            inner = QVBoxLayout()
            inner.setSpacing(2)
            inner.setContentsMargins(0, 0, 0, 0)

            top = QHBoxLayout()
            ic  = QLabel(icon)
            ic.setStyleSheet("font-size: 20px; background: transparent;")
            vl  = QLabel(val)
            vl.setStyleSheet(
                f"font-size: 22px; font-weight: 700; "
                f"color: {self.theme.app('text_primary')}; background: transparent;"
            )
            top.addWidget(ic)
            top.addSpacing(6)
            top.addWidget(vl)
            top.addStretch()

            ll = QLabel(lbl)
            ll.setStyleSheet(
                f"font-size: 11px; color: {self.theme.app('text_muted')}; "
                f"background: transparent;"
            )
            inner.addLayout(top)
            inner.addWidget(ll)
            card._layout.addLayout(inner)

            grid.addWidget(card, i // 3, i % 3)

        return container

    def _build_activity_chart(self, daily: list[dict]) -> SectionCard:
        card = SectionCard("Daily Pages — Last 30 Days", self.theme)

        if not daily:
            empty = QLabel("No reading sessions recorded yet.")
            empty.setStyleSheet(
                f"font-size: 13px; color: {self.theme.app('text_muted')}; "
                f"padding: 8px 0; background: transparent;"
            )
            card.add(empty)
            return card

        # Fill missing days with 0
        from datetime import date, timedelta
        today     = date.today()
        date_map  = {r["date"]: r["pages"] for r in daily}
        data      = []
        for i in range(29, -1, -1):
            d   = (today - timedelta(days=i)).isoformat()
            day = (today - timedelta(days=i)).strftime("%d")
            data.append((day, date_map.get(d, 0)))

        chart = BarChart(data, self.theme, height=160)
        card.add(chart)

        # Peak day label
        if daily:
            peak = max(daily, key=lambda x: x["pages"])
            peak_lbl = QLabel(
                f"Peak: {peak['pages']} pages on {peak['date']}"
            )
            peak_lbl.setStyleSheet(
                f"font-size: 11px; color: {self.theme.app('text_muted')}; "
                f"background: transparent;"
            )
            card.add(peak_lbl)

        return card

    def _build_reading_habits(
        self, overview: dict, active_day: str
    ) -> SectionCard:
        card = SectionCard("Reading Habits", self.theme)

        minutes = overview.get("total_minutes", 0)
        pages   = overview.get("total_pages", 0)
        total   = overview.get("total_books", 0)
        comp    = overview.get("completed", 0)
        comp_pct = int((comp / total * 100)) if total else 0

        sessions = StatsRepository()
        avg_pages = (
            pages // max(len(sessions.get_daily_pages(365)), 1)
        )

        card.add_row("Most active day",    active_day)
        card.add_row("Avg pages / session", str(avg_pages))
        card.add_row("Completion rate",    f"{comp_pct}%")
        card.add_row("Total reading time", f"{minutes // 60}h {minutes % 60}m")

        return card

    def _build_bottom_row(self, overview: dict) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(20)

        row.addWidget(self._build_format_breakdown(overview), stretch=1)
        row.addWidget(self._build_type_breakdown(overview),   stretch=1)
        row.addWidget(self._build_top_authors(overview),      stretch=1)

        return row

    def _build_format_breakdown(self, overview: dict) -> SectionCard:
        card   = SectionCard("By Format", self.theme)
        data   = overview.get("format_breakdown", [])
        total  = sum(r["count"] for r in data) or 1
        colors = {
            "epub": "#4A6FA5", "pdf":  "#C0392B",
            "cbz":  "#27AE60", "cbr":  "#27AE60",
            "txt":  "#8E44AD", "html": "#E67E22",
        }
        for row in data:
            bar = HorizBar(
                row["format"],
                row["count"],
                total,
                colors.get(row["format"], "#555555"),
                self.theme,
            )
            card.add(bar)
        if not data:
            card.add_row("No data", "—")
        return card

    def _build_type_breakdown(self, overview: dict) -> SectionCard:
        card   = SectionCard("By Type", self.theme)
        data   = overview.get("type_breakdown", [])
        total  = sum(r["count"] for r in data) or 1
        colors = {
            "fanfic":    "#E91E8C",
            "published": "#4A6FA5",
            "manga":     "#E67E22",
            "comic":     "#27AE60",
            "unknown":   "#555555",
        }
        for row in data:
            bar = HorizBar(
                row["book_type"],
                row["count"],
                total,
                colors.get(row["book_type"], "#555555"),
                self.theme,
            )
            card.add(bar)
        if not data:
            card.add_row("No data", "—")
        return card

    def _build_top_authors(self, overview: dict) -> SectionCard:
        card = SectionCard("Top Authors", self.theme)
        data = overview.get("top_authors", [])
        if not data:
            card.add_row("No data", "—")
            return card
        for row in data:
            card.add_row(
                self._truncate(row["author"], 22),
                f"{row['count']} book{'s' if row['count'] != 1 else ''}"
            )
        return card

    def _truncate(self, text: str, n: int) -> str:
        return text if len(text) <= n else text[:n - 1] + "…"

    def _apply_theme(self):
        self.setStyleSheet(
            f"StatsView {{ background: {self.theme.app('window_bg')}; }}"
        )

    def refresh(self):
        old = self.layout()
        if old:
            QWidget().setLayout(old)
        self._build_ui()
        self._apply_theme()