from engines.epub_engine import EpubEngine
from engines.pdf_engine import PdfEngine
from engines.comic_engine import ComicEngine
from core.book_model import Book

class BookLoader:
    """
    Unified loader service to load books of any format.
    Delegates parsing to format-specific engines.
    """
    def load(self, file_path: str, fmt: str) -> Book:
        fmt = fmt.lower().strip()
        if fmt == "epub":
            return EpubEngine().load(file_path)
        elif fmt == "pdf":
            return PdfEngine().load(file_path)
        elif fmt in ("cbz", "cbr", "cb7", "cbt"):
            return ComicEngine().load(file_path)
        else:
            raise ValueError(f"Unsupported format: {fmt}")
