import urllib.request
import urllib.parse
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class FetchedMetadata:
    title:       Optional[str] = None
    author:      Optional[str] = None
    publisher:   Optional[str] = None
    description: Optional[str] = None
    language:    Optional[str] = None
    page_count:  Optional[int] = None
    cover_data:  Optional[bytes] = None
    tags:        list[str] = None
    isbn:        Optional[str] = None
    year:        Optional[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class MetadataFetcher:
    """
    Fetches book metadata from:
        1. OpenLibrary API   (primary)
        2. Google Books API  (fallback + enrichment)

    No API keys required.
    """

    OL_SEARCH   = "https://openlibrary.org/search.json"
    OL_COVER    = "https://covers.openlibrary.org/b/id/{}-L.jpg"
    GB_SEARCH   = "https://www.googleapis.com/books/v1/volumes"
    TIMEOUT     = 8

    # ── Public API ─────────────────────────────────────────────────────────

    def fetch(
        self,
        title:  str,
        author: str = "",
        on_progress=None,   # callback(step: str, pct: int)
    ) -> FetchedMetadata:
        result = FetchedMetadata()

        self._progress(on_progress, "Searching OpenLibrary...", 10)
        ol = self._search_openlibrary(title, author)
        if ol:
            result = ol
            self._progress(on_progress, "Found on OpenLibrary.", 50)
        else:
            self._progress(on_progress, "Trying Google Books...", 50)

        self._progress(on_progress, "Searching Google Books...", 60)
        gb = self._search_google_books(title, author)
        if gb:
            result = self._merge(result, gb)
            self._progress(on_progress, "Enriched from Google Books.", 80)

        if result.cover_data is None and ol and ol.isbn:
            self._progress(on_progress, "Fetching cover art...", 85)
            result.cover_data = self._fetch_cover_ol(ol.isbn)

        self._progress(on_progress, "Done.", 100)
        return result

    # ── OpenLibrary ────────────────────────────────────────────────────────

    def _search_openlibrary(
        self, title: str, author: str
    ) -> Optional[FetchedMetadata]:
        try:
            query = urllib.parse.urlencode({
                "title":  title,
                "author": author,
                "limit":  "1",
                "fields": (
                    "title,author_name,publisher,language,"
                    "first_publish_year,subject,isbn,cover_i,"
                    "number_of_pages_median"
                ),
            })
            url  = f"{self.OL_SEARCH}?{query}"
            data = self._get_json(url)

            docs = data.get("docs", [])
            if not docs:
                return None

            doc = docs[0]

            result          = FetchedMetadata()
            result.title    = doc.get("title")
            result.author   = (doc.get("author_name") or [""])[0]
            result.publisher= (doc.get("publisher")   or [""])[0]
            result.language = (doc.get("language")    or ["en"])[0]
            result.year     = str(doc.get("first_publish_year", ""))
            result.page_count = doc.get("number_of_pages_median")
            result.tags     = (doc.get("subject") or [])[:8]
            isbns           = doc.get("isbn") or []
            result.isbn     = isbns[0] if isbns else None

            # Cover via cover_i
            cover_id = doc.get("cover_i")
            if cover_id:
                result.cover_data = self._fetch_url(
                    self.OL_COVER.format(cover_id)
                )

            return result

        except Exception:
            return None

    # ── Google Books ───────────────────────────────────────────────────────

    def _search_google_books(
        self, title: str, author: str
    ) -> Optional[FetchedMetadata]:
        try:
            q     = f"intitle:{title}"
            if author:
                q += f"+inauthor:{author}"
            query = urllib.parse.urlencode({
                "q":          q,
                "maxResults": "1",
                "printType":  "books",
            })
            url  = f"{self.GB_SEARCH}?{query}"
            data = self._get_json(url)

            items = data.get("items", [])
            if not items:
                return None

            info            = items[0].get("volumeInfo", {})
            result          = FetchedMetadata()
            result.title    = info.get("title")
            result.author   = (info.get("authors") or [""])[0]
            result.publisher= info.get("publisher")
            result.description = info.get("description")
            result.language = info.get("language")
            result.page_count = info.get("pageCount")
            result.year     = (info.get("publishedDate") or "")[:4]
            result.tags     = info.get("categories") or []

            # ISBN
            iids = info.get("industryIdentifiers") or []
            for iid in iids:
                if iid.get("type") in ("ISBN_13", "ISBN_10"):
                    result.isbn = iid.get("identifier")
                    break

            # Cover thumbnail — upgrade to larger size
            img_links = info.get("imageLinks", {})
            thumb     = (
                img_links.get("extraLarge")
                or img_links.get("large")
                or img_links.get("medium")
                or img_links.get("thumbnail")
            )
            if thumb:
                # Force HTTPS
                thumb = thumb.replace("http://", "https://")
                result.cover_data = self._fetch_url(thumb)

            return result

        except Exception:
            return None

    # ── Cover via ISBN fallback ────────────────────────────────────────────

    def _fetch_cover_ol(self, isbn: str) -> bytes | None:
        url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
        data = self._fetch_url(url)
        # OL returns a 1x1 pixel gif for missing covers
        if data and len(data) > 1000:
            return data
        return None

    # ── Merge results ──────────────────────────────────────────────────────

    def _merge(
        self,
        primary:   FetchedMetadata,
        secondary: FetchedMetadata,
    ) -> FetchedMetadata:
        """Fill gaps in primary with secondary data."""
        if not primary.title:       primary.title       = secondary.title
        if not primary.author:      primary.author      = secondary.author
        if not primary.publisher:   primary.publisher   = secondary.publisher
        if not primary.description: primary.description = secondary.description
        if not primary.language:    primary.language    = secondary.language
        if not primary.page_count:  primary.page_count  = secondary.page_count
        if not primary.year:        primary.year        = secondary.year
        if not primary.isbn:        primary.isbn        = secondary.isbn
        if not primary.cover_data:  primary.cover_data  = secondary.cover_data
        if not primary.tags:        primary.tags        = secondary.tags
        return primary

    # ── HTTP helpers ───────────────────────────────────────────────────────

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Vedh/0.1 (reading app)"}
        )
        with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _fetch_url(self, url: str) -> bytes | None:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Vedh/0.1 (reading app)"}
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                return resp.read()
        except Exception:
            return None

    def _progress(self, cb, step: str, pct: int):
        if cb:
            cb(step, pct)