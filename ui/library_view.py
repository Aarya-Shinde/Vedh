from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea,
    QGridLayout, QFileDialog, QSizePolicy,
    QLineEdit, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont

from core.theme_manager import ThemeManager
from core.plugin_manager import PluginManager
from storage.repositories import BookRepository


SUPPORTED_FORMATS = (
    "Books (*.epub *.pdf *.txt *.html *.fb2);;"
    "Comics (*.cbz *.cbr *.cb7 *.cbt);;"
    "All supported files (*.epub *.pdf *.txt *.html *.fb2 *.cbz *.cbr)"
)


class LibraryView(QWidget):
    open_book_requested = pyqtSignal(str)   # emits book_id

    def __init__(self, theme: ThemeManager, plugins: PluginManager):
        super().__init__()
        self.theme = theme
        self.plugins = plugins
        self.repo = BookRepository()
        self._books = []
        self._selection_mode = False
        self._selected_books = set()

        self._build_ui()
        self._apply_theme()
        self._load_library()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        topbar = self._build_topbar()
        layout.addWidget(topbar)

        # Toolbar for search/sort/filter
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # Divider
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {self.theme.app('divider')};")
        layout.addWidget(div)

        # Scroll area for content
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setStyleSheet("QScrollArea { border: none; }")

        # Grid view container
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(24, 24, 24, 24)
        self.grid_layout.setSpacing(16)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll)

        # Empty state (shown when no books)
        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("Library")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')};"
        )
        bar_layout.addWidget(title)
        bar_layout.addStretch()

        # Selection controls container
        self.selection_bar = QWidget()
        self.selection_layout = QHBoxLayout(self.selection_bar)
        self.selection_layout.setContentsMargins(0, 0, 0, 0)
        self.selection_layout.setSpacing(8)

        self.delete_selected_btn = QPushButton("Delete Selected (0)")
        self.delete_selected_btn.setFixedHeight(34)
        self.delete_selected_btn.setEnabled(False)
        self.delete_selected_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_selected_btn.setStyleSheet(f"""
            QPushButton {{
                background: #C0392B;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 0 18px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: #A93226;
            }}
            QPushButton:disabled {{
                background: {self.theme.app('divider')};
                color: {self.theme.app('text_muted')};
            }}
        """)
        self.delete_selected_btn.clicked.connect(self._on_delete_selected)

        self.cancel_select_btn = QPushButton("Cancel")
        self.cancel_select_btn.setFixedHeight(34)
        self.cancel_select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_select_btn.setStyleSheet(self._ghost_btn_style())
        self.cancel_select_btn.clicked.connect(self._toggle_selection_mode)

        self.selection_layout.addWidget(self.delete_selected_btn)
        self.selection_layout.addWidget(self.cancel_select_btn)
        self.selection_bar.hide()

        # Regular controls container
        self.regular_bar = QWidget()
        self.regular_layout = QHBoxLayout(self.regular_bar)
        self.regular_layout.setContentsMargins(0, 0, 0, 0)
        self.regular_layout.setSpacing(8)

        self.select_btn = QPushButton("Select")
        self.select_btn.setFixedHeight(34)
        self.select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_btn.setStyleSheet(self._ghost_btn_style())
        self.select_btn.clicked.connect(self._toggle_selection_mode)

        self.import_btn = QPushButton("+ Import")
        self.import_btn.setFixedHeight(34)
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.theme.app('accent')};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 0 18px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.app('accent_hover')};
            }}
        """)
        self.import_btn.clicked.connect(self._on_import)

        self.regular_layout.addWidget(self.select_btn)
        self.regular_layout.addWidget(self.import_btn)

        bar_layout.addWidget(self.selection_bar)
        bar_layout.addWidget(self.regular_bar)

        return bar

    def _ghost_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {self.theme.app('text_secondary')};
                border: 1px solid {self.theme.app('divider')};
                border-radius: 6px;
                padding: 0 18px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.app('sidebar_hover')};
                color: {self.theme.app('text_primary')};
            }}
        """

    def _toggle_selection_mode(self):
        self._selection_mode = not self._selection_mode
        if not self._selection_mode:
            self._selected_books.clear()
        
        self.selection_bar.setVisible(self._selection_mode)
        self.regular_bar.setVisible(not self._selection_mode)
        self._update_cards_selection_state()

    def _on_card_selection_toggled(self, book_id: str, selected: bool):
        if selected:
            self._selected_books.add(book_id)
        else:
            self._selected_books.discard(book_id)
        self._update_cards_selection_state()

    def _update_cards_selection_state(self):
        self.delete_selected_btn.setText(f"Delete Selected ({len(self._selected_books)})")
        self.delete_selected_btn.setEnabled(len(self._selected_books) > 0)

        # Notify cards
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if hasattr(card, "set_selection_mode"):
                    is_selected = card.book_id in self._selected_books
                    card.set_selection_mode(self._selection_mode, is_selected)

    def _on_delete_selected(self):
        if not self._selected_books:
            return
        
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Delete Selected Books",
            f"Are you sure you want to delete the {len(self._selected_books)} selected books from the library?\n"
            f"The files on disk will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                for book_id in list(self._selected_books):
                    self.repo.delete(book_id)
                self._selected_books.clear()
                self._selection_mode = False
                self.selection_bar.hide()
                self.regular_bar.show()
                self._load_library()
                parent_win = self.window()
                if hasattr(parent_win, "home_view"):
                    parent_win.home_view.refresh()
                if hasattr(parent_win, "stats_view"):
                    parent_win.stats_view.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete books: {e}")

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(12)

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search books...")
        self.search_input.setFixedHeight(30)
        self.search_input.textChanged.connect(self._load_library)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {self.theme.app('card_bg')};
                color: {self.theme.app('text_primary')};
                border: 1px solid {self.theme.app('card_border')};
                border-radius: 6px;
                padding-left: 10px;
                font-size: 13px;
            }}
        """)
        layout.addWidget(self.search_input)

        # Sort dropdown
        sort_label = QLabel("Sort:")
        sort_label.setStyleSheet(f"color: {self.theme.app('text_secondary')}; font-size: 13px;")
        layout.addWidget(sort_label)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Recently Added", "Title", "Author"])
        self.sort_combo.setFixedHeight(30)
        self.sort_combo.currentTextChanged.connect(self._load_library)
        self.sort_combo.setStyleSheet(self._combo_style())
        layout.addWidget(self.sort_combo)

        # Filter dropdown
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet(f"color: {self.theme.app('text_secondary')}; font-size: 13px;")
        layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Favorites"])
        self.filter_combo.setFixedHeight(30)
        self.filter_combo.currentTextChanged.connect(self._load_library)
        self.filter_combo.setStyleSheet(self._combo_style())
        layout.addWidget(self.filter_combo)

        layout.addStretch()

        return toolbar

    def _combo_style(self) -> str:
        return f"""
            QComboBox {{
                background: {self.theme.app('card_bg')};
                color: {self.theme.app('text_primary')};
                border: 1px solid {self.theme.app('card_border')};
                border-radius: 6px;
                padding: 0 24px 0 10px;
                min-width: 120px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {self.theme.app('card_bg')};
                color: {self.theme.app('text_primary')};
                selection-background-color: {self.theme.app('sidebar_hover')};
                border: 1px solid {self.theme.app('card_border')};
            }}
        """

    def _build_empty_state(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("◆")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")

        msg = QLabel("Your library is empty")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(
            f"font-size: 16px; color: {self.theme.app('text_secondary')}; "
            f"margin-top: 12px;"
        )

        sub = QLabel("Click '+ Import' to add books, comics or PDFs")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"font-size: 13px; color: {self.theme.app('text_muted')}; "
            f"margin-top: 6px;"
        )

        layout.addWidget(icon)
        layout.addWidget(msg)
        layout.addWidget(sub)

        return w

    # ── Logic ──────────────────────────────────────────────────────────────

    def filter_by_collection(self, collection_id: str | None):
        self._active_collection = collection_id
        self._load_library()

    def _load_library(self):
        col_id = getattr(self, "_active_collection", None)
        if col_id:
            from storage.repositories import CollectionRepository
            books = CollectionRepository().get_books(col_id)
        else:
            books = self.repo.get_all()

        # Apply Filter (All vs Favorites)
        if hasattr(self, "filter_combo"):
            filter_val = self.filter_combo.currentText()
            if filter_val == "Favorites":
                books = [b for b in books if bool(b["is_favorite"])]

        # Apply Search
        if hasattr(self, "search_input"):
            query = self.search_input.text().strip().lower()
            if query:
                books = [
                    b for b in books
                    if query in (b["title"] or "").lower() or query in (b["author"] or "").lower()
                ]

        # Apply Sort
        if hasattr(self, "sort_combo"):
            sort_val = self.sort_combo.currentText()
            if sort_val == "Title":
                books = sorted(books, key=lambda b: (b["title"] or "").lower())
            elif sort_val == "Author":
                books = sorted(books, key=lambda b: (b["author"] or "Unknown").lower())

        self._books = books

        if not books:
            while self.grid_layout.count():
                item = self.grid_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.scroll.hide()
            self.empty_state.show()
        else:
            self.empty_state.hide()
            self.scroll.show()
            self._populate_grid(books)

    def _populate_grid(self, books):
        # Clear existing
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Responsive columns based on width
        width = self.scroll.width()
        cols = max(2, width // 180) if width > 200 else 5

        for i, book in enumerate(books):
            from ui.book_card import BookCard
            card = BookCard(book, self.theme)
            card.open_requested.connect(self._on_open_book)
            card.fetch_metadata_requested.connect(self._on_fetch_metadata)
            card.convert_requested.connect(self._on_convert)
            card.removed.connect(lambda bid: self._load_library())
            card.selection_toggled.connect(self._on_card_selection_toggled)
            card.set_selection_mode(self._selection_mode, book["id"] in self._selected_books)
            self.grid_layout.addWidget(card, i // cols, i % cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_books"):
            self._populate_grid(self._books)

    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Books", "", SUPPORTED_FORMATS
        )
        if not paths:
            return
        
        success_count = 0
        from ui.widgets.toast import ToastManager
        for path in paths:
            try:
                self._import_file(path)
                success_count += 1
            except Exception as e:
                from pathlib import Path
                ToastManager.get_instance().show(
                    f"Failed to import {Path(path).name}: {e}", "error"
                )
        
        if success_count > 0:
            ToastManager.get_instance().show(
                f"Successfully imported {success_count} book(s)!", "success"
            )
        self._load_library()

    def _import_file(self, file_path: str):
        from pathlib import Path
        from core.book_model import BookMetadata
        from core.classifier import BookClassifier
        from storage.repositories import TagRepository, CollectionRepository

        p         = Path(file_path)
        fmt       = p.suffix.lower().lstrip(".")
        clf       = BookClassifier()
        tag_repo  = TagRepository()
        col_repo  = CollectionRepository()

        # Extract metadata via unified BookLoader service
        try:
            from core.book_loader import BookLoader
            book_obj = BookLoader().load(file_path, fmt)
            meta     = book_obj.metadata
        except Exception:
            meta = BookMetadata(title=p.stem, author="Unknown")

        # Get image ratio for PDF manga detection
        img_ratio = 0.0
        if fmt == "pdf":
            img_ratio = clf.image_block_ratio(file_path)

        # Extract text sample for fanfic detection
        sample = clf.extract_sample(file_path, fmt)

        # Classify
        book_type, suggested_tags = clf.classify(
            file_path    = file_path,
            fmt          = fmt,
            title        = meta.title,
            author       = meta.author       or "",
            publisher    = meta.publisher    or "",
            description  = meta.description  or "",
            sample_text  = sample,
            image_block_ratio = img_ratio,
        )

        # Save book
        book_id = self.repo.add(meta, file_path, fmt)

        # Save book_type
        conn = __import__('storage.database', fromlist=['get_connection']).get_connection()
        with conn:
            conn.execute(
                "UPDATE books SET book_type=? WHERE id=?",
                (book_type, book_id)
            )
        conn.close()

        # Apply auto tags
        for tag_name in suggested_tags:
            tag_id = tag_repo.get_or_create(tag_name, is_auto=True)
            tag_repo.add_to_book(book_id, tag_id)

        # Auto-assign to matching default collection
        collection_map = {
            "fanfic":    "fanfic-default",
            "manga":     "originals-default",
            "comic":     "originals-default",
            "published": "originals-default",
        }
        col_id = collection_map.get(book_type)
        if col_id:
            col_repo.add_book(book_id, col_id)

        self.plugins.emit_book_import(book_id, file_path)

    def _on_open_book(self, book_id: str):
        self.open_book_requested.emit(book_id)

    def _on_fetch_metadata(self, book_id: str):
        from ui.metadata_dialog import MetadataDialog
        row = self.repo.get_by_id(book_id)
        if not row:
            return
        dialog = MetadataDialog(row, self.theme, self)
        if dialog.exec():
            self._load_library()

    def _on_convert(self, book_id: str):
        from ui.convert_dialog import ConvertDialog
        row = self.repo.get_by_id(book_id)
        if not row:
            return
        dialog = ConvertDialog(row, self.theme, self)
        dialog.exec()
        self._load_library()

    # ── Theme ──────────────────────────────────────────────────────────────

    def _apply_theme(self):
        self.setStyleSheet(
            f"LibraryView {{ background: {self.theme.app('window_bg')}; }}"
        )
        self.grid_container.setStyleSheet(
            f"background: {self.theme.app('window_bg')};"
        )