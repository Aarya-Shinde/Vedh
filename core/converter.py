import shutil
from pathlib import Path


class ConversionError(Exception):
    pass


class Converter:
    """
    Handles all format conversions.

    Supported:
        EPUB → PDF    via ebooklib + WeasyPrint
        PDF  → EPUB   via PyMuPDF + ebooklib
    """

    # ── Public API ─────────────────────────────────────────────────────────

    def epub_to_pdf(
        self,
        epub_path:  str,
        on_progress=None,   # callback(step: str, pct: int)
    ) -> str:
        """
        Convert EPUB to PDF.
        Returns path to the output PDF file.
        """
        src  = Path(epub_path)
        dest = src.with_suffix(".pdf")

        if dest.exists():
            dest = src.with_stem(src.stem + "_converted").with_suffix(".pdf")

        self._progress(on_progress, "Parsing EPUB...", 10)
        html_parts, metadata = self._epub_to_html(str(src))

        self._progress(on_progress, "Building HTML document...", 40)
        combined_html = self._combine_html(html_parts, metadata)

        self._progress(on_progress, "Rendering PDF...", 70)
        self._html_to_pdf(combined_html, str(dest))

        self._progress(on_progress, "Done.", 100)
        return str(dest)

    def pdf_to_epub(
        self,
        pdf_path:   str,
        on_progress=None,
    ) -> str:
        """
        Convert PDF to EPUB.
        Returns path to the output EPUB file.
        """
        src  = Path(pdf_path)
        dest = src.with_suffix(".epub")

        if dest.exists():
            dest = src.with_stem(src.stem + "_converted").with_suffix(".epub")

        self._progress(on_progress, "Parsing PDF...", 10)
        chapters, metadata, cover = self._pdf_to_content(str(src))

        self._progress(on_progress, "Building EPUB structure...", 50)
        self._content_to_epub(chapters, metadata, cover, str(dest))

        self._progress(on_progress, "Done.", 100)
        return str(dest)

    # ── EPUB → PDF ─────────────────────────────────────────────────────────

    def _epub_to_html(self, path: str) -> tuple[list[str], dict]:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book  = epub.read_epub(path, options={"ignore_ncx": True})
        parts = []

        meta = {
            "title":  self._get_meta(book, "title")   or "Untitled",
            "author": self._get_meta(book, "creator")  or "Unknown",
        }

        for item_id, _ in book.spine:
            item = book.get_item_with_id(item_id)
            if item is None:
                continue
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            html = item.get_content().decode("utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
            body = soup.find("body")
            if body:
                parts.append(str(body))

        return parts, meta

    def _combine_html(self, parts: list[str], meta: dict) -> str:
        title  = meta.get("title",  "")
        author = meta.get("author", "")

        body_content = "\n<div style='page-break-after:always'></div>\n".join(
            parts
        )

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        @page {{
            margin: 2cm 2.5cm;
            size: A4;
        }}
        body {{
            font-family: Georgia, serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #1A1A1A;
        }}
        h1, h2, h3, h4 {{
            font-family: Georgia, serif;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        h1 {{ font-size: 22pt; }}
        h2 {{ font-size: 17pt; }}
        h3 {{ font-size: 14pt; }}
        p  {{
            margin: 0 0 0.8em 0;
            text-align: justify;
        }}
        blockquote {{
            border-left: 3px solid #C4B9A8;
            margin: 1em 2em;
            padding: 0.5em 1em;
            color: #4A4A4A;
            font-style: italic;
        }}
        img {{
            max-width: 100%;
            height: auto;
        }}
        .title-page {{
            text-align: center;
            margin-top: 8cm;
        }}
        .title-page h1 {{ font-size: 28pt; }}
        .title-page p  {{ font-size: 14pt; color: #555; }}
    </style>
</head>
<body>
    <div class="title-page">
        <h1>{title}</h1>
        <p>{author}</p>
    </div>
    <div style="page-break-after:always"></div>
    {body_content}
</body>
</html>"""

    def _html_to_pdf(self, html: str, dest: str):
        try:
            from weasyprint import HTML, CSS
            HTML(string=html).write_pdf(dest)
        except ImportError:
            raise ConversionError(
                "WeasyPrint is not installed.\n"
                "Run: pip install weasyprint"
            )
        except Exception as e:
            raise ConversionError(f"PDF rendering failed: {e}")

    # ── PDF → EPUB ─────────────────────────────────────────────────────────

    def _pdf_to_content(
        self, path: str
    ) -> tuple[list[dict], dict, bytes | None]:
        import fitz

        doc      = fitz.open(path)
        meta     = doc.metadata or {}
        toc      = doc.get_toc()
        chapters = []
        cover    = None

        # Extract cover from first page
        if doc.page_count > 0:
            pix   = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
            cover = pix.tobytes("png")

        if toc:
            chapters = self._pdf_chapters_from_toc(doc, toc)
        else:
            chapters = self._pdf_chapters_flat(doc)

        doc.close()

        metadata = {
            "title":  meta.get("title")  or Path(path).stem,
            "author": meta.get("author") or "Unknown",
        }
        return chapters, metadata, cover

    def _pdf_chapters_from_toc(
        self, doc, toc: list
    ) -> list[dict]:
        chapters = []
        level1   = [(t, p) for l, t, p in toc if l == 1]

        for i, (title, start_page) in enumerate(level1):
            end_page = (
                level1[i + 1][1] - 1
                if i + 1 < len(level1)
                else doc.page_count
            )
            html = self._pages_to_html(doc, start_page - 1, end_page - 1)
            chapters.append({"title": title, "html": html})

        return chapters

    def _pdf_chapters_flat(self, doc) -> list[dict]:
        """Group every 10 pages into one chapter."""
        chapters = []
        chunk    = 10

        for start in range(0, doc.page_count, chunk):
            end   = min(start + chunk - 1, doc.page_count - 1)
            html  = self._pages_to_html(doc, start, end)
            title = f"Pages {start + 1}–{end + 1}"
            chapters.append({"title": title, "html": html})

        return chapters

    def _pages_to_html(self, doc, start: int, end: int) -> str:
        import fitz
        lines = []
        for page_num in range(start, min(end + 1, doc.page_count)):
            page  = doc.load_page(page_num)
            words = page.get_text("words")
            if words:
                text = " ".join(w[4] for w in words)
                lines.append(f"<p>{text}</p>")
        return "\n".join(lines)

    def _content_to_epub(
        self,
        chapters: list[dict],
        metadata: dict,
        cover:    bytes | None,
        dest:     str,
    ):
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_title(metadata.get("title", "Untitled"))
        book.set_language("en")
        book.add_author(metadata.get("author", "Unknown"))

        # Cover
        if cover:
            book.set_cover("cover.png", cover)

        spine    = ["nav"]
        toc      = []
        chapters_epub = []

        for i, ch in enumerate(chapters):
            uid      = f"chapter_{i + 1}"
            filename = f"{uid}.xhtml"

            html = f"""<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{ch['title']}</title>
    <style>
        body {{ font-family: Georgia, serif; font-size: 11pt;
                line-height: 1.6; margin: 2em; }}
        p    {{ margin: 0 0 0.8em; text-align: justify; }}
    </style>
</head>
<body>
    <h2>{ch['title']}</h2>
    {ch['html']}
</body>
</html>"""

            epub_ch = epub.EpubHtml(
                title=ch["title"], file_name=filename, lang="en"
            )
            epub_ch.content = html.encode("utf-8")
            book.add_item(epub_ch)
            chapters_epub.append(epub_ch)
            spine.append(epub_ch)
            toc.append(epub.Link(filename, ch["title"], uid))

        book.toc   = toc
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub.write_epub(dest, book)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _get_meta(self, book, tag: str) -> str | None:
        values = book.get_metadata("DC", tag)
        if values:
            val = values[0]
            return val[0] if isinstance(val, tuple) else val
        return None

    def _progress(self, cb, step: str, pct: int):
        if cb:
            cb(step, pct)