from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtCore import QRectF

from core.book_model import Book, Block, BlockType
from rendering.text_renderer import TextRenderer
from rendering.image_renderer import ImageRenderer
from rendering.pagination.engine import PaginationEngine
from rendering.pagination.cache import PaginationResult


class LayoutEngine:
    """
    Orchestrates TextRenderer, ImageRenderer, and PaginationEngine.

    The reader widget only talks to this class.
    It asks for a page number and gets back a fully painted surface.

    Flow:
        Book → PaginationEngine → page block references
             → TextRenderer / ImageRenderer → painted output
    """

    def __init__(self):
        self._text_renderer  = TextRenderer()
        self._image_renderer = ImageRenderer()
        self._pagination     = PaginationEngine()

        self._book:           Book | None           = None
        self._result:         PaginationResult | None = None
        self._theme:          dict                  = {}
        self._page_width:     float                 = 700.0
        self._viewport_width: float                 = 700.0
        self._page_height:    float                 = 900.0
        self._margin_h:       float                 = 48.0   # left/right
        self._margin_top:     float                 = 40.0
        self._margin_bottom:  float                 = 40.0
        self._is_comic:       bool                  = False

    # ── Configuration ──────────────────────────────────────────────────────

    def configure(
        self,
        theme: dict,
        viewport_width:  float,
        viewport_height: float,
        is_comic: bool = False,
    ):
        self._theme         = theme
        self._viewport_width = viewport_width
        self._page_height   = viewport_height
        self._is_comic      = is_comic

        if is_comic:
            self._margin_h      = 0.0
            self._margin_top    = 0.0
            self._margin_bottom = 0.0
            self._page_width    = viewport_width
        else:
            self._margin_h      = float(theme.get("margin_h", 48.0))
            self._margin_top    = float(theme.get("margin_v", 40.0))
            self._margin_bottom = float(theme.get("margin_v", 40.0))
            # Content width = viewport minus horizontal margins
            self._page_width = min(
                float(theme.get("page_width", 750)),
                viewport_width - self._margin_h * 2,
            )

        self._text_renderer.configure(theme, self._page_width)
        self._image_renderer.configure(
            theme, self._page_width, is_comic=is_comic
        )
        self._pagination.configure(
            theme,
            self._page_width,
            viewport_height,
        )

        # Invalidate pagination if book already loaded
        if self._book:
            self._pagination.invalidate(self._book.id)
            self._result = None

    def set_fit_mode(self, mode: str):
        self._image_renderer.set_fit_mode(mode)

    # ── Book loading ───────────────────────────────────────────────────────

    def load_book(self, book: Book):
        self._book   = book
        self._result = None
        self._image_renderer.clear_cache()

        # Detect comic mode from format
        comic_formats = {"cbz", "cbr", "cb7", "cbt"}
        self._is_comic = book.format in comic_formats
        self._image_renderer.set_comic_mode(self._is_comic)

        # Run pagination
        self._result = self._pagination.paginate(book)

    # ── Page access ────────────────────────────────────────────────────────

    @property
    def total_pages(self) -> int:
        return self._result.total_pages if self._result else 0

    def get_page_blocks(self, page_num: int) -> list[Block]:
        if not self._result or not self._book:
            return []
        refs = self._result.get_page(page_num)
        blocks = []
        for chapter_idx, block_idx in refs:
            try:
                block = self._book.chapters[chapter_idx].blocks[block_idx]
                blocks.append(block)
            except IndexError:
                continue
        return blocks

    # ── Painting ───────────────────────────────────────────────────────────

    def paint_page(self, painter: QPainter, page_num: int):
        """
        Paint all blocks on the given page onto the painter.
        Called by the reader widget's paintEvent.
        """
        if not self._result or not self._book:
            self._paint_empty(painter)
            return

        blocks = self.get_page_blocks(page_num)
        if not blocks:
            self._paint_empty(painter)
            return

        # Background (support both background and bg theme keys)
        bg = self._theme.get("background", self._theme.get("bg", "#FAF9F6"))
        painter.fillRect(
            QRectF(0, 0, self._viewport_width, self._page_height),
            QColor(bg),
        )

        # Center the page horizontally
        page_total_width = self._page_width + self._margin_h * 2
        page_start_x = max(0.0, (self._viewport_width - page_total_width) / 2)

        # Content origin — centered with margins
        x = page_start_x + self._margin_h
        y = float(self._margin_top)

        for block in blocks:
            if block.type == BlockType.PAGE_BREAK:
                continue

            elif block.type == BlockType.IMAGE:
                consumed = self._image_renderer.draw_block(
                    painter, block, x, y,
                    viewport_height=self._page_height,
                )

            else:
                consumed = self._text_renderer.draw_block(
                    painter, block, x, y
                )

            y += consumed

    def _paint_empty(self, painter: QPainter):
        bg = self._theme.get("background", self._theme.get("bg", "#FAF9F6"))
        painter.fillRect(
            QRectF(0, 0, self._viewport_width, self._page_height),
            QColor(bg),
        )

    # ── Chapter navigation ─────────────────────────────────────────────────

    def page_for_chapter(self, chapter_idx: int) -> int:
        """Return the first page number that contains a block from the chapter."""
        if not self._result:
            return 0
        for page_num, refs in enumerate(self._result.pages):
            for c_idx, _ in refs:
                if c_idx == chapter_idx:
                    return page_num
        return 0

    def chapter_for_page(self, page_num: int) -> int:
        """Return which chapter index the given page belongs to."""
        if not self._result:
            return 0
        refs = self._result.get_page(page_num)
        if refs:
            return refs[0][0]
        return 0