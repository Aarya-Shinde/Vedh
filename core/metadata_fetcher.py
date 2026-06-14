import urllib.request
import urllib.parse
import json
import re
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
        2. Google Books API  (enrichment)
        3. AniList GraphQL   (manga/comic enrichment)
        4. Goodreads Web     (fallback/enrichment)
        5. AO3 & FF.net      (fanfic URL scrapers)

    No API keys required.
    """

    OL_SEARCH   = "https://openlibrary.org/search.json"
    OL_COVER    = "https://covers.openlibrary.org/b/id/{}-L.jpg"
    GB_SEARCH   = "https://www.googleapis.com/books/v1/volumes"
    TIMEOUT     = 8

    def clean_query(self, title: str) -> str:
        # Remove parenthesized text like (2014), (US), (Digital)
        title = re.sub(r'\([^)]*\)', '', title)
        # Remove bracketed text like [Manga], [CBZ]
        title = re.sub(r'\[[^\]]*\]', '', title)
        # Remove volume indicators: v01, v.01, vol 01, vol. 01, volume 01, #01, no 01 etc.
        title = re.sub(r'(?i)\b(?:v|vol|volume|issue|no|#)\.?\s*\d+\b', '', title)
        # Remove trailing/leading spaces and normalize multiple spaces
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    # ── Public API ─────────────────────────────────────────────────────────

    def fetch(
        self,
        title:  str,
        author: str = "",
        book_type: str = "unknown",
        file_path: str = "",
        format: str = "",
        on_progress=None,   # callback(step: str, pct: int)
    ) -> FetchedMetadata:
        book_type = book_type.lower().strip()
        trimmed_title = title.strip()
        if trimmed_title.startswith("http://") or trimmed_title.startswith("https://"):
            self._progress(on_progress, "Scraping fanfiction link...", 20)
            ao3_or_ffnet = None
            if "archiveofourown.org" in trimmed_title:
                ao3_or_ffnet = self._scrape_ao3(trimmed_title)
            elif "fanfiction.net" in trimmed_title:
                ao3_or_ffnet = self._scrape_ffnet(trimmed_title)

            # If web scraper was fully successful
            if ao3_or_ffnet and ao3_or_ffnet.title and not ao3_or_ffnet.title.startswith("AO3 Work #") and ao3_or_ffnet.author != "Unknown Author":
                self._progress(on_progress, "Done.", 100)
                return ao3_or_ffnet

            # Fallback to local file extraction if web scraping failed or is login-locked
            if file_path and format:
                self._progress(on_progress, "Lock/block detected. Extracting from file...", 50)
                local_meta = self._extract_from_local_file(file_path, format)
                if local_meta:
                    if ao3_or_ffnet:
                        # Prioritize local metadata details
                        result = self._merge(local_meta, ao3_or_ffnet)
                    else:
                        result = local_meta

                    # Ensure Platform and Link details are saved in the description box
                    platform_str = "Archive of Our Own" if "archiveofourown.org" in trimmed_title else "FanFiction.Net"
                    desc = result.description or ""
                    if "Platform:" not in desc:
                        desc += f"\n\n---\nPlatform: {platform_str}\nSource Link: {trimmed_title}"
                        result.description = desc.strip()
                    result.publisher = platform_str

                    self._progress(on_progress, "Done.", 100)
                    return result

            if ao3_or_ffnet:
                self._progress(on_progress, "Done.", 100)
                return ao3_or_ffnet

        result = FetchedMetadata()

        # Clean search queries
        query_title = self.clean_query(title)
        if not query_title:
            query_title = title

        query_author = author.strip()
        if query_author.lower() in ("unknown", ""):
            query_author = ""

        # Route search based on book type to reduce burden
        if book_type == "fanfic":
            self._progress(on_progress, "Please paste an AO3 or FanFiction.net URL.", 100)
            return result

        elif book_type in ("comic", "manga"):
            self._progress(on_progress, "Searching AniList (Manga)...", 50)
            al = self._search_anilist(query_title)
            if al:
                result = al
                self._progress(on_progress, "Found on AniList.", 90)
            self._progress(on_progress, "Done.", 100)
            return result

        elif book_type == "published":
            self._progress(on_progress, "Searching OpenLibrary...", 30)
            ol = self._search_openlibrary(query_title, query_author)
            if ol:
                result = ol
                self._progress(on_progress, "Found on OpenLibrary.", 60)
            
            self._progress(on_progress, "Searching Goodreads...", 70)
            gr = self._search_goodreads(query_title, query_author)
            if gr:
                result = self._merge(result, gr)
                self._progress(on_progress, "Enriched from Goodreads.", 90)
            
            if result.cover_data is None and ol and ol.isbn:
                self._progress(on_progress, "Fetching cover art...", 95)
                result.cover_data = self._fetch_cover_ol(ol.isbn)

            self._progress(on_progress, "Done.", 100)
            return result

        else:
            self._progress(on_progress, "Searching OpenLibrary...", 25)
            ol = self._search_openlibrary(query_title, query_author)
            if ol:
                result = ol
                self._progress(on_progress, "Found on OpenLibrary.", 50)

            self._progress(on_progress, "Searching AniList...", 65)
            al = self._search_anilist(query_title)
            if al:
                result = self._merge(result, al)
                self._progress(on_progress, "Enriched from AniList.", 80)

            self._progress(on_progress, "Searching Goodreads...", 85)
            gr = self._search_goodreads(query_title, query_author)
            if gr:
                result = self._merge(result, gr)
                self._progress(on_progress, "Enriched from Goodreads.", 95)

            if result.cover_data is None and ol and ol.isbn:
                self._progress(on_progress, "Fetching cover art...", 97)
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

    # ── AniList ────────────────────────────────────────────────────────────

    def _search_anilist(self, title: str) -> Optional[FetchedMetadata]:
        try:
            query = """
            query ($search: String) {
              Media (search: $search, type: MANGA) {
                title {
                  romaji
                  english
                }
                description
                genres
                volumes
                startDate {
                  year
                }
                coverImage {
                  large
                }
                staff {
                  edges {
                    role
                    node {
                      name {
                        full
                      }
                    }
                  }
                }
              }
            }
            """
            variables = {"search": title}
            
            data = json.dumps({"query": query, "variables": variables}).encode("utf-8")
            req = urllib.request.Request(
                "https://graphql.anilist.co",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Vedh/0.1"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            
            media = res.get("data", {}).get("Media", {})
            if not media:
                return None
                
            result = FetchedMetadata()
            title_info = media.get("title", {})
            result.title = title_info.get("english") or title_info.get("romaji")
            result.description = media.get("description")
            if result.description:
                result.description = re.sub(r'<[^>]*>', '', result.description).strip()
            
            result.tags = media.get("genres", [])
            
            cover_url = media.get("coverImage", {}).get("large")
            if cover_url:
                result.cover_data = self._fetch_url(cover_url)

            # Parse staff for authors/artists
            staff_edges = media.get("staff", {}).get("edges", [])
            authors = []
            for edge in staff_edges:
                role = (edge.get("role") or "").lower()
                name = edge.get("node", {}).get("name", {}).get("full")
                if name:
                    if any(r in role for r in ("story", "art", "writer", "illustrator", "artist")):
                        if name not in authors:
                            authors.append(name)
            
            if authors:
                result.author = ", ".join(authors)
            else:
                result.author = "Unknown"

            # Parse publication year
            start_date = media.get("startDate", {})
            if start_date and start_date.get("year"):
                result.year = str(start_date.get("year"))
                
            return result
        except Exception:
            return None

    # ── Goodreads Web Scraper ──────────────────────────────────────────────

    def _search_goodreads(self, title: str, author: str) -> Optional[FetchedMetadata]:
        try:
            q = urllib.parse.quote(f"{title} {author}".strip())
            url = f"https://www.goodreads.com/search?q={q}"
            
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # Extract first book link: href="/book/show/12345..."
            link_match = re.search(r'href=["\'](/book/show/\d+[^"\']*)["\']', html)
            if not link_match:
                return None

            book_url = f"https://www.goodreads.com{link_match.group(1)}"
            
            # Fetch book page
            req_book = urllib.request.Request(
                book_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req_book, timeout=self.TIMEOUT) as resp_book:
                book_html = resp_book.read().decode("utf-8", errors="replace")

            result = FetchedMetadata()
            
            # Title
            title_m = re.search(r'<h1[^>]*data-testid="bookTitle"[^>]*>\s*(.*?)\s*</h1>', book_html, re.DOTALL)
            if title_m:
                result.title = re.sub(r'<[^>]*>', '', title_m.group(1)).strip()
            
            # Author
            author_m = re.search(r'<span[^>]*class="ContributorLink__name"[^>]*>\s*(.*?)\s*</span>', book_html, re.DOTALL)
            if author_m:
                result.author = re.sub(r'<[^>]*>', '', author_m.group(1)).strip()

            # Description
            desc_m = re.search(r'<span[^>]*class="Formatted"[^>]*>\s*(.*?)\s*</span>', book_html, re.DOTALL)
            if desc_m:
                desc_clean = re.sub(r'<br\s*/?>', '\n', desc_m.group(1))
                result.description = re.sub(r'<[^>]*>', '', desc_clean).strip()

            # Cover
            cover_m = re.search(r'<img[^>]*class="BookCover__image"[^>]*src=["\'](https://[^"\']+)["\']', book_html)
            if cover_m:
                cover_url = cover_m.group(1)
                result.cover_data = self._fetch_url(cover_url)

            # Pages
            pages_m = re.search(r'(\d+)\s*pages', book_html)
            if pages_m:
                result.page_count = int(pages_m.group(1))

            return result
        except Exception:
            return None

    # ── AO3 Web Scraper ────────────────────────────────────────────────────

    def _scrape_ao3(self, url: str) -> Optional[FetchedMetadata]:
        try:
            req_url = url
            if "?" in url:
                req_url = url + "&view_adult=true"
            else:
                req_url = url + "?view_adult=true"

            req = urllib.request.Request(
                req_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            )
            
            html = ""
            try:
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
            except Exception as net_err:
                print(f"AO3 network fetch failed: {net_err}")

            result = FetchedMetadata()
            result.publisher = "Archive of Our Own"
            
            title = None
            author = None
            summary = None
            tags = []
            language = "en"
            chapters = None
            year = None

            if html:
                # 1. Title
                title_match = re.search(r'<h2[^>]*class="[^"]*title[^"]*"[^>]*>\s*(.*?)\s*</h2>', html, re.DOTALL)
                if title_match:
                    title = re.sub(r'<[^>]*>', '', title_match.group(1)).strip()
                
                # 2. Author
                author_match = re.search(r'<a[^>]*rel="author"[^>]*>\s*(.*?)\s*</a>', html, re.DOTALL)
                if author_match:
                    author = author_match.group(1).strip()
                else:
                    byline_match = re.search(r'<h3[^>]*class="byline[^"]*"[^>]*>\s*<a[^>]*>\s*(.*?)\s*</a>', html, re.DOTALL)
                    if byline_match:
                        author = byline_match.group(1).strip()

                # Fallback to <title> tag parsing
                if not title or not author:
                    title_tag_match = re.search(r'<title>\s*(.*?)\s*</title>', html, re.DOTALL | re.IGNORECASE)
                    if title_tag_match:
                        tag_content = re.sub(r'<[^>]*>', '', title_tag_match.group(1)).strip()
                        parts = tag_content.split(" - ")
                        if len(parts) >= 2:
                            if not title:
                                title = parts[0].strip()
                            if not author:
                                author = parts[1].strip()

                # 3. Summary
                summary_match = re.search(r'<blockquote[^>]*class="[^"]*summary[^"]*"[^>]*>\s*(.*?)\s*</blockquote>', html, re.DOTALL)
                if summary_match:
                    summary_raw = summary_match.group(1)
                    summary_clean = re.sub(r'<br\s*/?>', '\n', summary_raw)
                    summary_clean = re.sub(r'<p[^>]*>', '', summary_clean)
                    summary_clean = re.sub(r'</p>', '\n\n', summary_clean)
                    summary_clean = re.sub(r'<[^>]*>', '', summary_clean)
                    summary = summary_clean.strip()

                # 4. Tags
                tag_matches = re.findall(r'<a[^>]*class="tag"[^>]*>\s*(.*?)\s*</a>', html)
                for t in tag_matches:
                    t_clean = re.sub(r'<[^>]*>', '', t).strip()
                    if t_clean and t_clean not in tags:
                        tags.append(t_clean)

                # 5. Language
                lang_match = re.search(r'<dd[^>]*class="language"[^>]*>\s*(.*?)\s*</dd>', html, re.DOTALL)
                if lang_match:
                    language = re.sub(r'<[^>]*>', '', lang_match.group(1)).strip()

                # 6. Chapters
                chapters_match = re.search(r'<dd[^>]*class="chapters"[^>]*>\s*(.*?)\s*</dd>', html, re.DOTALL)
                if chapters_match:
                    chapters_text = re.sub(r'<[^>]*>', '', chapters_match.group(1)).strip()
                    num_match = re.match(r'^(\d+)', chapters_text)
                    if num_match:
                        chapters = int(num_match.group(1))
                    else:
                        chapters = chapters_text

                # 7. Year
                year_match = re.search(r'<dd[^>]*class="(published|status)"[^>]*>\s*(\d{4})-\d{2}-\d{2}\s*</dd>', html)
                if year_match:
                    year = year_match.group(2)

            if not title:
                work_match = re.search(r'/works/(\d+)', url)
                if work_match:
                    title = f"AO3 Work #{work_match.group(1)}"
                else:
                    title = "AO3 Fanfiction"
            if not author:
                author = "Unknown Author"

            result.title = title
            result.author = author
            result.language = language
            result.tags = tags[:12]
            if isinstance(chapters, int):
                result.page_count = chapters
            if year:
                result.year = year

            # Format details directly in description
            desc = summary or ""
            desc += f"\n\n---\nPlatform: {result.publisher}\nSource Link: {url}"
            if chapters:
                desc += f"\nChapters: {chapters}"
            if year:
                desc += f"\nPublished: {year}"
            result.description = desc.strip()

            return result
        except Exception as e:
            print(f"Error scraping AO3: {e}")
            return None

    # ── FanFiction.net Web Scraper ─────────────────────────────────────────

    def _scrape_ffnet(self, url: str) -> Optional[FetchedMetadata]:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            )
            
            html = ""
            try:
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
            except Exception as net_err:
                print(f"FanFiction.net network fetch failed: {net_err}")

            result = FetchedMetadata()
            result.publisher = "FanFiction.Net"
            
            title = None
            author = None
            summary = None
            tags = []
            language = "en"
            chapters = None
            year = None

            if html:
                # 1. Title
                title_match = re.search(r'<b[^>]*class="xheader_title"[^>]*>\s*(.*?)\s*</b>', html, re.DOTALL)
                if title_match:
                    title = re.sub(r'<[^>]*>', '', title_match.group(1)).strip()

                # 2. Author
                author_match = re.search(r'<a[^>]*class="xheader_author"[^>]*>\s*(.*?)\s*</a>', html, re.DOTALL)
                if author_match:
                    author = re.sub(r'<[^>]*>', '', author_match.group(1)).strip()

                # 3. Summary
                summary_match = re.search(r'<div[^>]*class="xheader_summary"[^>]*>\s*(.*?)\s*</div>', html, re.DOTALL)
                if summary_match:
                    summary = re.sub(r'<[^>]*>', '', summary_match.group(1)).strip()

                # 4. Metadata details
                meta_match = re.search(r'<span[^>]*class="xgray[^"]*"[^>]*>\s*(.*?)\s*</span>', html, re.DOTALL)
                if meta_match:
                    meta_text = re.sub(r'<[^>]*>', '', meta_match.group(1))
                    parts = [p.strip() for p in meta_text.split("-")]
                    
                    for p in parts:
                        if p.startswith("Rated:"):
                            continue
                        elif p in ("English", "Spanish", "French", "German", "Italian", "Japanese"):
                            language = p.lower()[:2]
                        elif "/" in p and any(genre in p for genre in ("Adventure", "Romance", "Angst", "Drama", "Sci-Fi", "Fantasy", "Humor")):
                            tags.extend([g.strip().lower() for g in p.split("/")])
                        elif p.startswith("Chapters:"):
                            try:
                                chapters = int(p.split(":")[1].strip())
                            except Exception:
                                pass
                        elif p.startswith("Published:"):
                            date_str = p.split(":")[1].strip()
                            year_match = re.search(r'(\d{2,4})$', date_str)
                            if year_match:
                                year = year_match.group(1)
                                if len(year) == 2:
                                    year = "20" + year
                        elif p.startswith("Words:") or p.startswith("Favs:") or p.startswith("Follows:") or p.startswith("Reviews:"):
                            continue
                        elif p.startswith("Updated:") or p.startswith("id:"):
                            continue
                        else:
                            if len(p) < 30:
                                tags.append(p)

            # Fallbacks from URL path if scraping was blocked
            if not title:
                url_path = urllib.parse.urlparse(url).path
                path_parts = [p for p in url_path.split("/") if p]
                if len(path_parts) >= 3:
                    title = path_parts[2].replace("-", " ")
                else:
                    title = "Fanfiction Story"
            
            if not author:
                author = "Unknown Author"

            result.title = title
            result.author = author
            result.language = language
            result.tags = tags
            if isinstance(chapters, int):
                result.page_count = chapters
            if year:
                result.year = year

            # Format details directly in description
            desc = summary or ""
            desc += f"\n\n---\nPlatform: {result.publisher}\nSource Link: {url}"
            if chapters:
                desc += f"\nChapters: {chapters}"
            if year:
                desc += f"\nPublished: {year}"
            result.description = desc.strip()

            return result
        except Exception as e:
            print(f"Error scraping FanFiction.net: {e}")
            return None

    # ── Cover via ISBN fallback ────────────────────────────────────────────

    def _fetch_cover_ol(self, isbn: str) -> bytes | None:
        url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
        data = self._fetch_url(url)
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
        if primary.tags is None or len(primary.tags) == 0:
            primary.tags = secondary.tags
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
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                return resp.read()
        except Exception:
            return None

    def _progress(self, cb, step: str, pct: int):
        if cb:
            cb(step, pct)

    def _extract_from_local_file(self, file_path: str, fmt: str) -> Optional[FetchedMetadata]:
        try:
            from pathlib import Path
            path = Path(file_path)
            if not path.exists():
                return None
            
            fmt = fmt.lower().strip()
            result = FetchedMetadata()
            
            if fmt == "epub":
                from engines.epub_engine import EpubEngine
                engine = EpubEngine()
                book = engine.load(str(path))
                if book and book.metadata:
                    meta = book.metadata
                    result.title = meta.title
                    result.author = meta.author
                    result.publisher = meta.publisher
                    result.description = meta.description
                    result.language = meta.language
                    result.cover_data = meta.cover_data
                    result.tags = meta.tags
                    
            elif fmt == "pdf":
                from engines.pdf_engine import PdfEngine
                engine = PdfEngine()
                book = engine.load(str(path))
                if book and book.metadata:
                    meta = book.metadata
                    result.title = meta.title
                    result.author = meta.author
                    result.description = meta.description
                    result.language = meta.language
                    result.cover_data = meta.cover_data
                    result.tags = meta.tags
                    
            if result.title == "Unknown Title":
                result.title = None
            if result.author == "Unknown Author":
                result.author = None
                
            return result
        except Exception as e:
            print(f"Error extracting metadata from local file: {e}")
            return None


def extract_fanfic_url(file_path: str, fmt: str) -> Optional[str]:
    import re
    from pathlib import Path
    
    path = Path(file_path)
    if not path.exists():
        return None
        
    fmt = fmt.lower().strip()
    
    # URL patterns to search for
    patterns = [
        r'https?://(?:www\.)?archiveofourown\.org/works/\d+\S*',
        r'https?://(?:www\.)?fanfiction\.net/s/\d+\S*'
    ]
    
    # 1. EPUB
    if fmt == "epub":
        try:
            import ebooklib
            from ebooklib import epub
            book = epub.read_epub(str(path), options={"ignore_ncx": True})
            count = 0
            for item_id, _ in book.spine:
                item = book.get_item_with_id(item_id)
                if item and item.get_type() == ebooklib.ITEM_DOCUMENT:
                    html = item.get_content().decode("utf-8", errors="replace")
                    for pattern in patterns:
                        urls = re.findall(pattern, html)
                        if urls:
                            clean_url = re.split(r'[\s"\'>\]\)]', urls[0])[0]
                            return clean_url
                    count += 1
                    if count >= 3:
                        break
        except Exception as e:
            print(f"Error extracting URL from EPUB: {e}")
            
    # 2. PDF
    elif fmt == "pdf":
        try:
            import fitz
            doc = fitz.open(str(path))
            for i in range(min(3, doc.page_count)):
                page = doc.load_page(i)
                text = page.get_text("text")
                for pattern in patterns:
                    urls = re.findall(pattern, text)
                    if urls:
                        clean_url = re.split(r'[\s"\'>\]\)]', urls[0])[0]
                        doc.close()
                        return clean_url
            doc.close()
        except Exception as e:
            print(f"Error extracting URL from PDF: {e}")
            
    # 3. HTML / TXT / Other text files
    else:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(15000)
            for pattern in patterns:
                urls = re.findall(pattern, head)
                if urls:
                    clean_url = re.split(r'[\s"\'>\]\)]', urls[0])[0]
                    return clean_url
        except Exception as e:
            print(f"Error extracting URL from text file: {e}")
            
    return None