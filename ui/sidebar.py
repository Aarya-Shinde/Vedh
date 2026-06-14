from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpacerItem,
    QSizePolicy, QScrollArea, QInputDialog,
    QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QMimeData, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QCursor, QDrag, QColor

from core.theme_manager import ThemeManager
from storage.repositories import CollectionRepository


# ── Top nav items ──────────────────────────────────────────────────────────

NAV_ITEMS = [
    ("home",       "Home",       ""),
    ("library",    "Library",    ""),
    ("statistics", "Statistics", ""),
    ("settings",   "Settings",   ""),
]


# ── Nav button ─────────────────────────────────────────────────────────────

class NavButton(QPushButton):

    def __init__(self, icon: str, label: str, theme: ThemeManager):
        super().__init__()
        self.theme      = theme
        self._active    = False
        self._collapsed = False

        self.setFixedHeight(40)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 16, 0)

        self.icon_label = QLabel(icon)
        self.icon_label.setFixedWidth(20)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 16px; background: transparent;")

        self.text_label = QLabel(label)
        self.text_label.setStyleSheet(
            f"font-size: 14px; font-weight: 500; "
            f"color: {theme.app('sidebar_text')}; background: transparent;"
        )

        if not icon or icon == "•":
            self.icon_label.hide()
            layout.setSpacing(0)
        else:
            layout.setSpacing(12)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()

        self._refresh_style()

    def set_active(self, active: bool):
        self._active = active
        self._refresh_style()

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        if collapsed:
            self.text_label.hide()
            self.setToolTip(self.text_label.text())
        else:
            self.text_label.show()
            self.setToolTip("")
        self._refresh_style()

    def _refresh_style(self):
        t = self.theme
        if self._active:
            bg     = t.app("sidebar_hover")
            color  = t.app("sidebar_text_active")
        else:
            bg     = "transparent"
            color  = t.app("sidebar_text")

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: none;
                border-radius: 8px;
                margin: 2px 10px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {t.app('sidebar_hover')};
            }}
        """)
        self.text_label.setStyleSheet(
            f"font-size: 14px; font-weight: 500; "
            f"color: {color}; background: transparent;"
        )


# ── Collection drop target ─────────────────────────────────────────────────

class CollectionItem(QWidget):
    """
    A collection row in the sidebar.
    Accepts book card drops.
    Emits clicked and drop signals.
    """

    clicked      = pyqtSignal(str)        # collection_id
    book_dropped = pyqtSignal(str, str)   # book_id, collection_id

    def __init__(
        self,
        collection_id: str,
        name:  str,
        icon:  str,
        theme: ThemeManager,
        is_default: bool = False,
    ):
        super().__init__()
        self.collection_id = collection_id
        self.theme         = theme
        self.is_default    = is_default
        self._active       = False
        self._hovered      = False
        self._drop_hover   = False
        self._collapsed    = False

        self.setFixedHeight(38)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 12, 0)

        self.icon_label = QLabel(icon)
        self.icon_label.setFixedWidth(18)
        self.icon_label.setStyleSheet("font-size: 14px; background: transparent;")

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(
            f"font-size: 13px; color: {theme.app('sidebar_text')}; "
            f"background: transparent;"
        )

        if not icon or icon == "•":
            self.icon_label.hide()
            layout.setSpacing(0)
        else:
            layout.setSpacing(10)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.name_label)
        layout.addStretch()

        self._refresh_style()

    def set_active(self, active: bool):
        self._active = active
        self._refresh_style()

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        if collapsed:
            self.name_label.hide()
            self.setToolTip(self.name_label.text())
            self.layout().setContentsMargins(17, 0, 17, 0)
        else:
            self.name_label.show()
            self.setToolTip("")
            self.layout().setContentsMargins(20, 0, 12, 0)
        self._refresh_style()

    def set_name(self, name: str):
        self.name_label.setText(name)

    # ── Mouse ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.collection_id)

    def contextMenuEvent(self, event):
        if self.is_default:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {self.theme.app('card_bg')};
                color: {self.theme.app('text_primary')};
                border: 1px solid {self.theme.app('divider')};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item:selected {{
                background: {self.theme.app('sidebar_hover')};
                border-radius: 4px;
            }}
        """)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        action = menu.exec(event.globalPos())
        if action == rename_action:
            self._on_rename()
        elif action == delete_action:
            self._on_delete()

    def _on_rename(self):
        name, ok = QInputDialog.getText(
            self, "Rename Collection",
            "New name:", text=self.name_label.text()
        )
        if ok and name.strip():
            CollectionRepository().rename(self.collection_id, name.strip())
            self.set_name(name.strip())

    def _on_delete(self):
        CollectionRepository().delete(self.collection_id)
        self.setParent(None)
        self.deleteLater()

    # ── Drag and drop ──────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            self._drop_hover = True
            self._refresh_style()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drop_hover = False
        self._refresh_style()

    def dropEvent(self, event):
        self._drop_hover = False
        self._refresh_style()
        book_id = event.mimeData().text()
        if book_id:
            self.book_dropped.emit(book_id, self.collection_id)
            event.acceptProposedAction()

    # ── Style ──────────────────────────────────────────────────────────────

    def _refresh_style(self):
        t = self.theme
        if self._drop_hover:
            bg     = t.app("accent")
            border = f"border-left: 3px solid {t.app('accent_hover')};"
        elif self._active:
            bg     = t.app("sidebar_hover")
            border = f"border-left: 3px solid {t.app('sidebar_accent')};"
        else:
            bg     = "transparent"
            border = "border-left: 3px solid transparent;"

        self.setStyleSheet(f"""
            CollectionItem {{
                background: {bg};
                {border}
            }}
            CollectionItem:hover {{
                background: {t.app('sidebar_hover')};
            }}
        """)
        color = (
            t.app("sidebar_text_active")
            if self._active or self._drop_hover
            else t.app("sidebar_text")
        )
        self.name_label.setStyleSheet(
            f"font-size: 13px; color: {color}; background: transparent;"
        )


# ── Sidebar ────────────────────────────────────────────────────────────────

class Sidebar(QWidget):

    nav_clicked        = pyqtSignal(int)     # page index
    collection_clicked = pyqtSignal(str)     # collection_id
    book_dropped       = pyqtSignal(str, str) # book_id, collection_id

    def __init__(self, theme: ThemeManager):
        super().__init__()
        self.theme          = theme
        self._nav_buttons:  list[NavButton]      = []
        self._col_items:    list[CollectionItem] = []
        self._active_nav    = 0
        self._active_col_id: str | None          = None
        self._collapsed     = False

        self.setMinimumWidth(200)
        self.setMaximumWidth(200)
        self._build_ui()
        self._apply_theme()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # App title + Collapse Button
        header = QWidget()
        header.setFixedHeight(60)
        self.header_layout = QHBoxLayout(header)
        self.header_layout.setContentsMargins(24, 0, 8, 0)
        
        self.title = QLabel()
        self.title.setStyleSheet("background: transparent;")
        self.header_layout.addWidget(self.title)
        
        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setFixedSize(24, 24)
        self.toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggle_btn.clicked.connect(self.toggle_collapse)
        self.header_layout.addWidget(self.toggle_btn)
        
        outer.addWidget(header)

        self.div1 = self._divider()
        outer.addWidget(self.div1)

        outer.addSpacing(6)

        # Nav buttons
        for i, (key, label, icon) in enumerate(NAV_ITEMS):
            btn = NavButton(icon, label, self.theme)
            btn.clicked.connect(lambda checked, idx=i: self._on_nav(idx))
            self._nav_buttons.append(btn)
            outer.addWidget(btn)

        outer.addSpacing(12)
        self.div2 = self._divider()
        outer.addWidget(self.div2)

        # Collections section header
        self.col_header = QWidget()
        self.col_header.setFixedHeight(32)
        chl = QHBoxLayout(self.col_header)
        chl.setContentsMargins(24, 0, 12, 0)
        self.col_label = QLabel("Collections")
        self.col_label.setStyleSheet(
            f"font-size: 11px; font-weight: 600; "
            f"text-transform: uppercase; letter-spacing: 1px; "
            f"color: {self.theme.app('text_muted')};"
        )
        chl.addWidget(self.col_label)
        chl.addStretch()
        outer.addWidget(self.col_header)

        # Scrollable collection list
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._col_container = QWidget()
        self._col_container.setStyleSheet("background: transparent;")
        self._col_layout = QVBoxLayout(self._col_container)
        self._col_layout.setContentsMargins(0, 0, 0, 0)
        self._col_layout.setSpacing(0)

        self._load_collections()

        # Add new collection button
        self.add_btn = QPushButton("  ＋  New Collection")
        self.add_btn.setFixedHeight(36)
        self.add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.add_btn.clicked.connect(self._on_add_collection)
        self._col_layout.addWidget(self.add_btn)
        self._col_layout.addStretch()

        self.scroll_area.setWidget(self._col_container)
        outer.addWidget(self.scroll_area)

        # Version
        self.version = QLabel("v0.1.0")
        self.version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version.setStyleSheet(
            f"font-size: 11px; color: {self.theme.app('text_muted')}; padding: 10px;"
        )
        outer.addWidget(self.version)

        # Gradient overlay at bottom
        self.gradient_overlay = QWidget(self)
        self.gradient_overlay.setFixedHeight(24)
        self.gradient_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._update_overlay_visibility)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._update_overlay_visibility)

        # Set home active by default
        self._nav_buttons[0].set_active(True)
        self._style_add_btn(False)
        self._update_overlay_visibility()

    def _load_collections(self):
        # Clear existing items
        for item in self._col_items:
            item.setParent(None)
            item.deleteLater()
        self._col_items.clear()

        collections = CollectionRepository().get_all()
        for col in collections:
            item = CollectionItem(
                collection_id = col["id"],
                name          = col["name"],
                icon          = col["icon"],
                theme         = self.theme,
                is_default    = bool(col["is_default"]),
            )
            item.clicked.connect(self._on_collection_clicked)
            item.book_dropped.connect(self._on_book_dropped)
            item.set_collapsed(self._collapsed)
            self._col_items.append(item)

            count = self._col_layout.count()
            self._col_layout.insertWidget(count - 2 if count >= 2 else count, item)

    # ── Signals & Collapsible ──────────────────────────────────────────────

    def toggle_collapse(self):
        self._collapsed = not self._collapsed
        
        # UI adjustments before/during collapse
        self.title.setVisible(not self._collapsed)
        self.col_header.setVisible(not self._collapsed)
        self.toggle_btn.setText("▶" if self._collapsed else "◀")
        self.version.setText("" if self._collapsed else "v0.1.0")

        if self._collapsed:
            self.header_layout.setContentsMargins(0, 0, 0, 0)
            self.header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.header_layout.setContentsMargins(20, 0, 8, 0)
            self.header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        for btn in self._nav_buttons:
            btn.set_collapsed(self._collapsed)

        for item in self._col_items:
            item.set_collapsed(self._collapsed)

        self._style_add_btn(self._collapsed)

        # Animation (200ms duration)
        start_w = 52 if self._collapsed else 200
        end_w   = 200 if self._collapsed else 52
        # Start width is current width
        start_w = self.width()
        end_w   = 52 if self._collapsed else 200

        self._anim = QPropertyAnimation(self, b"minimumWidth")
        self._anim.setDuration(200)
        self._anim.setStartValue(start_w)
        self._anim.setEndValue(end_w)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        self._anim_max.setDuration(200)
        self._anim_max.setStartValue(start_w)
        self._anim_max.setEndValue(end_w)
        self._anim_max.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._anim.start()
        self._anim_max.start()

    def _style_add_btn(self, collapsed: bool):
        t = self.theme
        if collapsed:
            self.add_btn.setText(" ＋")
            self.add_btn.setToolTip("New Collection")
            self.add_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t.app('text_muted')};
                    border: none;
                    text-align: center;
                    font-size: 14px;
                    padding-left: 0px;
                }}
                QPushButton:hover {{
                    color: {t.app('accent')};
                }}
            """)
        else:
            self.add_btn.setText("  ＋  New Collection")
            self.add_btn.setToolTip("")
            self.add_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t.app('text_muted')};
                    border: none;
                    text-align: left;
                    padding-left: 20px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    color: {t.app('accent')};
                    background: {t.app('sidebar_hover')};
                }}
            """)

    def _update_overlay_visibility(self):
        bar = self.scroll_area.verticalScrollBar()
        # If scrolled page range exists and we are not yet at the absolute bottom
        has_more = (bar.maximum() > 0 and bar.value() < bar.maximum())
        self.gradient_overlay.setVisible(has_more)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_overlay_geometry()

    def _update_overlay_geometry(self):
        if hasattr(self, "gradient_overlay") and hasattr(self, "scroll_area"):
            geom = self.scroll_area.geometry()
            self.gradient_overlay.setGeometry(
                geom.x(),
                geom.bottom() - 24,
                geom.width(),
                24
            )

    def _on_nav(self, index: int):
        self._nav_buttons[self._active_nav].set_active(False)
        self._active_nav = index
        self._nav_buttons[index].set_active(True)
        self._deactivate_collections()
        self.nav_clicked.emit(index)

    def _on_collection_clicked(self, collection_id: str):
        self._deactivate_collections()
        for btn in self._nav_buttons:
            btn.set_active(False)
        for item in self._col_items:
            if item.collection_id == collection_id:
                item.set_active(True)
                self._active_col_id = collection_id
                break
        self.collection_clicked.emit(collection_id)

    def _on_book_dropped(self, book_id: str, collection_id: str):
        self.book_dropped.emit(book_id, collection_id)

    def _on_add_collection(self):
        name, ok = QInputDialog.getText(
            self, "New Collection", "Collection name:"
        )
        if ok and name.strip():
            col_id = CollectionRepository().create(name.strip())
            self._load_collections()

    def _deactivate_collections(self):
        for item in self._col_items:
            item.set_active(False)
        self._active_col_id = None

    # ── Helpers & Theme ────────────────────────────────────────────────────

    def _divider(self) -> QWidget:
        div = QWidget()
        div.setFixedHeight(1)
        return div

    def _apply_theme(self):
        t = self.theme
        self.setStyleSheet(
            f"Sidebar {{ background: {t.app('sidebar_bg')}; "
            f"border-right: 1px solid {t.app('divider')}; }}"
        )
        
        # Stylish Logo: V (pink) + edh (primary text)
        v_color = "#E06D83"
        edh_color = t.app("text_primary")
        self.title.setText(
            f'<span style="color: {v_color}; font-family: \'Motterdam\'; font-weight: 800; font-size: 34px;">V</span>'
            f'<span style="color: {edh_color}; font-family: \'Motterdam\'; font-weight: 600; font-size: 26px; letter-spacing: 0.5px;">edh</span>'
        )
        
        self.div1.setStyleSheet(f"background: {t.app('divider')};")
        self.div2.setStyleSheet(f"background: {t.app('divider')};")
        
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #E06D83;
                border: none;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {t.app('accent_hover')};
            }}
        """)

        self.gradient_overlay.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 transparent,
                    stop:1 {t.app('sidebar_bg')}
                );
            }}
        """)

        self._style_add_btn(self._collapsed)
        self._update_overlay_visibility()