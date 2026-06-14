from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar,
    QScrollArea, QWidget, QLineEdit,
    QTextEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QCursor

from core.theme_manager import ThemeManager
from core.metadata_fetcher import MetadataFetcher, FetchedMetadata
from storage.repositories import BookRepository, TagRepository


# ── Worker thread ──────────────────────────────────────────────────────────

class FetchWorker(QThread):

    progress = pyqtSignal(str, int)     # step, pct
    finished = pyqtSignal(object)       # FetchedMetadata
    failed   = pyqtSignal(str)

    def __init__(self, title: str, author: str, book_type: str = "unknown", file_path: str = "", format: str = ""):
        super().__init__()
        self._title  = title
        self._author = author
        self._book_type = book_type
        self._file_path = file_path
        self._format = format

    def run(self):
        try:
            fetcher = MetadataFetcher()
            result  = fetcher.fetch(
                self._title, self._author, book_type=self._book_type,
                file_path=self._file_path, format=self._format,
                on_progress=lambda s, p: self.progress.emit(s, p)
            )
            self.finished.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


# ── Dialog ─────────────────────────────────────────────────────────────────

class MetadataDialog(QDialog):

    def __init__(self, book_row, theme: ThemeManager, parent=None):
        super().__init__(parent)
        self.book_row  = book_row
        self.theme     = theme
        self._result: FetchedMetadata | None = None
        self._worker:  FetchWorker    | None = None

        self.setWindowTitle("Fetch Metadata")
        self.setFixedSize(560, 580)
        self.setModal(True)

        self._build_ui()
        self._apply_theme()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel("Fetch Metadata")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')};"
        )
        layout.addWidget(title)

        # Book Type selector (Always Visible)
        from PyQt6.QtWidgets import QComboBox
        type_row = QHBoxLayout()
        type_row.setSpacing(12)
        type_lbl = QLabel("Book Type:")
        type_lbl.setStyleSheet(f"font-size: 13px; color: {self.theme.app('text_secondary')};")

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Published", "Fanfic", "Manga", "Comic", "Unknown"])

        curr_type = "unknown"
        if "book_type" in self.book_row.keys():
            curr_type = (self.book_row["book_type"] or "unknown").lower()
        idx = self.type_combo.findText(curr_type.title())
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        else:
            self.type_combo.setCurrentIndex(4) # Unknown

        self.type_combo.setFixedHeight(30)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        type_row.addWidget(type_lbl)
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        layout.addLayout(type_row)

        # Search fields
        search_row = QHBoxLayout()
        title_val = self.book_row["title"] or ""
        if curr_type == "fanfic" and not (title_val.startswith("http://") or title_val.startswith("https://")):
            from core.metadata_fetcher import extract_fanfic_url
            extracted = extract_fanfic_url(self.book_row["file_path"], self.book_row["format"])
            if extracted:
                title_val = extracted

        self._title_input = QLineEdit(title_val)
        self._title_input.setPlaceholderText("Book title or Fanfic URL (AO3/FF.net)")
        self._title_input.setStyleSheet(self._input_style())

        self._author_input = QLineEdit(self.book_row["author"] or "")
        self._author_input.setPlaceholderText("Author")
        self._author_input.setStyleSheet(self._input_style())

        self._fetch_btn = QPushButton("Search")
        self._fetch_btn.setFixedHeight(36)
        self._fetch_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._fetch_btn.clicked.connect(self._on_fetch)
        self._fetch_btn.setStyleSheet(self._accent_btn_style())

        search_row.addWidget(self._title_input,  stretch=2)
        search_row.addWidget(self._author_input, stretch=1)
        search_row.addWidget(self._fetch_btn)
        layout.addLayout(search_row)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {self.theme.app('divider')};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {self.theme.app('accent')};
                border-radius: 2px;
            }}
        """)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        # Status label
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"font-size: 12px; color: {self.theme.app('text_muted')};"
        )
        layout.addWidget(self._status)

        # Result area
        self._result_widget = self._build_result_widget()
        self._result_widget.hide()
        layout.addWidget(self._result_widget, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._cancel_btn.clicked.connect(self.reject)
        self._cancel_btn.setStyleSheet(self._ghost_btn_style())

        self._save_btn = QPushButton("Save Metadata")
        self._save_btn.setFixedHeight(36)
        self._save_btn.setEnabled(True)  # Enable by default to allow setting type without searching
        self._save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setStyleSheet(self._accent_btn_style())

        btn_row.addWidget(self._cancel_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

    def _build_result_widget(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Cover
        self._cover_label = QLabel()
        self._cover_label.setFixedSize(120, 170)
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_label.setStyleSheet(
            f"background: {self.theme.app('card_bg')}; "
            f"border: 1px solid {self.theme.app('divider')}; "
            f"border-radius: 6px;"
        )
        layout.addWidget(self._cover_label)

        # Fields
        fields = QVBoxLayout()
        fields.setSpacing(8)

        self._res_title  = self._result_row("Title",       fields)
        self._res_author = self._result_row("Author",      fields)
        self._res_pub    = self._result_row("Publisher",   fields)
        self._res_year   = self._result_row("Year",        fields)
        self._res_lang   = self._result_row("Language",    fields)
        self._res_pages  = self._result_row("Pages",       fields)
        self._res_isbn   = self._result_row("ISBN",        fields)

        # Description
        desc_lbl = QLabel("Description")
        desc_lbl.setStyleSheet(
            f"font-size: 11px; color: {self.theme.app('text_muted')};"
        )
        self._res_desc = QTextEdit()
        self._res_desc.setFixedHeight(60)
        self._res_desc.setReadOnly(True)
        self._res_desc.setStyleSheet(f"""
            QTextEdit {{
                background: {self.theme.app('card_bg')};
                color: {self.theme.app('text_secondary')};
                border: 1px solid {self.theme.app('divider')};
                border-radius: 4px;
                font-size: 12px;
                padding: 4px;
            }}
        """)
        fields.addWidget(desc_lbl)
        fields.addWidget(self._res_desc)
        fields.addStretch()

        layout.addLayout(fields, stretch=1)
        return widget

    def _result_row(self, label: str, parent_layout) -> QLabel:
        row = QWidget()
        rl  = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(70)
        lbl.setStyleSheet(
            f"font-size: 11px; color: {self.theme.app('text_muted')}; "
            f"background: transparent;"
        )
        val = QLabel("—")
        val.setStyleSheet(
            f"font-size: 13px; color: {self.theme.app('text_primary')}; "
            f"background: transparent;"
        )
        val.setWordWrap(True)

        rl.addWidget(lbl)
        rl.addWidget(val, stretch=1)
        parent_layout.addWidget(row)
        return val

    # ── Fetch ──────────────────────────────────────────────────────────────

    def _on_fetch(self):
        title  = self._title_input.text().strip()
        author = self._author_input.text().strip()
        selected_type = self.type_combo.currentText().lower()

        if selected_type == "fanfic" and not (title.startswith("http://") or title.startswith("https://")):
            from core.metadata_fetcher import extract_fanfic_url
            extracted = extract_fanfic_url(self.book_row["file_path"], self.book_row["format"])
            if extracted:
                title = extracted
                self._title_input.setText(extracted)

        if not title:
            return

        self._fetch_btn.setEnabled(False)
        self._progress_bar.show()
        self._progress_bar.setValue(0)
        self._result_widget.hide()
        self._save_btn.setEnabled(False)

        self._worker = FetchWorker(
            title, author, book_type=selected_type,
            file_path=self.book_row["file_path"],
            format=self.book_row["format"]
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, step: str, pct: int):
        self._status.setText(step)
        self._progress_bar.setValue(pct)

    def _on_finished(self, result: FetchedMetadata):
        self._result = result
        self._fetch_btn.setEnabled(True)
        self._progress_bar.hide()
        self._status.setText("Metadata found — review below.")
        self._populate_result(result)
        self._result_widget.show()
        self._save_btn.setEnabled(True)

    def _on_failed(self, error: str):
        self._fetch_btn.setEnabled(True)
        self._progress_bar.hide()
        self._status.setText(f"Failed: {error}")

    def _populate_result(self, r: FetchedMetadata):
        self._res_title.setText(r.title   or "—")
        self._res_author.setText(r.author or "—")
        self._res_pub.setText(r.publisher  or "—")
        self._res_year.setText(r.year      or "—")
        self._res_lang.setText(r.language  or "—")
        self._res_pages.setText(str(r.page_count) if r.page_count else "—")
        self._res_isbn.setText(r.isbn      or "—")
        self._res_desc.setPlainText(r.description or "")

        if r.cover_data:
            px = QPixmap()
            if px.loadFromData(r.cover_data):
                self._cover_label.setPixmap(px.scaled(
                    120, 170,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))

    # ── Save ───────────────────────────────────────────────────────────────

    def _on_save(self):
        book_id = self.book_row["id"]
        conn    = __import__(
            'storage.database', fromlist=['get_connection']
        ).get_connection()

        selected_type = self.type_combo.currentText().lower()

        r = self._result
        if r:
            cover_val = None
            if r.cover_data:
                from storage.repositories import save_cover_image
                cover_val = save_cover_image(book_id, r.cover_data)

            with conn:
                conn.execute("""
                    UPDATE books SET
                        title       = COALESCE(?, title),
                        author      = COALESCE(?, author),
                        publisher   = COALESCE(?, publisher),
                        description = COALESCE(?, description),
                        language    = COALESCE(?, language),
                        cover       = COALESCE(?, cover),
                        book_type   = ?,
                        updated_at  = datetime('now')
                    WHERE id = ?
                """, (
                    r.title,
                    r.author,
                    r.publisher,
                    r.description,
                    r.language,
                    cover_val,
                    selected_type,
                    book_id,
                ))
            conn.close()

            # Save tags
            tag_repo = TagRepository()
            for tag_name in r.tags:
                clean = tag_name.lower().strip()[:30]
                if clean:
                    tag_id = tag_repo.get_or_create(clean, is_auto=True)
                    tag_repo.add_to_book(book_id, tag_id)
        else:
            # Only update book_type
            with conn:
                conn.execute("""
                    UPDATE books SET
                        book_type   = ?,
                        updated_at  = datetime('now')
                    WHERE id = ?
                """, (selected_type, book_id))
            conn.close()

        self.accept()

    # ── Style ──────────────────────────────────────────────────────────────

    def _input_style(self) -> str:
        t = self.theme
        return f"""
            QLineEdit {{
                background: {t.app('card_bg')};
                color: {t.app('text_primary')};
                border: 1px solid {t.app('divider')};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 13px;
                height: 32px;
            }}
            QLineEdit:focus {{
                border-color: {t.app('accent')};
            }}
        """

    def _accent_btn_style(self) -> str:
        t = self.theme
        is_dark = "Dark" in t.app("name", "dark")
        primary_text = "#181614" if is_dark else "#FFFFFF"
        return f"""
            QPushButton {{
                background: {t.app('accent')};
                color: {primary_text};
                border: none;
                border-radius: 6px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {t.app('accent_hover')};
            }}
            QPushButton:disabled {{
                background: {t.app('divider')};
                color: {t.app('text_muted')};
            }}
        """

    def _ghost_btn_style(self) -> str:
        t = self.theme
        return f"""
            QPushButton {{
                background: transparent;
                color: {t.app('text_secondary')};
                border: 1px solid {t.app('divider')};
                border-radius: 6px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {t.app('sidebar_hover')};
                color: {t.app('text_primary')};
                border-color: {t.app('accent')};
            }}
        """

    def _apply_theme(self):
        t = self.theme
        self.setStyleSheet(
            f"MetadataDialog {{ background: {t.app('window_bg')}; }}"
        )
        if hasattr(self, "_fetch_btn"):
            self._fetch_btn.setStyleSheet(self._accent_btn_style())
        if hasattr(self, "_save_btn"):
            self._save_btn.setStyleSheet(self._accent_btn_style())
        if hasattr(self, "_cancel_btn"):
            self._cancel_btn.setStyleSheet(self._ghost_btn_style())

    def _on_type_changed(self, text):
        selected_type = text.lower()
        title_val = self._title_input.text().strip()
        if selected_type == "fanfic" and not (title_val.startswith("http://") or title_val.startswith("https://")):
            from core.metadata_fetcher import extract_fanfic_url
            extracted = extract_fanfic_url(self.book_row["file_path"], self.book_row["format"])
            if extracted:
                self._title_input.setText(extracted)