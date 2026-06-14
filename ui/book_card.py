from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QHBoxLayout, QProgressBar, QSizePolicy,
    QPushButton, QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QSize, QMimeData,
    QPropertyAnimation, QEasingCurve, QPoint, QRectF
)
from PyQt6.QtGui import (
    QPixmap, QColor, QPainter, QFont, QCursor, QDrag,
    QLinearGradient, QPen, QPainterPath
)
from datetime import datetime

from core.theme_manager import ThemeManager


FORMAT_COLORS = {
    "epub":  "#4A6FA5",
    "pdf":   "#C0392B",
    "cbz":   "#27AE60",
    "cbr":   "#27AE60",
    "txt":   "#8E44AD",
    "html":  "#E67E22",
    "fb2":   "#16A085",
}


class BookCard(QWidget):

    open_requested = pyqtSignal(str)   # emits book_id
    fetch_metadata_requested = pyqtSignal(str)   # book_id
    convert_requested        = pyqtSignal(str)   # book_id
    removed                  = pyqtSignal(str)   # book_id
    selection_toggled        = pyqtSignal(str, bool) # book_id, selected

    def __init__(self, book_row, theme: ThemeManager):
        super().__init__()
        self.book_row = book_row
        self.theme = theme
        self.book_id = book_row["id"]
        self.is_missing = book_row["status"] == "missing"
        try:
            self.is_favorite = bool(book_row["is_favorite"])
        except Exception:
            self.is_favorite = False

        self._selection_mode = False
        self._selected = False

        self.setFixedSize(QSize(160, 260))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(book_row["title"])

        self._build_ui()
        self._apply_theme()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Cover container (covers + overlays + badge + fav)
        self.cover_container = QWidget(self)
        self.cover_container.setFixedSize(QSize(160, 180))

        # Cover image
        self.cover_img = QLabel(self.cover_container)
        self.cover_img.setGeometry(0, 0, 160, 180)
        self.cover_img.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Selection badge
        self.selection_badge = QLabel(self.cover_container)
        self.selection_badge.setGeometry(8, 8, 20, 20)
        self.selection_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selection_badge.hide()

        raw = self.book_row["cover"]
        loaded = False
        if raw:
            pixmap = QPixmap()
            if isinstance(raw, bytes):
                loaded = pixmap.loadFromData(raw)
            elif isinstance(raw, str):
                loaded = pixmap.load(raw)
                
            if loaded:
                self.cover_img.setPixmap(
                    pixmap.scaled(160, 180,
                                  Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                  Qt.TransformationMode.SmoothTransformation)
                )

        if not loaded:
            self.cover_img.setPixmap(self._generate_placeholder())

        if self.is_missing:
            # Dim the cover if it is missing
            dim_overlay = QWidget(self.cover_container)
            dim_overlay.setGeometry(0, 0, 160, 180)
            dim_overlay.setStyleSheet("background: rgba(0, 0, 0, 0.5); border-top-left-radius: 6px; border-top-right-radius: 6px;")

        # Format badge
        self.badge = QLabel(self.book_row["format"].upper(), self.cover_container)
        self.badge.setGeometry(8, 150, 48, 22)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_col = FORMAT_COLORS.get(self.book_row["format"], "#555555")
        self.badge.setStyleSheet(f"""
            QLabel {{
                background: {badge_col};
                color: #FFFFFF;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)

        # Favorite button
        self.fav_btn = QPushButton("★", self.cover_container)
        self.fav_btn.setGeometry(128, 150, 24, 22)
        self.fav_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.fav_btn.clicked.connect(self._on_toggle_favorite)
        self._update_favorite_ui()

        # Hover overlay quick-actions
        if not self.is_missing:
            self.hover_overlay = QWidget(self.cover_container)
            self.hover_overlay.setGeometry(0, 0, 160, 180)
            self.hover_overlay.setStyleSheet("""
                QWidget {
                    background: rgba(0, 0, 0, 0.7);
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                }
            """)
            
            self.opacity_effect = QGraphicsOpacityEffect(self.hover_overlay)
            self.hover_overlay.setGraphicsEffect(self.opacity_effect)
            self.opacity_effect.setOpacity(0.0)

            self.open_action_btn = QPushButton("Open", self.hover_overlay)
            self.open_action_btn.setGeometry(25, 60, 110, 26)
            self.open_action_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            is_dark = "Dark" in self.theme.app("name", "dark")
            primary_text = "#181614" if is_dark else "#FFFFFF"
            self.open_action_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {self.theme.app("accent")};
                    color: {primary_text};
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: {self.theme.app("accent_hover")};
                }}
            """)
            self.open_action_btn.clicked.connect(lambda: self.open_requested.emit(self.book_id))

            self.add_action_btn = QPushButton("+ Collection", self.hover_overlay)
            self.add_action_btn.setGeometry(25, 96, 110, 26)
            self.add_action_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.add_action_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255, 255, 255, 0.2);
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 0.35);
                }}
            """)
            self.add_action_btn.clicked.connect(self._show_add_to_collection_menu)

        layout.addWidget(self.cover_container)

        # 2. Info area (Title + Author + Progress)
        info = QWidget()
        info.setFixedHeight(80)
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(8, 6, 8, 6)
        info_layout.setSpacing(3)

        title_label = QLabel(self._truncate(self.book_row["title"], 22))
        title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')}; background: transparent;"
        )

        author_label = QLabel(self._truncate(self.book_row["author"] or "Unknown", 24))
        author_label.setStyleSheet(
            f"font-size: 11px; color: {self.theme.app('text_secondary')}; "
            f"background: transparent;"
        )

        # Progress row
        from storage.repositories import ProgressRepository
        progress_row = ProgressRepository().get(self.book_id)
        pct = progress_row["percentage"] if progress_row else 0.0

        prog_widget = QWidget()
        prog_widget.setFixedHeight(14)
        prog_widget_layout = QHBoxLayout(prog_widget)
        prog_widget_layout.setContentsMargins(0, 0, 0, 0)
        prog_widget_layout.setSpacing(6)

        self.prog_track = QWidget()
        self.prog_track.setFixedHeight(4)
        self.prog_track.setStyleSheet(f"background: {self.theme.app('divider')}; border-radius: 2px;")
        
        self.prog_fill = QWidget(self.prog_track)
        self.prog_fill.setFixedHeight(4)
        self.prog_fill.setStyleSheet(f"background: {self.theme.app('accent')}; border-radius: 2px;")
        fill_w = max(0, int(90 * pct / 100))
        self.prog_fill.setFixedWidth(fill_w)

        pct_label = QLabel(f"{int(pct)}%")
        pct_label.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {self.theme.app('text_muted')}; background: transparent;")

        prog_widget_layout.addWidget(self.prog_track, stretch=1)
        prog_widget_layout.addWidget(pct_label)

        info_layout.addWidget(title_label)
        info_layout.addWidget(author_label)
        info_layout.addWidget(prog_widget)
        layout.addWidget(info)

    def _generate_placeholder(self) -> QPixmap:
        """Generate a beautiful gradient placeholder with watermarked title."""
        title = self.book_row["title"]
        fmt = self.book_row["format"]
        
        book_type = "unknown"
        if "book_type" in self.book_row.keys():
            book_type = (self.book_row["book_type"] or "unknown").lower()

        if book_type == "fanfic":
            color_hex = "#1E1E1E"
        else:
            color_hex = FORMAT_COLORS.get(fmt, "#555555")
        
        pixmap = QPixmap(160, 180)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Clip painter to rounded rectangle
        clip_path = QPainterPath()
        clip_path.addRoundedRect(0, 0, 160, 180, 6, 6)
        painter.setClipPath(clip_path)
        
        # 1. Base background
        if book_type == "fanfic":
            painter.setBrush(QColor(color_hex))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(0, 0, 160, 180)
        else:
            gradient = QLinearGradient(0, 0, 160, 180)
            gradient.setColorAt(0.0, QColor(color_hex).darker(140))
            gradient.setColorAt(1.0, QColor(self.theme.app("accent")))
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(0, 0, 160, 180)
        
        # 2. Faint blurred image for fanfic
        if book_type == "fanfic":
            bg_path = "assets/images/Thin Ice.png"
            bg_pix = QPixmap(bg_path)
            if not bg_pix.isNull():
                # Center crop and scale
                scaled_bg = bg_pix.scaled(
                    160, 180,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # Apply downscale-upscale blur technique
                small = scaled_bg.scaled(
                    16, 18,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation
                )
                blurred_bg = small.scaled(
                    160, 180,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # Draw blurred image with 0.5 opacity for a faint look
                painter.setOpacity(0.5)
                x_offset = (blurred_bg.width() - 160) // 2
                y_offset = (blurred_bg.height() - 180) // 2
                painter.drawPixmap(0, 0, blurred_bg, x_offset, y_offset, 160, 180)
                painter.setOpacity(1.0)
        
        # 3. Text
        font = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 220))
        
        text_rect = QRectF(12, 40, 136, 100)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self._truncate(title, 40)
        )

        if book_type == "fanfic":
            sub_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(sub_font)
            painter.setPen(QColor(255, 255, 255, 180))
            painter.drawText(
                QRectF(0, 15, 160, 20),
                Qt.AlignmentFlag.AlignCenter,
                "FANFICTION"
            )
        
        painter.end()
        return pixmap

    def _update_favorite_ui(self):
        color = self.theme.app("accent") if self.is_favorite else "rgba(255, 255, 255, 0.6)"
        self.fav_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0, 0, 0, 0.4);
                color: {color};
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 0.6);
                color: {self.theme.app("accent")};
            }}
        """)

    def _on_toggle_favorite(self):
        from storage.repositories import BookRepository
        new_fav = BookRepository().toggle_favorite(self.book_id)
        self.is_favorite = new_fav
        self._update_favorite_ui()

    def _show_add_to_collection_menu(self):
        from PyQt6.QtWidgets import QMenu
        from storage.repositories import CollectionRepository

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {self.theme.app('card_bg')};
                color: {self.theme.app('text_primary')};
                border: 1px solid {self.theme.app('divider')};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background: {self.theme.app('sidebar_hover')};
            }}
        """)

        collections = CollectionRepository().get_all()
        for col in collections:
            a = menu.addAction(f"{col['icon']}  {col['name']}")
            a.setData(col["id"])

        pos = self.add_action_btn.mapToGlobal(QPoint(0, self.add_action_btn.height()))
        action = menu.exec(pos)
        if action:
            col_id = action.data()
            if col_id:
                CollectionRepository().add_book(self.book_id, col_id)

    # ── Interaction ────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._selection_mode:
            if event.button() == Qt.MouseButton.LeftButton:
                self._selected = not self._selected
                self._update_selection_ui()
                self.selection_toggled.emit(self.book_id, self._selected)
            return

        if event.button() == Qt.MouseButton.LeftButton and not self.is_missing:
            # Check if click was inside buttons to avoid opening book twice
            if not self.fav_btn.geometry().contains(event.pos()):
                self.open_requested.emit(self.book_id)

    def mouseMoveEvent(self, event):
        if self._selection_mode:
            return
        if event.buttons() == Qt.MouseButton.LeftButton:
            drag      = QDrag(self)
            mime      = QMimeData()
            mime.setText(self.book_id)
            drag.setMimeData(mime)

            pixmap = self.grab().scaled(
                80, 130,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
            drag.exec(Qt.DropAction.MoveAction)

    def enterEvent(self, event):
        self._set_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hover(False)
        super().leaveEvent(event)

    def _set_hover(self, hovered: bool):
        bg = self.theme.app("card_hover") if hovered else self.theme.app("card_bg")
        border = self.theme.app("accent") if hovered else self.theme.app("card_border")
        self.setStyleSheet(
            f"BookCard {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; }}"
        )

        if not self.is_missing and hasattr(self, "opacity_effect"):
            if hasattr(self, "_overlay_anim"):
                self._overlay_anim.stop()

            target_opacity = 0.0 if self._selection_mode else (0.95 if hovered else 0.0)
            self._overlay_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
            self._overlay_anim.setDuration(150)
            self._overlay_anim.setStartValue(self.opacity_effect.opacity())
            self._overlay_anim.setEndValue(target_opacity)
            self._overlay_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._overlay_anim.start()

    def set_selection_mode(self, enabled: bool, selected: bool):
        self._selection_mode = enabled
        self._selected = selected
        self.selection_badge.setVisible(enabled)
        if enabled:
            self._update_selection_ui()

    def _update_selection_ui(self):
        if self._selected:
            self.selection_badge.setText("✓")
            self.selection_badge.setStyleSheet(f"""
                QLabel {{
                    background: {self.theme.app('accent')};
                    color: #FFFFFF;
                    border: 1px solid {self.theme.app('accent')};
                    border-radius: 10px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """)
        else:
            self.selection_badge.setText("")
            self.selection_badge.setStyleSheet(f"""
                QLabel {{
                    background: rgba(0, 0, 0, 0.4);
                    color: transparent;
                    border: 1.5px solid rgba(255, 255, 255, 0.8);
                    border-radius: 10px;
                }}
            """)

    def contextMenuEvent(self, event):
        if self._selection_mode:
            event.accept()
            return

        from PyQt6.QtWidgets import QMenu
        from storage.repositories import CollectionRepository

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {self.theme.app('card_bg')};
                color: {self.theme.app('text_primary')};
                border: 1px solid {self.theme.app('divider')};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background: {self.theme.app('sidebar_hover')};
            }}
            QMenu::separator {{
                height: 1px;
                background: {self.theme.app('divider')};
                margin: 4px 8px;
            }}
        """)

        open_action     = menu.addAction("Open")
        menu.addSeparator()

        col_menu = menu.addMenu("Add to Collection")
        col_menu.setStyleSheet(menu.styleSheet())
        collections = CollectionRepository().get_all()
        for col in collections:
            a = col_menu.addAction(f"{col['icon']}  {col['name']}")
            a.setData(col["id"])

        menu.addSeparator()
        fetch_action    = menu.addAction("Fetch Metadata")
        convert_action  = menu.addAction("Convert...")
        menu.addSeparator()
        remove_action   = menu.addAction("Remove from Library")

        action = menu.exec(event.globalPos())
        if not action:
            return

        if action == open_action:
            if not self.is_missing:
                self.open_requested.emit(self.book_id)

        elif action.parent() == col_menu:
            col_id = action.data()
            if col_id:
                CollectionRepository().add_book(self.book_id, col_id)

        elif action == fetch_action:
            self.fetch_metadata_requested.emit(self.book_id)

        elif action == convert_action:
            self.convert_requested.emit(self.book_id)

        elif action == remove_action:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Remove Book",
                f"Remove '{self.book_row['title']}' from library?\n"
                f"The file will not be deleted.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                from storage.repositories import BookRepository
                BookRepository().delete(self.book_id)
                self.removed.emit(self.book_id)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _truncate(self, text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[:max_len - 1] + "…"

    def _apply_theme(self):
        self.setStyleSheet(
            f"BookCard {{ background: {self.theme.app('card_bg')}; "
            f"border: 1px solid {self.theme.app('card_border')}; border-radius: 8px; }}"
        )