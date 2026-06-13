from dataclasses import dataclass, field


@dataclass
class PaginationCacheKey:
    book_id:    str
    font_family: str
    font_size:  float
    page_width: float
    page_height: float
    line_spacing: float

    def __hash__(self):
        return hash((
            self.book_id,
            self.font_family,
            self.font_size,
            self.page_width,
            self.page_height,
            self.line_spacing,
        ))

    def __eq__(self, other):
        return hash(self) == hash(other)


@dataclass
class PaginationResult:
    """
    One entry per page — each page is a list of
    (chapter_index, block_index) tuples.
    """
    pages: list[list[tuple[int, int]]] = field(default_factory=list)
    total_pages: int = 0

    def get_page(self, page_num: int) -> list[tuple[int, int]]:
        if 0 <= page_num < len(self.pages):
            return self.pages[page_num]
        return []


class PaginationCache:
    """
    In-memory cache of pagination results.
    Keyed by book + current theme/layout settings.
    Invalidated automatically when settings change.
    """

    def __init__(self, max_entries: int = 10):
        self._cache: dict[PaginationCacheKey, PaginationResult] = {}
        self._max   = max_entries

    def get(
        self, key: PaginationCacheKey
    ) -> PaginationResult | None:
        return self._cache.get(key)

    def set(self, key: PaginationCacheKey, result: PaginationResult):
        if len(self._cache) >= self._max:
            # Evict oldest entry
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[key] = result

    def invalidate(self, book_id: str):
        """Remove all cached results for a specific book."""
        keys = [k for k in self._cache if k.book_id == book_id]
        for k in keys:
            del self._cache[k]

    def clear(self):
        self._cache.clear()