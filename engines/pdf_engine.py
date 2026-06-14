from pathlib import Path
from uuid import uuid4

import fitz  # PyMuPDF
import re

from core.book_model import (
    Book, BookMetadata, Chapter, Block, BlockType
)


# Heading detection — if a text span is this much larger than
# the document's modal font size, treat it as a heading
HEADING_SIZE_RATIO = 1.2

CHAPTER_PATTERNS = [
    re.compile(r"^chapter\s+\d+", re.IGNORECASE),
    re.compile(r"^chapter\s+[ivxlcdm]+", re.IGNORECASE),   # roman numerals
    re.compile(r"^ch\.\s*\d+", re.IGNORECASE),
    re.compile(r"^part\s+\d+", re.IGNORECASE),
    re.compile(r"^part\s+[ivxlcdm]+", re.IGNORECASE),
    re.compile(r"^prologue$", re.IGNORECASE),
    re.compile(r"^epilogue$", re.IGNORECASE),
    re.compile(r"^interlude$", re.IGNORECASE),
    re.compile(r"^\d+\.$"),                                  # "1." "2." alone on a line
]



class PdfEngine:

    def load(self, file_path: str) -> Book:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        doc = fitz.open(str(path))

        metadata = self._extract_metadata(doc, path)
        chapters = self._extract_chapters(doc)

        doc.close()

        return Book(
            id=uuid4(),
            metadata=metadata,
            file_path=file_path,
            format="pdf",
            chapters=chapters,
        )

    # ── Metadata ───────────────────────────────────────────────────────────

    def _extract_metadata(self, doc: fitz.Document, path: Path) -> BookMetadata:
        meta = doc.metadata or {}

        title  = meta.get("title")  or path.stem
        author = meta.get("author") or "Unknown Author"
        cover_data = self._extract_cover(doc)

        return BookMetadata(
            title=title,
            author=author,
            cover_data=cover_data,
        )

    def _extract_cover(self, doc: fitz.Document) -> bytes | None:
        if doc.page_count == 0:
            return None
        page = doc.load_page(0)
        # Render first page at low res as cover thumbnail
        mat = fitz.Matrix(0.5, 0.5)
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")

    # ── Chapters ───────────────────────────────────────────────────────────

    def _extract_chapters(self, doc: fitz.Document) -> list[Chapter]:
        toc = doc.get_toc()  # [[level, title, page], ...]

        if toc:
            return self._chapters_from_toc(doc, toc)
        else:
            return self._chapters_from_pages(doc)

    def _chapters_from_toc(
        self, doc: fitz.Document, toc: list
    ) -> list[Chapter]:
        """Use the PDF's table of contents to split into chapters."""
        chapters = []
        modal_size = self._modal_font_size(doc)

        # Build page ranges from TOC entries
        ranges = []
        for i, (level, title, start_page) in enumerate(toc):
            if level != 1:
                continue
            end_page = doc.page_count
            # Find next level-1 entry to get end boundary
            for j in range(i + 1, len(toc)):
                if toc[j][0] == 1:
                    end_page = toc[j][2] - 1
                    break
            ranges.append((title, start_page - 1, end_page - 1))

        for order, (title, start, end) in enumerate(ranges):
            blocks = []
            for page_num in range(start, min(end + 1, doc.page_count)):
                page_blocks = self._parse_page(
                    doc.load_page(page_num), page_num, modal_size
                )
                blocks.extend(page_blocks)
                blocks.append(Block(type=BlockType.PAGE_BREAK))

            chapters.append(Chapter(
                id=str(uuid4()),
                title=title,
                blocks=blocks,
                order=order,
            ))

        return chapters

    def _chapters_from_pages(self, doc: fitz.Document) -> list[Chapter]:
        """
        No TOC — scan all pages, split into chapters at heading markers.
        Fanfic / self-published books benefit most from this.
        """
        modal_size = self._modal_font_size(doc)

        # First pass — collect all blocks across all pages
        all_blocks: list[Block] = []
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_blocks = self._parse_page(page, page_num, modal_size)
            all_blocks.extend(page_blocks)
            all_blocks.append(Block(type=BlockType.PAGE_BREAK))

        # Second pass — split at level-1 headings
        chapters: list[Chapter] = []
        current_title = "Front Matter"
        current_blocks: list[Block] = []
        order = 0

        for block in all_blocks:
            is_chapter_heading = (
                block.type == BlockType.HEADING
                and block.level == 1
            )

            if is_chapter_heading and current_blocks:
                # Save current chapter
                chapters.append(Chapter(
                    id=str(uuid4()),
                    title=current_title,
                    blocks=current_blocks,
                    order=order,
                ))
                order += 1
                current_title  = block.text
                current_blocks = []
            else:
                current_blocks.append(block)

        # Save last chapter
        if current_blocks:
            chapters.append(Chapter(
                id=str(uuid4()),
                title=current_title,
                blocks=current_blocks,
                order=order,
            ))

        # If no chapter splits were found, return as single chapter
        if len(chapters) == 1 and chapters[0].title == "Front Matter":
            chapters[0].title = "Content"

        return chapters

    # ── Page → Blocks ──────────────────────────────────────────────────────

    def _parse_page(
        self,
        page: fitz.Page,
        page_num: int,
        modal_size: float,
    ) -> list[Block]:
        blocks = []

        # Extract text with detailed span info
        text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        for block in text_dict.get("blocks", []):
            block_type = block.get("type")

            # ── Text block ──
            if block_type == 0:
                lines_data = []
                for line in block.get("lines", []):
                    line_text = ""
                    max_size  = 0.0
                    is_bold   = False

                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if not text.strip():
                            continue
                        line_text += text + " "
                        size = span.get("size", 0)
                        if size > max_size:
                            max_size = size
                        flags = span.get("flags", 0)
                        if flags & 2**4:  # bold flag
                            is_bold = True

                    line_text = line_text.strip()
                    if line_text:
                        lines_data.append({
                            "text": line_text,
                            "size": max_size,
                            "bold": is_bold
                        })

                if not lines_data:
                    continue

                current_paragraph_parts = []
                for item in lines_data:
                    txt = item["text"]
                    sz = item["size"]
                    bld = item["bold"]

                    is_chapter = self._is_chapter_marker(txt, bld)
                    is_heading = (modal_size > 0 and sz >= modal_size * HEADING_SIZE_RATIO) or is_chapter

                    if is_heading:
                        if current_paragraph_parts:
                            blocks.append(self._create_merged_paragraph(current_paragraph_parts))
                            current_paragraph_parts = []
                        level = 1 if is_chapter else self._heading_level(sz, modal_size)
                        blocks.append(Block(
                            type=BlockType.HEADING,
                            text=txt,
                            level=level,
                        ))
                    else:
                        current_paragraph_parts.append(txt)

                if current_paragraph_parts:
                    blocks.append(self._create_merged_paragraph(current_paragraph_parts))

            # ── Image block ──
            elif block_type == 1:
                try:
                    xref = block.get("image")
                    if xref:
                        img_data = page.parent.extract_image(xref)
                        if img_data:
                            blocks.append(Block(
                                type=BlockType.IMAGE,
                                image_data=img_data["image"],
                                alt_text=f"Image on page {page_num + 1}",
                            ))
                except Exception:
                    pass  # skip unreadable images silently

        return blocks

    # ── Helpers ────────────────────────────────────────────────────────────

    def _is_chapter_marker(self, text: str, is_bold: bool) -> bool:
        """
        Returns True if this line looks like a chapter heading
        regardless of font size.
        """
        stripped = text.strip()

        # Must be a short line — chapter markers aren't paragraphs
        if len(stripped) > 80:
            return False

        for pattern in CHAPTER_PATTERNS:
            if pattern.match(stripped):
                return True

        # Bold short line that's title-cased or all-caps — strong signal
        if is_bold and len(stripped) <= 60:
            if stripped.istitle() or stripped.isupper():
                return True

        return False

    def _modal_font_size(self, doc: fitz.Document) -> float:
        """
        Find the most common font size across the first 10 pages.
        Used as the baseline to detect headings.
        """
        from collections import Counter
        sizes = Counter()

        sample = min(10, doc.page_count)
        for page_num in range(sample):
            page = doc.load_page(page_num)
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = round(span.get("size", 0), 1)
                        if size > 0:
                            sizes[size] += 1

        if not sizes:
            return 12.0
        return sizes.most_common(1)[0][0]

    def _heading_level(self, size: float, modal: float) -> int:
        ratio = size / modal
        if ratio >= 2.0:   return 1
        if ratio >= 1.6:   return 2
        if ratio >= 1.3:   return 3
        return 4

    def _create_merged_paragraph(self, parts: list[str]) -> Block:
        merged_text = ""
        for part in parts:
            if not merged_text:
                merged_text = part
            else:
                if merged_text.endswith("-"):
                    merged_text = merged_text[:-1] + part
                else:
                    merged_text += " " + part
        return Block(
            type=BlockType.PARAGRAPH,
            text=merged_text,
        )