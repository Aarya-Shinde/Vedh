import re
from pathlib import Path


# ── Keyword banks ──────────────────────────────────────────────────────────

FANFIC_TEXT_SIGNALS = [
    "fanfiction.net", "archiveofourown", "archiveofourown.org",
    "ao3", "wattpad", "quotev",
    "i don't own", "i do not own",
    "disclaimer", "no copyright infringement",
    "originally posted", "cross-posted",
    "beta reader", "unbeta'd", "unbetaed",
    "author's note", "a/n:", "a.n:",
    "chapter posted", "kudos", "comments appreciated",
]

FANFIC_FILENAME_SIGNALS = [
    "ao3", "ffnet", "fanfic", "fanfiction",
    "wattpad", "quotev",
]

FANFIC_PUBLISHER_SIGNALS = [
    "archiveofourown", "fanfiction.net",
    "wattpad", "quotev",
]

MANGA_FILENAME_SIGNALS = [
    "vol.", "vol_", "ch.", "ch_", "chapter",
    "[scan]", "[raw]", "[digital]",
    "tankoubon", "manga",
]

MANGA_PUBLISHER_SIGNALS = [
    "shonen jump", "viz media", "kodansha",
    "square enix", "dark horse", "seven seas",
    "yen press", "tokyopop", "vertical",
]

COMIC_FILENAME_SIGNALS = [
    "dc comics", "marvel", "image comics",
    "darkhorse", "idw",
]

USERNAME_PATTERN = re.compile(
    r"^[a-z0-9_\-\.]{3,30}$", re.IGNORECASE
)
REAL_NAME_PATTERN = re.compile(
    r"^[A-Z][a-z]+ [A-Z][a-z]+$"
)
ISBN_PATTERN = re.compile(
    r"(isbn[:\s]*)?(97[89][\d\-]{10}|\d{9}[\dX])",
    re.IGNORECASE,
)


class BookClassifier:
    """
    Analyses a book's metadata, filename, and optionally
    its text content to assign a book_type and suggest tags.

    Returns:
        book_type : "fanfic" | "published" | "manga" | "comic" | "unknown"
        tag_names : list of suggested tag name strings
    """

    def classify(
        self,
        file_path:   str,
        fmt:         str,
        title:       str       = "",
        author:      str       = "",
        publisher:   str       = "",
        description: str       = "",
        sample_text: str       = "",
        image_block_ratio: float = 0.0,
    ) -> tuple[str, list[str]]:

        path      = Path(file_path)
        filename  = path.stem.lower()
        publisher = (publisher or "").lower()
        author    = (author    or "").lower()
        desc      = (description or "").lower()
        sample    = (sample_text  or "").lower()
        tags: list[str] = []

        # ── Comics (CBZ/CBR always) ────────────────────────────────────────
        if fmt in ("cbz", "cbr", "cb7", "cbt"):
            book_type = self._classify_comic_archive(
                filename, publisher, tags
            )
            return book_type, tags

        # ── PDF image-heavy → manga ────────────────────────────────────────
        if fmt == "pdf" and image_block_ratio >= 0.85:
            tags.append("manga")
            return "manga", tags

        # ── Fanfic detection ───────────────────────────────────────────────
        fanfic_score = 0

        # Text content is strongest signal
        for signal in FANFIC_TEXT_SIGNALS:
            if signal in sample:
                fanfic_score += 3
                break

        # Publisher domain
        for signal in FANFIC_PUBLISHER_SIGNALS:
            if signal in publisher:
                fanfic_score += 3
                break

        # Filename
        for signal in FANFIC_FILENAME_SIGNALS:
            if signal in filename:
                fanfic_score += 2
                break

        # Author looks like a username
        if USERNAME_PATTERN.match(author.strip()) and \
                not REAL_NAME_PATTERN.match(author.strip()):
            fanfic_score += 1

        # Description hints
        for signal in FANFIC_TEXT_SIGNALS:
            if signal in desc:
                fanfic_score += 1
                break

        if fanfic_score >= 3:
            tags.append("fanfic")
            return "fanfic", tags

        # ── Published book detection ───────────────────────────────────────
        published_score = 0

        if ISBN_PATTERN.search(desc) or ISBN_PATTERN.search(sample):
            published_score += 3

        if publisher and publisher not in FANFIC_PUBLISHER_SIGNALS:
            published_score += 2

        if REAL_NAME_PATTERN.match(author.strip()):
            published_score += 1

        for signal in MANGA_PUBLISHER_SIGNALS:
            if signal in publisher:
                tags.append("manga")
                return "manga", tags

        if published_score >= 2:
            tags.append("published")
            return "published", tags

        # ── Manga filename signals ─────────────────────────────────────────
        for signal in MANGA_FILENAME_SIGNALS:
            if signal in filename:
                tags.append("manga")
                return "manga", tags

        return "unknown", tags

    # ── Comic archive classification ───────────────────────────────────────

    def _classify_comic_archive(
        self,
        filename:  str,
        publisher: str,
        tags:      list[str],
    ) -> str:
        for signal in MANGA_PUBLISHER_SIGNALS:
            if signal in publisher:
                tags.append("manga")
                return "manga"

        for signal in MANGA_FILENAME_SIGNALS:
            if signal in filename:
                tags.append("manga")
                return "manga"

        for signal in COMIC_FILENAME_SIGNALS:
            if signal in filename:
                tags.append("comic")
                return "comic"

        # Default for CBZ/CBR without stronger signals
        tags.append("comic")
        return "comic"

    # ── Sample text extraction ─────────────────────────────────────────────

    def extract_sample(self, file_path: str, fmt: str) -> str:
        """
        Extract a small text sample from the first few pages.
        Used for fanfic detection.
        """
        try:
            if fmt == "epub":
                return self._sample_epub(file_path)
            elif fmt == "pdf":
                return self._sample_pdf(file_path)
        except Exception:
            pass
        return ""

    def _sample_epub(self, file_path: str) -> str:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book = epub.read_epub(file_path, options={"ignore_ncx": True})
        text_parts = []
        count = 0

        for item_id, _ in book.spine:
            if count >= 3:
                break
            item = book.get_item_with_id(item_id)
            if item and item.get_type() == ebooklib.ITEM_DOCUMENT:
                html  = item.get_content().decode("utf-8", errors="replace")
                soup  = BeautifulSoup(html, "html.parser")
                text  = soup.get_text(separator=" ", strip=True)
                text_parts.append(text[:2000])
                count += 1

        return " ".join(text_parts)

    def _sample_pdf(self, file_path: str) -> str:
        import fitz
        doc  = fitz.open(file_path)
        text = ""
        for i in range(min(3, doc.page_count)):
            text += doc.load_page(i).get_text()
        doc.close()
        return text[:6000]

    def image_block_ratio(self, file_path: str) -> float:
        """
        For PDFs — what fraction of blocks are images.
        Used to detect image-heavy manga PDFs.
        """
        try:
            import fitz
            doc          = fitz.open(file_path)
            total_blocks = 0
            image_blocks = 0
            sample_pages = min(10, doc.page_count)

            for i in range(sample_pages):
                page   = doc.load_page(i)
                blocks = page.get_text("dict").get("blocks", [])
                for b in blocks:
                    total_blocks += 1
                    if b.get("type") == 1:
                        image_blocks += 1
            doc.close()

            if total_blocks == 0:
                return 0.0
            return image_blocks / total_blocks
        except Exception:
            return 0.0