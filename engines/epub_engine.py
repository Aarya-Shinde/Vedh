from pathlib import Path
from uuid import uuid4

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from core.book_model import (
    Book, BookMetadata, Chapter, Block, BlockType
)


class EpubEngine:

    def load(self, file_path: str) -> Book:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        self.file_path = file_path
        book = epub.read_epub(str(path), options={"ignore_ncx": True})

        metadata = self._extract_metadata(book)
        chapters = self._extract_chapters(book)

        return Book(
            id=uuid4(),
            metadata=metadata,
            file_path=file_path,
            format="epub",
            chapters=chapters,
        )

    # ── Metadata ───────────────────────────────────────────────────────────

    def _extract_metadata(self, book: epub.EpubBook) -> BookMetadata:
        title  = self._get_meta(book, "title")  or "Unknown Title"
        author = self._get_meta(book, "creator") or "Unknown Author"
        lang   = self._get_meta(book, "language") or "en"
        publisher   = self._get_meta(book, "publisher")
        description = self._get_meta(book, "description")

        cover_data = self._extract_cover(book)

        return BookMetadata(
            title=title,
            author=author,
            language=lang,
            publisher=publisher,
            description=description,
            cover_data=cover_data,
        )

    def _get_meta(self, book: epub.EpubBook, tag: str) -> str | None:
        values = book.get_metadata("DC", tag)
        if values:
            val = values[0]
            # ebooklib returns either a string or a (string, dict) tuple
            return val[0] if isinstance(val, tuple) else val
        return None

    def _extract_cover(self, book: epub.EpubBook) -> bytes | None:
        # Strategy 1: look for item with id 'cover-image' or type image/cover
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_COVER:
                return item.get_content()

        # Strategy 2: look for item whose id contains 'cover'
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            if "cover" in item.get_name().lower():
                return item.get_content()

        return None

    # ── Chapters ───────────────────────────────────────────────────────────

    def _extract_chapters(self, book: epub.EpubBook) -> list[Chapter]:
        chapters = []
        order = 0

        # Walk the spine — this preserves reading order
        for item_id, _ in book.spine:
            item = book.get_item_with_id(item_id)
            if item is None:
                continue
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            html = item.get_content().decode("utf-8", errors="replace")
            blocks = self._parse_html(html)

            if not blocks:
                continue

            # Try to get a chapter title from first heading block
            title = self._find_title(blocks) or item.get_name()

            chapters.append(Chapter(
                id=str(uuid4()),
                title=title,
                blocks=blocks,
                order=order,
            ))
            order += 1

        return chapters

    def _find_title(self, blocks: list[Block]) -> str | None:
        for block in blocks:
            if block.type == BlockType.HEADING:
                return block.text
        return None

    # ── HTML → Blocks ──────────────────────────────────────────────────────

    def _parse_html(self, html: str) -> list[Block]:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("body") or soup
        blocks = []

        for element in body.children:
            parsed = self._parse_element(element)
            if parsed:
                blocks.extend(parsed)

        return blocks

    def _extract_block_styles(self, element) -> dict:
        attrs = {}
        if not hasattr(element, "name") or element.name is None:
            return attrs

        style = element.get("style", "").lower()

        # Alignment
        align = None
        if "text-align: center" in style or "text-align:center" in style:
            align = "center"
        elif "text-align: right" in style or "text-align:right" in style:
            align = "right"
        elif "text-align: justify" in style or "text-align:justify" in style:
            align = "justify"
        elif element.get("align", "").lower() == "center":
            align = "center"
        else:
            classes = element.get("class", [])
            if isinstance(classes, str):
                classes = [classes]
            classes_str = " ".join(classes).lower()
            if "center" in classes_str or "centered" in classes_str or "dedication" in classes_str or "title" in classes_str:
                align = "center"
        if align:
            attrs["align"] = align

        # Italics
        italic = False
        if "font-style: italic" in style or "font-style:italic" in style:
            italic = True
        elif element.name in ("i", "em"):
            italic = True
        else:
            inner_text = element.get_text(strip=True)
            italic_elements = element.find_all(["i", "em"])
            if italic_elements:
                italic_text = "".join(ie.get_text(strip=True) for ie in italic_elements)
                if len(inner_text) > 0 and (len(italic_text) / len(inner_text)) >= 0.8:
                    italic = True
            classes = element.get("class", [])
            if isinstance(classes, str):
                classes = [classes]
            classes_str = " ".join(classes).lower()
            if "italic" in classes_str or "dedication" in classes_str or "copyright" in classes_str:
                italic = True
        if italic:
            attrs["italic"] = True

        # Bold
        bold = False
        if "font-weight: bold" in style or "font-weight:bold" in style:
            bold = True
        elif element.name in ("b", "strong"):
            bold = True
        else:
            inner_text = element.get_text(strip=True)
            bold_elements = element.find_all(["b", "strong"])
            if bold_elements:
                bold_text = "".join(be.get_text(strip=True) for be in bold_elements)
                if len(inner_text) > 0 and (len(bold_text) / len(inner_text)) >= 0.8:
                    bold = True
        if bold:
            attrs["bold"] = True

        return attrs

    def _parse_element(self, element) -> list[Block]:
        # Skip plain strings (whitespace between tags)
        if not hasattr(element, "name") or element.name is None:
            return []

        tag = element.name.lower()
        blocks = []

        # ── Headings ──
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = element.get_text(separator=" ", strip=True)
            if text:
                attrs = self._extract_block_styles(element)
                blocks.append(Block(
                    type=BlockType.HEADING,
                    text=text,
                    level=int(tag[1]),
                    attrs=attrs,
                ))

        # ── Paragraphs ──
        elif tag == "p":
            text = element.get_text(separator=" ", strip=True)
            if text:
                attrs = self._extract_block_styles(element)
                blocks.append(Block(
                    type=BlockType.PARAGRAPH,
                    text=text,
                    attrs=attrs,
                ))

        # ── Blockquotes ──
        elif tag == "blockquote":
            text = element.get_text(separator=" ", strip=True)
            if text:
                attrs = self._extract_block_styles(element)
                if "italic" not in attrs:
                    attrs["italic"] = True
                blocks.append(Block(
                    type=BlockType.QUOTE,
                    text=text,
                    attrs=attrs,
                ))

        # ── Images ──
        elif tag in ("img", "image"):
            src = element.get("src") or element.get("xlink:href") or element.get("href", "")
            alt = element.get("alt", "")
            blocks.append(Block(
                type=BlockType.IMAGE,
                image_path=src,
                alt_text=alt,
                attrs={
                    "epub_file_path": getattr(self, "file_path", ""),
                    "epub_image_href": src,
                }
            ))

        # ── Horizontal rule ──
        elif tag == "hr":
            blocks.append(Block(type=BlockType.HORIZONTAL_RULE))

        # ── Page breaks (epub:type or class hints) ──
        elif tag == "div":
            epub_type = element.get("epub:type", "")
            classes   = " ".join(element.get("class", []))
            if "pagebreak" in epub_type.lower() or "page-break" in classes.lower():
                blocks.append(Block(type=BlockType.PAGE_BREAK))
            else:
                # Recurse into divs
                for child in element.children:
                    blocks.extend(self._parse_element(child))

        # ── Tables — stub, not rendered yet ──
        elif tag == "table":
            blocks.append(Block(
                type=BlockType.TABLE,
                attrs={"raw_html": str(element)},
            ))

        # ── Code blocks — stub ──
        elif tag in ("pre", "code"):
            text = element.get_text()
            blocks.append(Block(
                type=BlockType.CODE_BLOCK,
                text=text,
            ))

        # ── Footnotes — stub ──
        elif tag == "a":
            epub_type = element.get("epub:type", "")
            if "noteref" in epub_type:
                blocks.append(Block(
                    type=BlockType.FOOTNOTE_REF,
                    text=element.get_text(strip=True),
                    attrs={"href": element.get("href", "")},
                ))

        # ── Lists — flatten into paragraphs for now ──
        elif tag in ("ul", "ol"):
            for li in element.find_all("li", recursive=False):
                text = li.get_text(separator=" ", strip=True)
                if text:
                    prefix = "• " if tag == "ul" else "– "
                    blocks.append(Block(
                        type=BlockType.PARAGRAPH,
                        text=prefix + text,
                    ))

        # ── Section / article — recurse ──
        elif tag in ("section", "article", "main", "aside", "figure"):
            for child in element.children:
                blocks.extend(self._parse_element(child))

        return blocks