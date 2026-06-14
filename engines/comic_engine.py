import zipfile
import tempfile
import shutil
from pathlib import Path
from uuid import uuid4

from PIL import Image as PilImage
import io

from core.book_model import (
    Book, BookMetadata, Chapter, Block, BlockType
)


# Supported image extensions inside archives
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".avif"}

# Try to import rarfile — optional, only needed for CBR
try:
    import rarfile
    RAR_SUPPORTED = True
except ImportError:
    RAR_SUPPORTED = False


class ComicEngine:

    def load(self, file_path: str) -> Book:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        fmt = path.suffix.lower().lstrip(".")

        if fmt == "cbz":
            return self._load_cbz(path)
        elif fmt == "cbr":
            return self._load_cbr(path)
        elif fmt in ("cb7", "cbt"):
            return self._load_via_patool(path, fmt)
        else:
            raise ValueError(f"Unsupported comic format: {fmt}")

    # ── CBZ ────────────────────────────────────────────────────────────────

    def _load_cbz(self, path: Path) -> Book:
        with zipfile.ZipFile(str(path), "r") as zf:
            image_names = self._filter_images(zf.namelist())
            image_names = self._sort_pages(image_names)

            pages_meta = []
            for name in image_names:
                pages_meta.append({
                    "archive_path": str(path),
                    "archive_member": name
                })

            metadata = self._extract_metadata(path, zf)
            # Fetch cover from the first page
            if image_names:
                try:
                    metadata.cover_data = zf.read(image_names[0])
                except Exception:
                    pass

        return self._build_book(path, metadata, pages_meta)

    # ── CBR ────────────────────────────────────────────────────────────────

    def _load_cbr(self, path: Path) -> Book:
        if not RAR_SUPPORTED:
            raise ImportError(
                "rarfile is not installed. "
                "Run: pip install rarfile\n"
                "You may also need 'unrar' on your system PATH."
            )

        with rarfile.RarFile(str(path), "r") as rf:
            image_names = self._filter_images(rf.namelist())
            image_names = self._sort_pages(image_names)

            pages_meta = []
            for name in image_names:
                pages_meta.append({
                    "archive_path": str(path),
                    "archive_member": name
                })

            metadata = self._extract_metadata_rar(path, rf)
            # Fetch cover from the first page
            if image_names:
                try:
                    metadata.cover_data = rf.read(image_names[0])
                except Exception:
                    pass

        return self._build_book(path, metadata, pages_meta)

    # ── CB7 / CBT ──────────────────────────────────────────────────────────

    def _load_via_patool(self, path: Path, fmt: str) -> Book:
        try:
            import patoolib
        except ImportError:
            raise ImportError(
                "patoolib is not installed. "
                "Run: pip install patool"
            )

        tmp_dir_obj = tempfile.TemporaryDirectory()
        tmp_dir = Path(tmp_dir_obj.name)
        try:
            patoolib.extract_archive(str(path), outdir=str(tmp_dir))
            image_paths = self._collect_images_from_dir(tmp_dir)
            image_paths = self._sort_pages(image_paths)

            pages_meta = []
            for img_path in image_paths:
                pages_meta.append({
                    "file_path": img_path
                })

            metadata = self._extract_metadata_dir(path, tmp_dir)
            # Fetch cover from the first page
            if image_paths:
                try:
                    metadata.cover_data = Path(image_paths[0]).read_bytes()
                except Exception:
                    pass

            book = self._build_book(path, metadata, pages_meta)
            # Keep temp directory alive until book is gc'd
            book.temp_dir = tmp_dir_obj
            return book
        except Exception:
            tmp_dir_obj.cleanup()
            raise

    # ── Build Book Model ───────────────────────────────────────────────────

    def _build_book(
        self,
        path: Path,
        metadata: BookMetadata,
        pages_meta: list[dict],
    ) -> Book:
        if not pages_meta:
            raise ValueError(f"No readable pages found in: {path.name}")

        # Each page is one block inside one chapter
        # Group pages into chapters of 20 pages each for navigation
        chapters = self._paginate_into_chapters(pages_meta)

        return Book(
            id=uuid4(),
            metadata=metadata,
            file_path=str(path),
            format=path.suffix.lower().lstrip("."),
            chapters=chapters,
        )

    def _paginate_into_chapters(
        self, pages_meta: list[dict], chunk_size: int = 20
    ) -> list[Chapter]:
        """
        Group pages into chapters for navigation.
        Short comics (<= chunk_size) get one chapter.
        Longer ones get grouped: Pages 1-20, Pages 21-40 etc.
        """
        if len(pages_meta) <= chunk_size:
            blocks = [
                Block(
                    type=BlockType.IMAGE,
                    image_data=None,
                    alt_text=f"Page {i + 1}",
                    attrs=meta
                )
                for i, meta in enumerate(pages_meta)
            ]
            return [Chapter(
                id=str(uuid4()),
                title="Pages",
                blocks=blocks,
                order=0,
            )]

        chapters = []
        for chunk_start in range(0, len(pages_meta), chunk_size):
            chunk = pages_meta[chunk_start: chunk_start + chunk_size]
            end   = min(chunk_start + chunk_size, len(pages_meta))
            blocks = [
                Block(
                    type=BlockType.IMAGE,
                    image_data=None,
                    alt_text=f"Page {chunk_start + i + 1}",
                    attrs=meta
                )
                for i, meta in enumerate(chunk)
            ]
            chapters.append(Chapter(
                id=str(uuid4()),
                title=f"Pages {chunk_start + 1}–{end}",
                blocks=blocks,
                order=chunk_start // chunk_size,
            ))

        return chapters

    # ── Metadata ───────────────────────────────────────────────────────────

    def _extract_metadata(
        self, path: Path, zf: zipfile.ZipFile
    ) -> BookMetadata:
        # ComicInfo.xml — standard metadata for CBZ comics
        if "ComicInfo.xml" in zf.namelist():
            try:
                return self._parse_comicinfo(zf.read("ComicInfo.xml"), path)
            except Exception:
                pass
        return self._extract_metadata_basic(path)

    def _extract_metadata_rar(
        self, path: Path, rf: rarfile.RarFile
    ) -> BookMetadata:
        if "ComicInfo.xml" in rf.namelist():
            try:
                return self._parse_comicinfo(rf.read("ComicInfo.xml"), path)
            except Exception:
                pass
        return self._extract_metadata_basic(path)

    def _extract_metadata_dir(
        self, path: Path, directory: Path
    ) -> BookMetadata:
        for p in directory.rglob("ComicInfo.xml"):
            try:
                return self._parse_comicinfo(p.read_bytes(), path)
            except Exception:
                pass
        return self._extract_metadata_basic(path)

    def _parse_comicinfo(self, xml_data: bytes, path: Path) -> BookMetadata:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_data)

        def get(tag: str) -> str | None:
            el = root.find(tag)
            return el.text.strip() if el is not None and el.text else None

        title  = get("Title")  or get("Series") or path.stem
        author = get("Writer") or get("Penciller") or "Unknown"
        publisher = get("Publisher")
        summary   = get("Summary")

        # Additional fields
        genre = get("Genre")
        tags = []
        if genre:
            tags = [t.strip().lower() for t in genre.split(",") if t.strip()]

        language = get("LanguageISO") or "en"
        
        return BookMetadata(
            title=title,
            author=author,
            publisher=publisher,
            description=summary,
            language=language,
            tags=tags,
        )

    def _extract_metadata_basic(self, path: Path) -> BookMetadata:
        return BookMetadata(
            title=path.stem,
            author="Unknown",
        )

    # ── Image helpers ──────────────────────────────────────────────────────

    def _filter_images(self, names: list[str]) -> list[str]:
        return [
            n for n in names
            if Path(n).suffix.lower() in IMAGE_EXTENSIONS
            and not Path(n).name.startswith(".")     # skip hidden files
            and "__MACOSX" not in n                  # skip macOS junk
        ]

    def _collect_images_from_dir(self, directory: Path) -> list[str]:
        results = []
        for p in directory.rglob("*"):
            if p.suffix.lower() in IMAGE_EXTENSIONS:
                results.append(str(p))
        return results

    def _sort_pages(self, names: list[str]) -> list[str]:
        """
        Natural sort so page10 comes after page9, not after page1.
        Handles: 001.jpg, page_01.jpg, Chapter1_Page001.jpg etc.
        """
        import re

        def natural_key(s: str) -> list:
            parts = re.split(r"(\d+)", Path(s).name.lower())
            return [
                int(p) if p.isdigit() else p
                for p in parts
            ]

        return sorted(names, key=natural_key)

    def _normalize_image(self, data: bytes) -> bytes | None:
        """
        Normalize non-standard images to PNG.
        Bypasses conversion for JPEG, PNG, and WEBP to avoid heavy CPU/memory work.
        """
        try:
            img = PilImage.open(io.BytesIO(data))
            if img.format in ("JPEG", "PNG", "WEBP"):
                return data

            # Convert palette or RGBA to RGB for consistency
            if img.mode in ("P", "RGBA", "LA"):
                background = PilImage.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA"):
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="PNG")  # No optimize=True (it blocks UI for seconds per page)
            return buf.getvalue()
        except Exception:
            # If Pillow can't open it, return raw bytes and let Qt try
            return data