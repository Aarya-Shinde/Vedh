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
        import uuid
        from core.book_model import Chapter, Block, BlockType

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

        # ── 1. Rebuild Chapters from Blocks if No Table of Contents ──
        book_title_lower = (book.metadata.title or "").lower().strip()
        generic_titles = {
            "content", "main", "front matter", "unknown", 
            "content.xhtml", "toc.xhtml", "chapter", "chapters", 
            book_title_lower
        }
        is_single_generic = (
            len(book.chapters) == 1 and 
            (book.chapters[0].title or "").lower().strip() in generic_titles
        )
        if len(book.chapters) == 0 or is_single_generic:
            all_blocks = book.chapters[0].blocks if book.chapters else []
            new_chapters = []
            current_title = "Front Matter"
            current_blocks = []
            order = 0

            for block in all_blocks:
                is_split = False
                if block.type == BlockType.HEADING:
                    if block.level == 1:
                        is_split = True
                    elif block.text:
                        stripped = block.text.strip()
                        for pattern in CHAPTER_PATTERNS:
                            if pattern.match(stripped):
                                is_split = True
                                break

                if is_split and (current_blocks or new_chapters):
                    new_chapters.append(Chapter(
                        id=str(uuid.uuid4()),
                        title=current_title,
                        blocks=current_blocks,
                        order=order
                    ))
                    order += 1
                    current_title = block.text.strip()
                    current_blocks = [block]
                else:
                    current_blocks.append(block)

            if current_blocks:
                new_chapters.append(Chapter(
                    id=str(uuid.uuid4()),
                    title=current_title,
                    blocks=current_blocks,
                    order=order
                ))

            if len(new_chapters) > 1:
                book.chapters = new_chapters

        # ── 2. Prepend Cover Image inside the Book View ──
        if book.metadata.cover_data:
            has_cover_at_start = False
            if book.chapters and book.chapters[0].blocks:
                first_b = book.chapters[0].blocks[0]
                if first_b.type == BlockType.IMAGE:
                    has_cover_at_start = True

            if not has_cover_at_start:
                cover_block = Block(
                    type=BlockType.IMAGE,
                    image_data=book.metadata.cover_data,
                    alt_text="Cover Image",
                    attrs={"is_cover": True}
                )
                page_break = Block(type=BlockType.PAGE_BREAK)

                if book.chapters:
                    book.chapters[0].blocks.insert(0, page_break)
                    book.chapters[0].blocks.insert(0, cover_block)
                else:
                    cover_chap = Chapter(
                        id=str(uuid.uuid4()),
                        title="Cover",
                        blocks=[cover_block, page_break],
                        order=0
                    )
                    book.chapters.insert(0, cover_chap)

        # ── 3. Apply Styling and Drop-Caps ──
        for chapter in book.chapters:
            chapter_is_dedication = False
            title_lower = (chapter.title or "").lower()
            if "dedication" in title_lower or "dedicated" in title_lower:
                chapter_is_dedication = True

            for block in chapter.blocks:
                if not block.text:
                    continue

                text_lower = block.text.lower()
                stripped = block.text.strip()
                stripped_lower = stripped.lower()

                # Dedication formatting (center & italics)
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

                # Copyright details -> italic
                if ("copyright" in text_lower or "©" in text_lower or 
                    "all rights reserved" in text_lower or "isbn" in text_lower or 
                    "first edition" in text_lower or "published by" in text_lower or 
                    "printed in" in text_lower):
                    block.attrs["italic"] = True

                # Chapter title/number bolding
                if len(stripped) <= 80:
                    matched_chapter = False
                    for pattern in CHAPTER_PATTERNS:
                        if pattern.match(stripped):
                            matched_chapter = True
                            break
                    if matched_chapter:
                        block.attrs["bold"] = True

            # Skip drop caps for front-matter / back-matter chapters
            skip_drop_caps = (
                "dedication" in title_lower or
                "copyright" in title_lower or
                "acknowledgements" in title_lower or
                "preface" in title_lower or
                "contents" in title_lower or
                "introduction" in title_lower or
                "about the author" in title_lower or
                "title page" in title_lower or
                "colophon" in title_lower or
                "epigraph" in title_lower or
                "foreword" in title_lower or
                "cover" in title_lower
            )

            if not skip_drop_caps:
                for block in chapter.blocks:
                    if block.type == BlockType.PARAGRAPH and block.text:
                        stripped = block.text.strip()
                        if len(stripped) >= 15:
                            if block.attrs.get("is_dedication") or block.attrs.get("italic"):
                                continue
                            block.attrs["is_first_paragraph"] = True
                            break
