from core.book_model import Book, BlockType
from rendering.pagination.measurer import BlockMeasurer, MeasuredBlock
from rendering.pagination.cache import (
    PaginationCache, PaginationCacheKey, PaginationResult
)


class PaginationEngine:
    """
    Breaks a Book's blocks into pages given a viewport height.

    A page is a list of (chapter_index, block_index) references.
    The renderer uses these references to know what to draw.

    Does NOT store any rendered content — purely geometric.
    """

    def __init__(self):
        self._measurer = BlockMeasurer()
        self._cache    = PaginationCache()

    # ── Configuration ──────────────────────────────────────────────────────

    def configure(
        self,
        theme: dict,
        page_width: float,
        page_height: float,
        dpr: float = 1.0,
    ):
        self._theme       = theme
        self._page_width  = page_width
        self._page_height = page_height
        self._dpr         = dpr
        self._measurer.configure(theme, page_width, page_height, dpr)

    # ── Public API ─────────────────────────────────────────────────────────

    def paginate(self, book: Book) -> PaginationResult:
        key = self._make_key(book.id)

        cached = self._cache.get(key)
        if cached:
            return cached

        result = self._run(book)
        self._cache.set(key, result)
        return result

    def invalidate(self, book_id: str):
        self._cache.invalidate(str(book_id))

    # ── Core algorithm ─────────────────────────────────────────────────────

    def _run(self, book: Book) -> PaginationResult:
        pages: list[list[tuple[int, int]]] = []
        current_page: list[tuple[int, int]] = []
        current_height: float = 0.0

        top_margin    = float(self._theme.get("page_margin_top",    40))
        bottom_margin = float(self._theme.get("page_margin_bottom", 40))
        usable_height = self._page_height - top_margin - bottom_margin

        for chapter_idx, chapter in enumerate(book.chapters):
            measured = self._measurer.measure_all(chapter.blocks)

            for block_idx, mb in enumerate(measured):

                # PAGE_BREAK — force a new page immediately
                if mb.block.type == BlockType.PAGE_BREAK:
                    if current_page:
                        pages.append(current_page)
                        current_page   = []
                        current_height = 0.0
                    continue

                # Check for dedication/TOC in paragraph/heading text
                is_break_keyword = False
                if mb.block.text:
                    lower_text = mb.block.text.strip().lower()
                    if lower_text in ("dedication", "table of contents", "toc", "title page", "about the author", "contents", "preface"):
                        is_break_keyword = True
                    elif mb.block.type == BlockType.HEADING and lower_text.startswith("chapter"):
                        is_break_keyword = True

                # Force break at:
                # 1. Start of any new chapter (block_idx == 0 and chapter_idx > 0)
                # 2. Heading block with level <= 2 inside a chapter (block_idx > 0)
                # 3. Dedicated keyword blocks
                should_force_break = False
                if block_idx == 0 and chapter_idx > 0:
                    should_force_break = True
                elif block_idx > 0:
                    if is_break_keyword:
                        should_force_break = True
                    elif mb.block.type == BlockType.HEADING and mb.block.level is not None and mb.block.level <= 2:
                        should_force_break = True

                if should_force_break:
                    if current_page:
                        pages.append(current_page)
                        current_page   = []
                        current_height = 0.0

                block_height = mb.height

                # Block taller than a full page — give it its own page
                if block_height > usable_height:
                    if current_page:
                        pages.append(current_page)
                        current_page   = []
                        current_height = 0.0
                    pages.append([(chapter_idx, block_idx)])
                    continue

                # Block fits on current page
                if current_height + block_height <= usable_height:
                    current_page.append((chapter_idx, block_idx))
                    current_height += block_height

                # Block doesn't fit — start new page
                else:
                    if current_page:
                        pages.append(current_page)
                    current_page   = [(chapter_idx, block_idx)]
                    current_height = block_height

        # Flush last page
        if current_page:
            pages.append(current_page)

        return PaginationResult(
            pages=pages,
            total_pages=len(pages),
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _make_key(self, book_id) -> PaginationCacheKey:
        return PaginationCacheKey(
            book_id=str(book_id),
            font_family=self._theme.get("font_family", "Georgia"),
            font_size=float(self._theme.get("font_size", 18)),
            page_width=self._page_width,
            page_height=self._page_height,
            line_spacing=float(self._theme.get("line_spacing", 1.6)),
        )