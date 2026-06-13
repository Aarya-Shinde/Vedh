from dataclasses import dataclass

from PyQt6.QtGui import QFontMetricsF, QFont, QFontDatabase
from PyQt6.QtCore import Qt

from core.book_model import Block, BlockType


@dataclass
class MeasuredBlock:
    block: Block
    height: float          # total height in pixels including spacing
    line_count: int        # number of lines after wrapping
    font: QFont            # font used for this block


class BlockMeasurer:
    """
    Measures the pixel height of every block given the current
    reader theme settings and available page width.

    This is the single source of truth for layout calculations.
    Everything that needs to know how tall a block is goes through here.
    """

    def __init__(self):
        self._theme: dict       = {}
        self._page_width: float = 700.0
        self._dpr: float        = 1.0    # device pixel ratio

    def configure(self, theme: dict, page_width: float, page_height: float = 900.0, dpr: float = 1.0):
        self._theme       = theme
        self._page_width  = page_width
        self._page_height = page_height
        self._dpr         = dpr

    # ── Public API ─────────────────────────────────────────────────────────

    def measure(self, block: Block) -> MeasuredBlock:
        btype = block.type

        if btype == BlockType.PARAGRAPH:
            font = self._body_font()
            if block.attrs.get("italic"):
                font.setItalic(True)
            if block.attrs.get("bold"):
                font.setBold(True)
            return self._measure_text(block, font)

        elif btype == BlockType.HEADING:
            level = block.level or 1
            font = self._heading_font(level)
            if block.attrs.get("italic"):
                font.setItalic(True)
            if block.attrs.get("bold"):
                font.setBold(True)
            measured = self._measure_text(block, font)
            measured.height += self._heading_top_gap(level) + self._heading_bottom_gap(level)
            return measured

        elif btype == BlockType.QUOTE:
            indent  = float(self._theme.get("quote_indent", 32))
            padding = 14.0
            font = self._quote_font()
            if block.attrs.get("italic"):
                font.setItalic(True)
            if block.attrs.get("bold"):
                font.setBold(True)
            measured = self._measure_text(
                block,
                font,
                width_override=self._page_width - indent * 2 - padding * 2,
            )
            measured.height += padding * 2
            return measured

        elif btype == BlockType.IMAGE:
            return self._measure_image(block)

        elif btype == BlockType.PAGE_BREAK:
            return MeasuredBlock(
                block=block,
                height=0.0,
                line_count=0,
                font=self._body_font(),
            )

        elif btype == BlockType.HORIZONTAL_RULE:
            return MeasuredBlock(
                block=block,
                height=24.0,
                line_count=1,
                font=self._body_font(),
            )

        else:
            # Stub blocks — TABLE, CODE_BLOCK, FOOTNOTE_REF, CAPTION
            # Reserve a nominal height so they don't break layout
            return MeasuredBlock(
                block=block,
                height=40.0,
                line_count=1,
                font=self._body_font(),
            )

    def measure_all(self, blocks: list[Block]) -> list[MeasuredBlock]:
        return [self.measure(b) for b in blocks]

    # ── Text measurement ───────────────────────────────────────────────────

    def _measure_text(
        self,
        block: Block,
        font: QFont,
        width_override: float | None = None,
    ) -> MeasuredBlock:
        text = block.text or ""
        if not text.strip():
            # Empty block — just paragraph spacing
            return MeasuredBlock(
                block=block,
                height=self._paragraph_spacing(),
                line_count=0,
                font=font,
            )

        available_width = width_override or self._page_width
        fm = QFontMetricsF(font)

        line_height   = fm.height() * self._line_spacing()
        para_spacing  = self._paragraph_spacing()

        # Word-wrap simulation
        line_count = self._count_wrapped_lines(text, fm, available_width)

        total_height = (line_count * line_height) + para_spacing

        return MeasuredBlock(
            block=block,
            height=total_height,
            line_count=line_count,
            font=font,
        )

    def _count_wrapped_lines(
        self,
        text: str,
        fm: QFontMetricsF,
        available_width: float,
    ) -> int:
        """
        Simulate word wrapping to count how many lines a text block
        will produce at the current page width.
        """
        if not text:
            return 0

        words  = text.split()
        lines  = 0
        current_line_width = 0.0
        space_width = fm.horizontalAdvance(" ")

        for word in words:
            word_width = fm.horizontalAdvance(word)

            if current_line_width == 0.0:
                # First word on a line
                current_line_width = word_width
            elif current_line_width + space_width + word_width <= available_width:
                current_line_width += space_width + word_width
            else:
                # Word doesn't fit — new line
                lines += 1
                current_line_width = word_width

        # Count the last line
        if current_line_width > 0:
            lines += 1

        return max(lines, 1)

    # ── Image measurement ──────────────────────────────────────────────────

    def _measure_image(self, block: Block) -> MeasuredBlock:
        """
        Measure image height by loading it and scaling to page width.
        Falls back to a sensible default if image can't be loaded.
        """
        from PyQt6.QtGui import QPixmap, QImage
        import io

        FALLBACK_IMAGE_HEIGHT = 120.0
        pixmap = None

        # Check epub lazy loading
        epub_file_path = block.attrs.get("epub_file_path")
        epub_image_href = block.attrs.get("epub_image_href")
        if epub_file_path and epub_image_href:
            try:
                data = self._load_epub_image(epub_file_path, epub_image_href)
                if data:
                    image = QImage()
                    if image.loadFromData(data):
                        pixmap = image
            except Exception as e:
                print(f"[BlockMeasurer] Lazy image load failed: {e}")

        if pixmap is None or (hasattr(pixmap, "isNull") and pixmap.isNull()):
            if block.image_path:
                from pathlib import Path
                if Path(block.image_path).is_file():
                    image = QImage(block.image_path)
                    if not image.isNull():
                        pixmap = image

        if pixmap is None or (hasattr(pixmap, "isNull") and pixmap.isNull()):
            return MeasuredBlock(
                block=block,
                height=FALLBACK_IMAGE_HEIGHT + self._paragraph_spacing(),
                line_count=1,
                font=self._body_font(),
            )

        orig_w = pixmap.width()
        orig_h = pixmap.height()

        if orig_w == 0:
            return MeasuredBlock(
                block=block,
                height=FALLBACK_IMAGE_HEIGHT + self._paragraph_spacing(),
                line_count=1,
                font=self._body_font(),
            )

        # Scale height proportionally to page width
        scale  = self._page_width / orig_w
        target_w = self._page_width
        target_h = orig_h * scale

        # Scale down if height exceeds usable page height
        margin_v = float(self._theme.get("margin_v", 40.0))
        usable_height = (self._page_height - margin_v * 2) if hasattr(self, "_page_height") else (self._page_width * 1.5)
        if target_h > usable_height:
            target_h = usable_height

        return MeasuredBlock(
            block=block,
            height=target_h + self._paragraph_spacing(),
            line_count=1,
            font=self._body_font(),
        )

    # ── Font builders ──────────────────────────────────────────────────────

    def _body_font(self) -> QFont:
        font = QFont()
        font.setFamily(self._theme.get("font_family", "Georgia"))
        font.setPointSizeF(max(1.0, float(self._theme.get("font_size", 18))))
        return font

    def _heading_font(self, level: int) -> QFont:
        font = self._body_font()
        base = max(1.0, float(self._theme.get("font_size", 18)))

        scale = {1: 2.0, 2: 1.6, 3: 1.35, 4: 1.15, 5: 1.0, 6: 1.0}
        font.setPointSizeF(base * scale.get(level, 1.0))
        font.setWeight(QFont.Weight.Bold)
        return font

    def _quote_font(self) -> QFont:
        font = self._body_font()
        font.setItalic(True)
        return font

    # ── Theme helpers ──────────────────────────────────────────────────────

    def _line_spacing(self) -> float:
        return self._theme.get("line_spacing", 1.6)

    def _paragraph_spacing(self) -> float:
        return float(self._theme.get("paragraph_spacing", 14))

    def _heading_top_gap(self, level: int) -> float:
        gaps = {1: 32.0, 2: 26.0, 3: 20.0, 4: 16.0, 5: 14.0, 6: 12.0}
        return gaps.get(level, 16.0)

    def _heading_bottom_gap(self, level: int) -> float:
        gaps = {1: 16.0, 2: 14.0, 3: 10.0, 4: 8.0, 5: 6.0, 6: 6.0}
        return gaps.get(level, 8.0)

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