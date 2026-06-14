from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QCursor

from core.theme_manager import ThemeManager
from core.converter import Converter, ConversionError


# ── Worker ─────────────────────────────────────────────────────────────────

class ConvertWorker(QThread):

    progress = pyqtSignal(str, int)
    finished = pyqtSignal(str)      # output path
    failed   = pyqtSignal(str)

    def __init__(self, file_path: str, fmt: str, target: str):
        super().__init__()
        self._path   = file_path
        self._fmt    = fmt
        self._target = target

    def run(self):
        try:
            conv = Converter()
            if self._fmt == "epub" and self._target == "pdf":
                out = conv.epub_to_pdf(
                    self._path,
                    on_progress=lambda s, p: self.progress.emit(s, p)
                )
            elif self._fmt == "pdf" and self._target == "epub":
                out = conv.pdf_to_epub(
                    self._path,
                    on_progress=lambda s, p: self.progress.emit(s, p)
                )
            else:
                self.failed.emit(f"Unsupported: {self._fmt} → {self._target}")
                return
            self.finished.emit(out)
        except ConversionError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Unexpected error: {e}")


# ── Dialog ─────────────────────────────────────────────────────────────────

class ConvertDialog(QDialog):

    def __init__(self, book_row, theme: ThemeManager, parent=None):
        super().__init__(parent)
        self.book_row = book_row
        self.theme    = theme
        self._worker: ConvertWorker | None = None
        self._target_buttons = []

        self.setWindowTitle("Convert Book")
        self.setFixedSize(440, 280)
        self.setModal(True)

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        fmt   = self.book_row["format"]
        title = self.book_row["title"]

        # Header
        hdr = QLabel("Convert Book")
        hdr.setStyleSheet(
            f"font-size: 16px; font-weight: 600; "
            f"color: {self.theme.app('text_primary')};"
        )
        layout.addWidget(hdr)

        # Book info
        info = QLabel(f"<b>{title}</b>  ·  {fmt.upper()}")
        info.setStyleSheet(
            f"font-size: 13px; color: {self.theme.app('text_secondary')};"
        )
        layout.addWidget(info)

        # Target format buttons
        btn_row = QHBoxLayout()
        self._target: str | None = None

        targets = self._get_targets(fmt)
        if not targets:
            no_conv = QLabel(
                f"No conversions available for {fmt.upper()} files."
            )
            no_conv.setStyleSheet(
                f"color: {self.theme.app('text_muted')}; font-size: 13px;"
            )
            layout.addWidget(no_conv)
        else:
            for target_fmt in targets:
                btn = QPushButton(
                    f"{fmt.upper()}  →  {target_fmt.upper()}"
                )
                btn.setFixedHeight(40)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.clicked.connect(
                    lambda checked, t=target_fmt: self._on_start(t)
                )
                btn.setStyleSheet(self._accent_btn_style())
                self._target_buttons.append(btn)
                btn_row.addWidget(btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Progress
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

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"font-size: 12px; color: {self.theme.app('text_muted')};"
        )
        layout.addWidget(self._status)

        layout.addStretch()

        # Close button
        close_row = QHBoxLayout()
        close_row.addStretch()
        self._close_btn = QPushButton("Close")
        self._close_btn.setFixedHeight(34)
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.clicked.connect(self.accept)
        self._close_btn.setStyleSheet(self._ghost_btn_style())
        close_row.addWidget(self._close_btn)
        layout.addLayout(close_row)

    def _get_targets(self, fmt: str) -> list[str]:
        mapping = {
            "epub": ["pdf"],
            "pdf":  ["epub"],
        }
        return mapping.get(fmt, [])

    def _on_start(self, target: str):
        self._progress_bar.show()
        self._progress_bar.setValue(0)
        self._status.setText("Starting conversion...")

        self._worker = ConvertWorker(
            self.book_row["file_path"],
            self.book_row["format"],
            target,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, step: str, pct: int):
        self._status.setText(step)
        self._progress_bar.setValue(pct)

    def _on_finished(self, output_path: str):
        self._progress_bar.setValue(100)
        self._status.setText(f"Saved: {output_path}")

        # Auto-import into library
        from pathlib import Path
        from core.book_model import BookMetadata
        from storage.repositories import BookRepository
        from ui.widgets.toast import ToastManager

        p    = Path(output_path)
        fmt  = p.suffix.lower().lstrip(".")
        meta = BookMetadata(
            title  = self.book_row["title"],
            author = self.book_row["author"],
        )
        repo = BookRepository()
        existing = repo.get_all()
        paths    = [r["file_path"] for r in existing]

        if output_path not in paths:
            repo.add(meta, output_path, fmt)
            self._status.setText(
                f"Converted and imported: {p.name}"
            )
            ToastManager.get_instance().show(f"Converted and imported: {p.name}", "success")
        else:
            ToastManager.get_instance().show(f"Successfully converted: {p.name}", "success")

    def _on_failed(self, error: str):
        self._progress_bar.hide()
        self._status.setText(f"Error: {error}")
        from ui.widgets.toast import ToastManager
        ToastManager.get_instance().show(f"Conversion failed: {error}", "error")

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
                padding: 0 20px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {t.app('accent_hover')};
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
            f"ConvertDialog {{ background: {t.app('window_bg')}; }}"
        )
        if hasattr(self, "_close_btn"):
            self._close_btn.setStyleSheet(self._ghost_btn_style())
        for btn in self._target_buttons:
            btn.setStyleSheet(self._accent_btn_style())
