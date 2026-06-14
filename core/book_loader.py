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
            book = EpubEngine().load(file_path)
        elif fmt == "pdf":
            book = PdfEngine().load(file_path)
        elif fmt in ("cbz", "cbr", "cb7", "cbt"):
            book = ComicEngine().load(file_path)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        self._preprocess_book_formatting(book)
        return book

    def _preprocess_book_formatting(self, book: Book):
        import re

        CHAPTER_PATTERNS = [
            re.compile(r"^chapter\s+\d+", re.IGNORECASE),
            re.compile(r"^chapter\s+[ivxlcdm]+", re.IGNORECASE),
            re.compile(r"^ch\.\s*\d+", re.IGNORECASE),
            re.compile(r"^ch\s+\d+", re.IGNORECASE),
            re.compile(r"^part\s+\d+", re.IGNORECASE),
            re.compile(r"^part\s+[ivxlcdm]+", re.IGNORECASE),
            re.compile(r"^prologue$", re.IGNORECASE),
            re.compile(r"^epilogue$", re.IGNORECASE),
            re.compile(r"^interlude$", re.IGNORECASE),
        ]

        for chapter in book.chapters:
            chapter_is_dedication = False
            title_lower = chapter.title.lower()
            if "dedication" in title_lower or "dedicated" in title_lower:
                chapter_is_dedication = True

            for block in chapter.blocks:
                if not block.text:
                    continue

                text_lower = block.text.lower()
                stripped = block.text.strip()
                stripped_lower = stripped.lower()

                # 1. Dedication formatting (center & italics)
                is_dedication_block = (
                    chapter_is_dedication or
                    "dedication" in text_lower or
                    "dedicated to" in text_lower or
                    "for my" in text_lower or
                    stripped_lower.startswith("to my ") or
                    (block.attrs.get("align") == "center" and len(stripped) < 300 and ("dedicated" in text_lower or "dedication" in text_lower))
                )

                if is_dedication_block:
                    block.attrs["align"] = "center"
                    block.attrs["italic"] = True
                    block.attrs["is_dedication"] = True

                # 2. Copyright details -> italic
                if ("copyright" in text_lower or "©" in text_lower or 
                    "all rights reserved" in text_lower or "isbn" in text_lower or 
                    "first edition" in text_lower or "published by" in text_lower or 
                    "printed in" in text_lower):
                    block.attrs["italic"] = True

                # 3. Chapter title/number bolding
                if len(stripped) <= 80:
                    matched_chapter = False
                    for pattern in CHAPTER_PATTERNS:
                        if pattern.match(stripped):
                            matched_chapter = True
                            break
                    if matched_chapter:
                        block.attrs["bold"] = True
