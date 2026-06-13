from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QSlider,
    QPushButton, QComboBox, QCheckBox,
    QSizePolicy, QSpacerItem, QLineEdit,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QCursor

from core.theme_manager import ThemeManager
from core.config_manager import ConfigManager


class SettingRow(QWidget):
    """Label + control side by side."""

    def __init__(self, label: str, control: QWidget, theme: ThemeManager):
        super().__init__()
        self.setFixedHeight(44)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(label)
        lbl.setFixedWidth(200)
        lbl.setStyleSheet(f"font-size: 13px; background: transparent;")
        layout.addWidget(lbl)
        layout.addWidget(control)


class SliderRow(QWidget):
    """Label + slider + value display."""

    value_changed = pyqtSignal(float)

    def __init__(
        self,
        label:   str,
        minimum: float,
        maximum: float,
        value:   float,
        step:    float,
        suffix:  str,
        theme:   ThemeManager,
    ):
        super().__init__()
        self.setFixedHeight(44)
        self._step = step
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        lbl = QLabel(label)
        lbl.setFixedWidth(200)
        lbl.setStyleSheet(f"font-size: 13px; background: transparent;")

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(int(minimum / step))
        self._slider.setMaximum(int(maximum / step))
        self._slider.setValue(int(value   / step))
        self._slider.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        formatted_val = f"{value:.1f}" if step == 0.1 else f"{int(value)}"
        self._val_label = QLabel(f"{formatted_val}{suffix}")
        self._val_label.setFixedWidth(54)
        self._val_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._val_label.setStyleSheet(f"font-size: 13px; background: transparent;")
        self._suffix = suffix

        self._slider.valueChanged.connect(self._on_change)

        layout.addWidget(lbl)
        layout.addWidget(self._slider, stretch=1)
        layout.addWidget(self._val_label)

    def _on_change(self, raw: int):
        val = raw * self._step
        formatted_val = f"{val:.1f}" if self._step == 0.1 else f"{int(val)}"
        self._val_label.setText(f"{formatted_val}{self._suffix}")
        self.value_changed.emit(val)

    def get_value(self) -> float:
        return self._slider.value() * self._step


class SectionHeader(QLabel):

    def __init__(self, text: str, theme: ThemeManager):
        super().__init__(text)
        self.setFixedHeight(36)
        self.setStyleSheet(
            f"font-size: 11px; font-weight: 600; "
            f"text-transform: uppercase; letter-spacing: 1px; "
            f"background: transparent; "
            f"padding-bottom: 4px;"
        )


class Divider(QWidget):
    def __init__(self, theme: ThemeManager):
        super().__init__()
        self.setFixedHeight(1)


class SettingsView(QWidget):

    # Emitted when settings change
    app_theme_changed    = pyqtSignal(str)
    reader_theme_changed = pyqtSignal(str)
    font_changed         = pyqtSignal(str)
    font_size_changed    = pyqtSignal(float)
    line_spacing_changed = pyqtSignal(float)
    page_width_changed   = pyqtSignal(float)
    margin_h_changed     = pyqtSignal(float)
    margin_v_changed     = pyqtSignal(float)
    profile_updated      = pyqtSignal()

    def __init__(self, theme: ThemeManager):
        super().__init__()
        self.theme = theme
        self._build_ui()
        self._apply_theme()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Clear layout if exists (used during rebuild)
        if self.layout():
            old_layout = self.layout()
            # Remove and delete widgets from layout to prevent floating widgets
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            QWidget().setLayout(old_layout)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        self.header_bar = QWidget()
        self.header_bar.setFixedHeight(54)
        bar_layout = QHBoxLayout(self.header_bar)
        bar_layout.setContentsMargins(32, 0, 32, 0)
        self.title_label = QLabel("Settings")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600; background: transparent;")
        bar_layout.addWidget(self.title_label)
        bar_layout.addStretch()

        self.reset_defaults_btn = QPushButton("Reset Defaults")
        self.reset_defaults_btn.setFixedHeight(28)
        self.reset_defaults_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.reset_defaults_btn.clicked.connect(self._on_reset_defaults)
        bar_layout.addWidget(self.reset_defaults_btn)

        outer.addWidget(self.header_bar)

        self.div_line = Divider(self.theme)
        outer.addWidget(self.div_line)

        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.content_widget = QWidget()
        self.content_widget.setObjectName("content")
        cl = QVBoxLayout(self.content_widget)
        cl.setContentsMargins(48, 32, 48, 48)
        cl.setSpacing(8)

        # 1. User Profile
        cl.addWidget(SectionHeader("User Profile", self.theme))
        cl.addSpacing(4)
        cl.addWidget(self._build_profile_card())
        cl.addSpacing(20)

        # 2. App Appearance
        cl.addWidget(SectionHeader("Appearance — App", self.theme))
        cl.addSpacing(4)
        cl.addWidget(self._build_app_theme_row())
        cl.addWidget(self._build_accent_row())
        cl.addSpacing(20)

        # 3. Reader Typography
        cl.addWidget(SectionHeader("Appearance — Reader Typography", self.theme))
        cl.addSpacing(4)
        cl.addWidget(self._build_reader_theme_row())
        cl.addWidget(self._build_font_row())
        cl.addWidget(self._build_font_size_row())
        cl.addWidget(self._build_line_spacing_row())
        cl.addSpacing(20)

        # 4. Reader Layout & Margins
        cl.addWidget(SectionHeader("Appearance — Reader Layout", self.theme))
        cl.addSpacing(4)
        cl.addWidget(self._build_page_width_row())
        cl.addWidget(self._build_margin_h_row())
        cl.addWidget(self._build_margin_v_row())
        cl.addSpacing(20)

        # 5. Library Preferences & Management
        cl.addWidget(SectionHeader("Library Management", self.theme))
        cl.addSpacing(4)
        cl.addWidget(self._build_auto_classify_row())
        cl.addWidget(self._build_auto_assign_row())
        cl.addWidget(self._build_recent_limit_row())
        cl.addWidget(self._build_management_actions())
        cl.addSpacing(20)

        # 6. About & Info
        cl.addWidget(SectionHeader("About & Diagnostics", self.theme))
        cl.addSpacing(4)
        cl.addWidget(self._build_about_section())

        cl.addStretch()
        self.scroll.setWidget(self.content_widget)
        outer.addWidget(self.scroll)

    # ── User Profile ───────────────────────────────────────────────────────

    def _build_profile_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("profile_card")
        
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        # Avatar circle with premium gradient
        username = ConfigManager().get("username", "Reader")
        initial = username[0].upper() if username else "R"
        
        avatar_container = QWidget()
        avatar_container.setFixedSize(60, 60)
        avatar_container.setObjectName("profile_avatar_container")
        
        avatar_layout = QVBoxLayout(avatar_container)
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        avatar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.avatar_label = QLabel(initial)
        self.avatar_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #FFFFFF; background: transparent;")
        avatar_layout.addWidget(self.avatar_label)
        
        layout.addWidget(avatar_container)

        # Info section
        info_col = QVBoxLayout()
        info_col.setSpacing(6)
        
        self.profile_title = QLabel(username)
        self.profile_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {self.theme.app('text_primary')};")
        
        sub = QLabel("Personalize your reader profile")
        sub.setStyleSheet(f"font-size: 11px; color: {self.theme.app('text_muted')};")
        
        info_col.addWidget(self.profile_title)
        info_col.addWidget(sub)
        
        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.setText(username)
        self.username_input.setFixedHeight(34)
        self.username_input.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {self.theme.app('divider')};
                border-radius: 6px;
                padding-left: 10px;
                font-size: 13px;
                background: {self.theme.app('window_bg')};
                color: {self.theme.app('text_primary')};
            }}
            QLineEdit:focus {{
                border-color: {self.theme.app('accent')};
            }}
        """)
        
        self.save_user_btn = QPushButton("Save")
        self.save_user_btn.setFixedHeight(34)
        self.save_user_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.save_user_btn.clicked.connect(self._on_save_profile)
        
        input_row.addWidget(self.username_input, stretch=1)
        input_row.addWidget(self.save_user_btn)
        
        info_col.addLayout(input_row)
        layout.addLayout(info_col, stretch=1)
        
        return card

    def _on_save_profile(self):
        new_name = self.username_input.text().strip()
        if new_name:
            ConfigManager().set("username", new_name)
            self.profile_updated.emit()
            if hasattr(self, "profile_title"):
                self.profile_title.setText(new_name)
            if hasattr(self, "avatar_label"):
                self.avatar_label.setText(new_name[0].upper() if new_name else "R")
            self.save_user_btn.setText("Saved ✓")
            QTimer.singleShot(1500, lambda: self.save_user_btn.setText("Save"))

    # ── App theme & Accent ──────────────────────────────────────────────────

    def _build_app_theme_row(self) -> QWidget:
        container = QWidget()
        layout    = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._theme_buttons = {}
        for name, label in [("dark", "Dark"), ("light", "Light")]:
            btn = QPushButton(label)
            btn.setFixedHeight(36)
            btn.setFixedWidth(100)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            layout.addWidget(btn)
            self._theme_buttons[name] = btn
            btn.clicked.connect(
                lambda checked, n=name: self._on_app_theme(n)
            )

        layout.addStretch()
        return container

    def _on_app_theme(self, name: str):
        self.app_theme_changed.emit(name)

    def _build_accent_row(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        accents = [
            ("Pink", "#E7717D"),
            ("Light Green", "#AFD275"),
            ("Brown", "#7E685A"),
            ("Light Gray", "#C2CAD0"),
            ("Beige-Gray", "#C2B9B0"),
        ]

        self.accent_buttons = {}
        for name, color in accents:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setToolTip(name)
            btn.clicked.connect(lambda checked, c=color: self._on_accent_changed(c))
            layout.addWidget(btn)
            self.accent_buttons[color] = btn

        layout.addStretch()
        return container

    def _on_accent_changed(self, color: str):
        self.theme._app_theme["accent"] = color
        self.theme._app_theme["sidebar_accent"] = color
        self.theme._app_theme["sidebar_text_active"] = color
        self.theme._app_theme["scrollbar_hover"] = color

        self.app_theme_changed.emit(self.theme._app_theme_name)

    def _update_accent_buttons(self):
        if not hasattr(self, "accent_buttons"):
            return
        current_accent = self.theme.app("accent").upper()
        for color, btn in self.accent_buttons.items():
            is_active = (color.upper() == current_accent)
            border_style = f"2.5px solid {self.theme.app('text_primary')}" if is_active else "1px solid rgba(0,0,0,0.15)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: {border_style};
                    border-radius: 14px;
                }}
            """)

    def _update_theme_buttons(self):
        if not hasattr(self, "_theme_buttons"):
            return
        for name, btn in self._theme_buttons.items():
            is_active = (name == self.theme._app_theme_name)
            self._style_toggle(btn, is_active)

    # ── Reader theme ───────────────────────────────────────────────────────

    def _build_reader_theme_row(self) -> SettingRow:
        combo = QComboBox()
        combo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        for name in self.theme.available_reader_themes():
            combo.addItem(name.title(), name)
        combo.setCurrentText(self.theme._reader_theme_name.title())
        combo.setStyleSheet(self._combo_style())
        combo.currentIndexChanged.connect(
            lambda i: self.reader_theme_changed.emit(combo.itemData(i))
        )
        return SettingRow("Reader Theme", combo, self.theme)

    # ── Typography ─────────────────────────────────────────────────────────

    def _build_font_row(self) -> SettingRow:
        combo = QComboBox()
        combo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        fonts = [
            ("Lora (Bundled)", "Lora"),
            ("Georgia",      "Georgia"),
            ("Merriweather", "Merriweather"),
            ("Segoe UI",     "Segoe UI"),
            ("Arial",        "Arial"),
            ("Times New Roman", "Times New Roman"),
        ]
        for label, val in fonts:
            combo.addItem(label, val)
        combo.setCurrentText(self.theme.reader("font_family", "Georgia"))
        combo.setStyleSheet(self._combo_style())
        combo.currentIndexChanged.connect(
            lambda i: self.font_changed.emit(combo.itemData(i))
        )
        return SettingRow("Font Family", combo, self.theme)

    def _build_font_size_row(self) -> SliderRow:
        row = SliderRow(
            "Font Size",
            minimum=12, maximum=36,
            value=float(self.theme.reader("font_size", 18)),
            step=1, suffix="pt",
            theme=self.theme,
        )
        row.value_changed.connect(self.font_size_changed.emit)
        return row

    def _build_line_spacing_row(self) -> SliderRow:
        row = SliderRow(
            "Line Spacing",
            minimum=1.0, maximum=3.0,
            value=float(self.theme.reader("line_spacing", 1.6)),
            step=0.1, suffix="x",
            theme=self.theme,
        )
        row.value_changed.connect(self.line_spacing_changed.emit)
        return row

    # ── Reader Layout & Margins ────────────────────────────────────────────

    def _build_page_width_row(self) -> SliderRow:
        row = SliderRow(
            "Page Width",
            minimum=400, maximum=1000,
            value=float(self.theme.reader("page_width", 750)),
            step=10, suffix="px",
            theme=self.theme,
        )
        row.value_changed.connect(self.page_width_changed.emit)
        return row

    def _build_margin_h_row(self) -> SliderRow:
        row = SliderRow(
            "Horizontal Margin",
            minimum=20, maximum=150,
            value=float(self.theme.reader("margin_h", 48.0)),
            step=2, suffix="px",
            theme=self.theme,
        )
        row.value_changed.connect(self.margin_h_changed.emit)
        return row

    def _build_margin_v_row(self) -> SliderRow:
        row = SliderRow(
            "Vertical Margin",
            minimum=20, maximum=120,
            value=float(self.theme.reader("margin_v", 40.0)),
            step=2, suffix="px",
            theme=self.theme,
        )
        row.value_changed.connect(self.margin_v_changed.emit)
        return row

    # ── Library Preferences & Management ───────────────────────────────────

    def _build_auto_classify_row(self) -> SettingRow:
        self.auto_classify_chk = QCheckBox()
        self.auto_classify_chk.setChecked(ConfigManager().get("auto_classify", True))
        self.auto_classify_chk.stateChanged.connect(
            lambda state: ConfigManager().set("auto_classify", self.auto_classify_chk.isChecked())
        )
        lbl_widget = QWidget()
        lbl_layout = QHBoxLayout(lbl_widget)
        lbl_layout.setContentsMargins(0, 0, 0, 0)
        lbl_layout.addWidget(self.auto_classify_chk)
        lbl_layout.addWidget(QLabel("Enabled"))
        lbl_layout.addStretch()
        return SettingRow("Auto-classify on import", lbl_widget, self.theme)

    def _build_auto_assign_row(self) -> SettingRow:
        self.auto_assign_chk = QCheckBox()
        self.auto_assign_chk.setChecked(ConfigManager().get("auto_assign", True))
        self.auto_assign_chk.stateChanged.connect(
            lambda state: ConfigManager().set("auto_assign", self.auto_assign_chk.isChecked())
        )
        lbl_widget = QWidget()
        lbl_layout = QHBoxLayout(lbl_widget)
        lbl_layout.setContentsMargins(0, 0, 0, 0)
        lbl_layout.addWidget(self.auto_assign_chk)
        lbl_layout.addWidget(QLabel("Enabled"))
        lbl_layout.addStretch()
        return SettingRow("Auto-assign collections", lbl_widget, self.theme)

    def _build_recent_limit_row(self) -> SettingRow:
        combo = QComboBox()
        combo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        for val in [4, 6, 8, 10, 12]:
            combo.addItem(f"{val} Books", val)
        
        current_limit = ConfigManager().get("recently_added_limit", 4)
        combo.setCurrentIndex(combo.findData(current_limit))
        combo.setStyleSheet(self._combo_style())
        combo.currentIndexChanged.connect(
            lambda i: self._on_recent_limit_changed(combo.itemData(i))
        )
        return SettingRow("Recently Added Limit", combo, self.theme)

    def _on_recent_limit_changed(self, val: int):
        ConfigManager().set("recently_added_limit", val)
        self.profile_updated.emit()

    def _build_management_actions(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(16)

        self.clear_stats_btn = QPushButton("Clear Reading Statistics")
        self.clear_stats_btn.setFixedHeight(34)
        self.clear_stats_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.clear_stats_btn.clicked.connect(self._on_clear_stats)
        layout.addWidget(self.clear_stats_btn)

        self.reset_db_btn = QPushButton("Delete All Books")
        self.reset_db_btn.setFixedHeight(34)
        self.reset_db_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.reset_db_btn.clicked.connect(self._on_reset_db)
        layout.addWidget(self.reset_db_btn)

        layout.addStretch()
        return container

    def _on_reset_db(self):
        reply = QMessageBox.warning(
            self,
            "Delete All Books",
            "Are you sure you want to delete all books and collections? This action is permanent and cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from storage.database import get_connection
                conn = get_connection()
                with conn:
                    conn.execute("DELETE FROM books")
                    conn.execute("DELETE FROM collections WHERE is_default = 0")
                conn.close()
                QMessageBox.information(self, "Success", "All books and collections have been deleted successfully.")
                self.profile_updated.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to reset database: {e}")

    def _on_clear_stats(self):
        reply = QMessageBox.warning(
            self,
            "Clear Reading Statistics",
            "Are you sure you want to clear your reading statistics and history? Your imported books will remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from storage.database import get_connection
                conn = get_connection()
                with conn:
                    conn.execute("DELETE FROM reading_sessions")
                    conn.execute("DELETE FROM reading_progress")
                conn.close()
                QMessageBox.information(self, "Success", "Reading statistics cleared successfully.")
                self.profile_updated.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear statistics: {e}")

    # ── About ──────────────────────────────────────────────────────────────

    def _build_about_section(self) -> QWidget:
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        def info_row(label, value):
            w  = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label)
            lbl.setFixedWidth(200)
            lbl.setStyleSheet(f"font-size: 13px; background: transparent;")
            val = QLabel(value)
            val.setStyleSheet(f"font-size: 13px; background: transparent;")
            hl.addWidget(lbl)
            hl.addWidget(val)
            hl.addStretch()
            return w

        layout.addWidget(info_row("Application",  "Vedh — The Premium E-Reader"))
        layout.addWidget(info_row("Version",       "1.0.0"))
        layout.addWidget(info_row("Python",        __import__('sys').version.split()[0]))
        layout.addWidget(info_row("PyQt6",         __import__('PyQt6.QtCore', fromlist=['PYQT_VERSION_STR']).PYQT_VERSION_STR))

        # Open config folder button
        self.open_btn = QPushButton("Open Config Folder")
        self.open_btn.setFixedHeight(34)
        self.open_btn.setFixedWidth(160)
        self.open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.open_btn.clicked.connect(self._open_config_folder)
        layout.addWidget(self.open_btn)

        return container

    def _open_config_folder(self):
        import subprocess, sys
        from pathlib import Path
        folder = str(Path.home() / ".vedh")
        Path(folder).mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", folder])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    # ── Styling helpers ────────────────────────────────────────────────────

    def _style_toggle(self, btn: QPushButton, active: bool):
        t = self.theme
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t.app('accent')};
                    color: #FFFFFF;
                    border: none;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 500;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t.app('text_secondary')};
                    border: 1px solid {t.app('divider')};
                    border-radius: 6px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background: {t.app('sidebar_hover')};
                    color: {t.app('text_primary')};
                }}
            """)

    def _combo_style(self) -> str:
        return ""

    def _apply_theme(self):
        t = self.theme
        self.setStyleSheet(f"""
            SettingsView {{
                background: {t.app('window_bg')};
            }}
            QScrollArea {{
                border: none;
                background: {t.app('window_bg')};
            }}
            QWidget#content {{
                background: {t.app('window_bg')};
            }}
            QLabel {{
                color: {t.app('text_primary')};
                background: transparent;
            }}
            Divider {{
                background: {t.app('divider')};
            }}
            SectionHeader {{
                color: {t.app('text_muted')};
                border-bottom: 1px solid {t.app('divider')};
            }}
            QWidget#profile_card {{
                background: {t.app('card_bg')};
                border: 1px solid {t.app('divider')};
                border-radius: 8px;
            }}
            QLineEdit {{
                background: {t.app('window_bg')};
                color: {t.app('text_primary')};
                border: 1px solid {t.app('divider')};
                border-radius: 6px;
                font-size: 13px;
            }}
            QComboBox {{
                background: {t.app('card_bg')};
                color: {t.app('text_primary')};
                border: 1px solid {t.app('divider')};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 13px;
                min-width: 180px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background: {t.app('card_bg')};
                color: {t.app('text_primary')};
                border: 1px solid {t.app('divider')};
                selection-background-color: {t.app('sidebar_hover')};
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border-radius: 4px;
                border: 1px solid {t.app('divider')};
                background: {t.app('card_bg')};
            }}
            QCheckBox::indicator:checked {{
                background: {t.app('accent')};
                border-color: {t.app('accent')};
            }}
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

        # Style save button specifically
        if hasattr(self, "save_user_btn"):
            self.save_user_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t.app('accent')};
                    color: #FFFFFF;
                    border: none;
                    border-radius: 6px;
                    padding: 0 16px;
                    font-weight: 500;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {t.app('accent_hover')};
                }}
            """)

        # Style dangerous reset button
        if hasattr(self, "reset_db_btn"):
            self.reset_db_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t.app('danger', '#C0392B')};
                    border: 1px solid {t.app('danger', '#C0392B')};
                    border-radius: 6px;
                    padding: 0 16px;
                    font-weight: 500;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {t.app('danger', '#C0392B')};
                    color: #FFFFFF;
                }}
            """)

        # Style warning stats button
        if hasattr(self, "clear_stats_btn"):
            self.clear_stats_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t.app('text_secondary')};
                    border: 1px solid {t.app('divider')};
                    border-radius: 6px;
                    padding: 0 16px;
                    font-weight: 500;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {t.app('sidebar_hover')};
                    color: {t.app('text_primary')};
                }}
            """)

        # Style open config folder button specifically
        if hasattr(self, "open_btn"):
            self.open_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t.app('accent')};
                    border: 1px solid {t.app('accent')};
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: {t.app('accent')};
                    color: #FFFFFF;
                }}
            """)

        # Style reset defaults button
        if hasattr(self, "reset_defaults_btn"):
            self.reset_defaults_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t.app('text_secondary')};
                    border: 1px solid {t.app('divider')};
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    color: {t.app('accent')};
                    border-color: {t.app('accent')};
                }}
            """)

        self._update_accent_buttons()
        self._update_theme_buttons()

    def _on_reset_defaults(self):
        reply = QMessageBox.question(
            self,
            "Reset Defaults",
            "Are you sure you want to reset all theme, typography, and layout settings to their defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            cfg = ConfigManager()
            cfg.set("app_theme", "dark")
            cfg.set("reader_theme", "default")
            cfg.set("font_family", "Georgia")
            cfg.set("font_size", 18.0)
            cfg.set("line_spacing", 1.6)
            cfg.set("page_width", 750.0)
            cfg.set("margin_h", 48.0)
            cfg.set("margin_v", 40.0)
            cfg.set("auto_classify", True)
            cfg.set("auto_assign", True)

            # Apply defaults to theme
            self.theme.load_defaults()

            # Emit all changes
            self.app_theme_changed.emit("dark")
            self.reader_theme_changed.emit("default")
            self.font_changed.emit("Georgia")
            self.font_size_changed.emit(18.0)
            self.line_spacing_changed.emit(1.6)
            self.page_width_changed.emit(750.0)
            self.margin_h_changed.emit(48.0)
            self.margin_v_changed.emit(40.0)

            # Rebuild widgets with default values
            self._build_ui()
            self._apply_theme()

            QMessageBox.information(self, "Success", "Settings have been reset to defaults.")