from PyQt6.QtGui import (
    QPainter, QPixmap, QImage, QColor,
    QBrush, QPen, QFont
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF
from collections import OrderedDict

from core.book_model import Block, BlockType


class ImageRenderer:
    """
    Draws image-based blocks onto a QPainter surface.

    Handles:
        IMAGE blocks — inline book images, comic pages, PDF page renders

    Comic mode:
        When is_comic=True, images are rendered to fill the full
        viewport with fit/fill modes rather than inline flow.
    """

    def __init__(self):
        self._theme:      dict  = {}
        self._page_width: float = 700.0
        self._is_comic:   bool  = False
        self._fit_mode:   str   = "fit_width"   # fit_width | fit_height | fit_page | original
        self._pixmap_cache: OrderedDict = OrderedDict()
        self._scroll_y:   float = 0.0

    # ── Configuration ──────────────────────────────────────────────────────

    def configure(
        self,
        theme: dict,
        page_width: float,
        is_comic: bool   = False,
        fit_mode: str    = "fit_width",
    ):
        self._theme      = theme
        self._page_width = page_width
        self._is_comic   = is_comic
        self._fit_mode   = fit_mode

    def set_fit_mode(self, mode: str):
        """fit_width | fit_height | fit_page | original"""
        self._fit_mode = mode
        self._pixmap_cache.clear()

    def set_scroll_y(self, val: float):
        self._scroll_y = val

    def set_comic_mode(self, enabled: bool):
        self._is_comic = enabled
        self._pixmap_cache.clear()

    # ── Public API ─────────────────────────────────────────────────────────

    def draw_block(
        self,
        painter: QPainter,
        block: Block,
        x: float,
        y: float,
        viewport_height: float = 0.0,
    ) -> float:
        """
        Draw an image block at (x, y).
        Returns height consumed.

        viewport_height is used in comic/fit_page mode to
        scale the image to fill the full page.
        """
        if block.type != BlockType.IMAGE:
            return 0.0

        pixmap = self._get_pixmap(block)

        if pixmap is None or pixmap.isNull():
            return self._draw_broken_image(painter, block, x, y)

        if self._is_comic:
            return self._draw_comic_page(
                painter, pixmap, x, y, viewport_height
            )
        else:
            return self._draw_inline_image(painter, pixmap, x, y, viewport_height)

    def draw_page(
        self,
        painter: QPainter,
        block: Block,
        viewport_width: float,
        viewport_height: float,
    ):
        """
        Full-viewport comic page render.
        Used by the comic reader widget directly.
        """
        pixmap = self._get_pixmap(block)
        if pixmap is None or pixmap.isNull():
            self._draw_broken_image(painter, block, 0, 0)
            return

        self._draw_comic_page(
            painter, pixmap, 0, 0,
            viewport_height,
            viewport_width=viewport_width,
        )

    # ── Inline image (books / PDF) ─────────────────────────────────────────

    def _draw_inline_image(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        x: float,
        y: float,
        viewport_height: float = 0.0,
    ) -> float:
        orig_w = pixmap.width()
        orig_h = pixmap.height()

        if orig_w == 0:
            return 0.0

        # Scale to page width, preserve aspect ratio
        scale    = self._page_width / orig_w
        target_w = self._page_width
        target_h = orig_h * scale

        # Cap height so it fits within the viewport/page vertical bounds
        margin_v = float(self._theme.get("margin_v", 40.0))
        usable_height = (viewport_height - margin_v * 2) if viewport_height > 0 else (self._page_width * 1.5)

        if target_h > usable_height:
            scale = usable_height / orig_h
            target_h = usable_height
            target_w = orig_w * scale

        # Center horizontally
        offset_x = x + (self._page_width - target_w) / 2
        
        target_rect = QRectF(offset_x, y, target_w, target_h)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(target_rect, pixmap, QRectF(pixmap.rect()))

        para_spacing = float(self._theme.get("paragraph_spacing", 14))
        return target_h + para_spacing

    # ── Comic page ─────────────────────────────────────────────────────────

    def _draw_comic_page(
        self,
        painter: QPainter,
        pixmap: QPixmap,
        x: float,
        y: float,
        viewport_height: float,
        viewport_width: float | None = None,
    ) -> float:
        vw = viewport_width  or self._page_width
        vh = viewport_height or self._page_width * 1.4

        orig_w = pixmap.width()
        orig_h = pixmap.height()

        if orig_w == 0 or orig_h == 0:
            return vh

        if self._fit_mode == "fit_page":
            # Scale to fit entirely within viewport
            scale = min(vw / orig_w, vh / orig_h)

        elif self._fit_mode == "fit_width":
            # Scale to fill width
            scale = vw / orig_w

        elif self._fit_mode == "fit_height":
            # Scale to fill height
            scale = vh / orig_h

        else:  # original
            scale = 1.0

        target_w = orig_w * scale
        target_h = orig_h * scale

        # Center in viewport
        offset_x = x + max(0.0, (vw - target_w) / 2.0)
        if target_h > vh:
            offset_y = y - self._scroll_y
        else:
            offset_y = y + (vh - target_h) / 2.0

        # Black background for comic pages
        painter.fillRect(
            QRectF(x, y, vw, vh),
            QColor("#000000"),
        )
        
        target_rect = QRectF(offset_x, offset_y, target_w, target_h)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(target_rect, pixmap, QRectF(pixmap.rect()))

        return vh

    # ── Broken image fallback ──────────────────────────────────────────────

    def _draw_broken_image(
        self,
        painter: QPainter,
        block: Block,
        x: float,
        y: float,
    ) -> float:
        h = 120.0
        rect = QRectF(x, y, self._page_width, h)

        painter.setBrush(QBrush(QColor("#1A1A1A")))
        pen = QPen(QColor("#333333"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 6, 6)

        font = QFont()
        font.setFamily("Segoe UI")
        font.setPointSizeF(12)
        painter.setFont(font)
        painter.setPen(QColor("#666666"))

        label = block.alt_text or "Image unavailable"
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"🖼  {label}")

        return h + float(self._theme.get("paragraph_spacing", 14))

    # ── Pixmap loading + cache ─────────────────────────────────────────────

    def _get_pixmap(self, block: Block) -> QPixmap | None:
        cache_key = (id(block), block.image_path, len(block.image_data) if block.image_data else 0)
        
        # If cache hit, move to end (MRU)
        if cache_key in self._pixmap_cache:
            pixmap = self._pixmap_cache.pop(cache_key)
            self._pixmap_cache[cache_key] = pixmap
            return pixmap

        pixmap = self._load_pixmap(block)
        if pixmap and not pixmap.isNull():
            pixmap = self._apply_dark_mode_filters(pixmap)
            # Evict oldest if full
            if len(self._pixmap_cache) >= 50:
                self._pixmap_cache.popitem(last=False)
            self._pixmap_cache[cache_key] = pixmap
        return pixmap

    def _apply_dark_mode_filters(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull() or self._is_comic:
            return pixmap

        # Check if theme background is dark
        from PyQt6.QtGui import QColor, QImage
        bg_hex = self._theme.get("background", self._theme.get("bg", "#FAF9F6"))
        try:
            bg_color = QColor(bg_hex)
        except Exception:
            bg_color = QColor("#FAF9F6")

        if bg_color.lightness() >= 128:
            return pixmap

        image = pixmap.toImage()
        w, h = image.width(), image.height()
        if w == 0 or h == 0:
            return pixmap

        # Sample pixels to check if it has a light background / line-art
        light_pixels = 0
        total_samples = min(100, w * h)
        
        # Deterministic sampling grid
        step_x = max(1, w // 10)
        step_y = max(1, h // 10)
        samples_count = 0
        
        for x in range(0, w, step_x):
            for y in range(0, h, step_y):
                pixel_color = QColor(image.pixelColor(x, y))
                if pixel_color.lightness() > 200:
                    light_pixels += 1
                samples_count += 1
                if samples_count >= total_samples:
                    break
            if samples_count >= total_samples:
                break

        if samples_count > 0 and (light_pixels / samples_count) >= 0.70:
            # Invert line-art
            image.invertPixels(QImage.InvertMode.InvertRgb)
            return QPixmap.fromImage(image)

        return pixmap

    def _load_pixmap(self, block: Block) -> QPixmap | None:
        # Strategy 1 — raw bytes (comics, extracted PDF images, EPUB cover)
        if block.image_data:
            pixmap = QPixmap()
            if pixmap.loadFromData(block.image_data):
                return pixmap

        # Strategy 2 — file path (EPUB internal image references)
        if block.image_path:
            # Only try loading directly if it points to a valid file on disk
            from pathlib import Path
            if Path(block.image_path).is_file():
                pixmap = QPixmap(block.image_path)
                if not pixmap.isNull():
                    return pixmap

        # Strategy 3 — lazy loading from block.attrs (comics archive, temp folder, or EPUB file)
        if block.attrs:
            epub_file_path = block.attrs.get("epub_file_path")
            epub_image_href = block.attrs.get("epub_image_href")
            if epub_file_path and epub_image_href:
                try:
                    data = self._load_epub_image(epub_file_path, epub_image_href)
                    if data:
                        pixmap = QPixmap()
                        if pixmap.loadFromData(data):
                            return pixmap
                except Exception as e:
                    print(f"[ImageRenderer] Lazy load failed for EPUB image {epub_image_href}: {e}")

            file_path = block.attrs.get("file_path")
            if file_path:
                pixmap = QPixmap(file_path)
                if not pixmap.isNull():
                    return pixmap

            archive_path = block.attrs.get("archive_path")
            archive_member = block.attrs.get("archive_member")
            if archive_path and archive_member:
                try:
                    data = self._load_archive_member(archive_path, archive_member)
                    if data:
                        pixmap = QPixmap()
                        if pixmap.loadFromData(data):
                            return pixmap
                except Exception as e:
                    print(f"[ImageRenderer] Lazy load failed for {archive_member}: {e}")

        return None

    def _load_epub_image(self, epub_file_path: str, href: str) -> bytes | None:
        import zipfile
        from urllib.parse import unquote
        
        href = unquote(href).replace("\\", "/")
        clean_href = href.lstrip("./").split("../")[-1]
        
        with zipfile.ZipFile(epub_file_path, "r") as zf:
            for name in zf.namelist():
                if name.replace("\\", "/").endswith(clean_href):
                    return zf.read(name)
        return None

    def _load_archive_member(self, archive_path: str, member: str) -> bytes | None:
        from pathlib import Path
        path = Path(archive_path)
        fmt = path.suffix.lower().lstrip(".")
        
        data = None
        if fmt == "cbz":
            import zipfile
            with zipfile.ZipFile(str(path), "r") as zf:
                data = zf.read(member)
        elif fmt == "cbr":
            import rarfile
            with rarfile.RarFile(str(path), "r") as rf:
                data = rf.read(member)

        if data:
            from PIL import Image as PilImage
            import io
            try:
                img = PilImage.open(io.BytesIO(data))
                if img.format in ("JPEG", "PNG", "WEBP"):
                    return data
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
                img.save(buf, format="PNG")
                return buf.getvalue()
            except Exception:
                return data
        return None

    def clear_cache(self):
        self._pixmap_cache.clear()