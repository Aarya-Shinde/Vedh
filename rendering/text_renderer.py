from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import (
    QPainter, QFont, QFontMetricsF, QColor,
    QPen, QBrush, QPixmap, QImage
)
from PyQt6.QtCore import Qt, QRectF, QPointF

from core.book_model import Block, BlockType


class TextRenderer:
    """
    Draws text-based blocks onto a QPainter surface.

    Handles:
        PARAGRAPH, HEADING, QUOTE, HORIZONTAL_RULE

    Skips gracefully:
        TABLE, CODE_BLOCK, FOOTNOTE_REF, CAPTION (stubs)

    Does not handle IMAGE — that goes to ImageRenderer.
    """

    def __init__(self):
        self._theme: dict      = {}
        self._page_width: float = 700.0

    # ── Configuration ──────────────────────────────────────────────────────

    def configure(self, theme: dict, page_width: float):
        self._theme      = theme
        self._page_width = page_width

    # ── Public API ─────────────────────────────────────────────────────────

    def draw_block(
        self,
        painter: QPainter,
        block: Block,
        x: float,
        y: float,
    ) -> float:
        """
        Draw a single block at (x, y).
        Returns the height consumed so the caller can advance y.
        """
        btype = block.type

        if btype == BlockType.PARAGRAPH:
            return self._draw_paragraph(painter, block, x, y)

        elif btype == BlockType.HEADING:
            return self._draw_heading(painter, block, x, y)

        elif btype == BlockType.QUOTE:
            return self._draw_quote(painter, block, x, y)

        elif btype == BlockType.HORIZONTAL_RULE:
            return self._draw_rule(painter, x, y)

        elif btype in (
            BlockType.TABLE,
            BlockType.CODE_BLOCK,
            BlockType.FOOTNOTE_REF,
            BlockType.CAPTION,
        ):
            return self._draw_stub(painter, block, x, y)

        # PAGE_BREAK, IMAGE — not handled here
        return 0.0

    # ── Paragraph ──────────────────────────────────────────────────────────

    def _draw_paragraph(
        self, painter: QPainter, block: Block, x: float, y: float
    ) -> float:
        text = block.text or ""
        if not text.strip():
            return self._paragraph_spacing()

        font = self._body_font()
        if block.attrs.get("italic"):
            font.setItalic(True)
        if block.attrs.get("bold"):
            font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(self._theme.get("text_color", self._theme.get("text", "#1E1E1E"))))

        align = block.attrs.get("align")

        # ── Drop-cap logic for first paragraph of a chapter ──
        is_first = block.attrs.get("is_first_paragraph") and align != "center"
        first_char = ""
        rest_text = text.lstrip()
        has_space_after = False

        if is_first and rest_text:
            if rest_text[0] in ('"', "'", '“', '‘', '”', '’') and len(rest_text) > 1 and rest_text[1].isalpha():
                first_char = rest_text[:2]
                rest_text = rest_text[2:]
                has_space_after = len(text.lstrip()) > 2 and text.lstrip()[2].isspace()
            elif rest_text[0].isalpha():
                first_char = rest_text[0]
                rest_text = rest_text[1:]
                has_space_after = len(text.lstrip()) > 1 and text.lstrip()[1].isspace()
            else:
                is_first = False

        if is_first:
            # Setup drop-cap font
            drop_font = QFont(font)
            base_sz = font.pointSizeF()
            if base_sz <= 0:
                pixel_sz = font.pixelSize()
                base_sz = pixel_sz * 0.75 if pixel_sz > 0 else 12.0
            drop_font.setPointSizeF(base_sz * 2.8)
            drop_font.setBold(True)
            drop_fm = QFontMetricsF(drop_font)

            drop_char_w = drop_fm.horizontalAdvance(first_char)
            padding = 8.0
            drop_box_w = drop_char_w + padding
            
            fm = QFontMetricsF(font)
            if has_space_after:
                drop_box_w += fm.horizontalAdvance(" ")

            line_height = fm.height() * self._line_spacing()
            drop_h = drop_fm.height()
            
            # Count lines to wrap
            wrap_lines_count = int(round(drop_h / line_height))
            if wrap_lines_count < 2:
                wrap_lines_count = 2

            # Word wrap simulation
            words = rest_text.split()
            lines = []
            current_line = []
            current_w = 0.0

            for word in words:
                word_w = fm.horizontalAdvance(word)
                space_w = fm.horizontalAdvance(" ")
                limit_w = (self._page_width - drop_box_w) if len(lines) < wrap_lines_count else self._page_width

                if not current_line:
                    current_line.append(word)
                    current_w = word_w
                elif current_w + space_w + word_w <= limit_w:
                    current_line.append(word)
                    current_w += space_w + word_w
                else:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                    current_w = word_w

            if current_line:
                lines.append(" ".join(current_line))

            # Draw the drop cap character using theme's primary color
            painter.setFont(drop_font)
            painter.setPen(QColor(self._theme.get("primary", "#D4AF37")))
            painter.drawText(QPointF(x, y + drop_fm.ascent() * 0.85), first_char)

            # Reset font and pen for body
            painter.setFont(font)
            painter.setPen(QColor(self._theme.get("text_color", self._theme.get("text", "#1E1E1E"))))

            # Draw lines
            current_y = y + fm.ascent()
            for idx, line in enumerate(lines):
                line_x = x + drop_box_w if idx < wrap_lines_count else x
                painter.drawText(QPointF(line_x, current_y), line)
                current_y += line_height

            return len(lines) * line_height + self._paragraph_spacing()

        return self._draw_wrapped_text(painter, text, font, x, y, self._page_width, align=align)

    # ── Heading ────────────────────────────────────────────────────────────

    def _draw_heading(
        self, painter: QPainter, block: Block, x: float, y: float
    ) -> float:
        text  = block.text or ""
        level = block.level or 1
        if not text.strip():
            return 0.0

        font = self._heading_font(level)
        if block.attrs.get("italic"):
            font.setItalic(True)
        if block.attrs.get("bold"):
            font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(self._theme.get("heading_color", self._theme.get("text", "#111111"))))

        align = block.attrs.get("align")
        # Extra space above heading
        top_gap = self._heading_top_gap(level)
        height  = self._draw_wrapped_text(
            painter, text, font, x, y + top_gap, self._page_width, align=align
        )

        return height + top_gap + self._heading_bottom_gap(level)

    # ── Quote ──────────────────────────────────────────────────────────────

    def _draw_quote(
        self, painter: QPainter, block: Block, x: float, y: float
    ) -> float:
        text = block.text or ""
        if not text.strip():
            return self._paragraph_spacing()

        indent      = float(self._theme.get("quote_indent", 32))
        padding     = 14.0
        inner_width = self._page_width - indent * 2 - padding * 2

        font = self._quote_font()
        if block.attrs.get("italic"):
            font.setItalic(True)
        if block.attrs.get("bold"):
            font.setBold(True)
        fm   = QFontMetricsF(font)
        line_height  = fm.height() * self._line_spacing()
        line_count   = self._count_lines(text, fm, inner_width)
        content_h    = line_count * line_height
        box_h        = content_h + padding * 2

        # Background rect
        bg_rect = QRectF(x + indent, y, self._page_width - indent * 2, box_h)
        painter.setBrush(QBrush(QColor(self._theme.get("quote_background", "#F0EDE6"))))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bg_rect, 6, 6)

        # Left accent bar
        bar_rect = QRectF(x + indent, y, 3, box_h)
        painter.setBrush(QBrush(QColor(self._theme.get("quote_border", "#C4B9A8"))))
        painter.drawRoundedRect(bar_rect, 2, 2)

        # Text
        painter.setFont(font)
        painter.setPen(QColor(self._theme.get("quote_text_color", self._theme.get("text", "#4A4A4A"))))
        align = block.attrs.get("align")
        self._draw_wrapped_text(
            painter, text, font,
            x + indent + padding + 6,
            y + padding,
            inner_width,
            align=align,
        )

        return box_h + self._paragraph_spacing()

    # ── Horizontal rule ────────────────────────────────────────────────────

    def _draw_rule(
        self, painter: QPainter, x: float, y: float
    ) -> float:
        pen = QPen(QColor(self._theme.get("quote_border", "#C4B9A8")))
        pen.setWidthF(1.0)
        painter.setPen(pen)

        center_y = y + 12
        painter.drawLine(
            QPointF(x + 60, center_y),
            QPointF(x + self._page_width - 60, center_y),
        )

        return 24.0

    # ── Stub blocks ────────────────────────────────────────────────────────

    def _draw_stub(
        self, painter: QPainter, block: Block, x: float, y: float
    ) -> float:
        """
        Placeholder rendering for unimplemented block types.
        Shows a subtle labeled box so layout isn't broken.
        """
        label = block.type.name.replace("_", " ").title()

        pen = QPen(QColor(self._theme.get("text_muted", "#AAAAAA")))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        rect = QRectF(x, y + 4, self._page_width, 32)
        painter.drawRect(rect)

        font = self._body_font()
        font.setPointSizeF(10)
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QColor(self._theme.get("text_muted", "#AAAAAA")))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"[ {label} ]")

        return 40.0

    # ── Word-wrap drawing ──────────────────────────────────────────────────

    def _draw_wrapped_text(
        self,
        painter: QPainter,
        text: str,
        font: QFont,
        x: float,
        y: float,
        width: float,
        align: str | None = None,
    ) -> float:
        """
        Draw text with manual word wrapping.
        Returns total height consumed.
        """
        fm          = QFontMetricsF(font)
        line_height = fm.height() * self._line_spacing()
        space_w     = fm.horizontalAdvance(" ")
        para_space  = self._paragraph_spacing()

        words        = text.split()
        lines        = []
        current_line = []
        current_w    = 0.0

        for word in words:
            word_w = fm.horizontalAdvance(word)
            if not current_line:
                current_line.append(word)
                current_w = word_w
            elif current_w + space_w + word_w <= width:
                current_line.append(word)
                current_w += space_w + word_w
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_w    = word_w

        if current_line:
            lines.append(" ".join(current_line))

        # Draw each line
        ascent     = fm.ascent()
        current_y  = y + ascent

        for line in lines:
            if align == "center":
                line_w = fm.horizontalAdvance(line)
                draw_x = x + (width - line_w) / 2.0
            elif align == "right":
                line_w = fm.horizontalAdvance(line)
                draw_x = x + (width - line_w)
            else:
                draw_x = x
            painter.drawText(QPointF(draw_x, current_y), line)
            current_y += line_height

        total_height = len(lines) * line_height + para_space
        return total_height

    # ── Helpers ────────────────────────────────────────────────────────────

    def _count_lines(
        self, text: str, fm: QFontMetricsF, width: float
    ) -> int:
        words        = text.split()
        lines        = 0
        current_w    = 0.0
        space_w      = fm.horizontalAdvance(" ")

        for word in words:
            word_w = fm.horizontalAdvance(word)
            if current_w == 0.0:
                current_w = word_w
            elif current_w + space_w + word_w <= width:
                current_w += space_w + word_w
            else:
                lines    += 1
                current_w = word_w

        if current_w > 0:
            lines += 1

        return max(lines, 1)

    # ── Font builders ──────────────────────────────────────────────────────

    def _body_font(self) -> QFont:
        font = QFont()
        font.setFamily(self._theme.get("font_family", "Georgia"))
        font.setPointSizeF(max(1.0, float(self._theme.get("font_size", 18))))
        return font

    def _heading_font(self, level: int) -> QFont:
        font  = self._body_font()
        base  = max(1.0, float(self._theme.get("font_size", 18)))
        scale = {1: 2.0, 2: 1.6, 3: 1.35, 4: 1.15, 5: 1.0, 6: 1.0}
        font.setPointSizeF(base * scale.get(level, 1.0))
        font.setWeight(QFont.Weight.Bold)
        return font

    def _quote_font(self) -> QFont:
        font = self._body_font()
        font.setItalic(True)
        return font

    # ── Spacing helpers ────────────────────────────────────────────────────

    def _line_spacing(self) -> float:
        return float(self._theme.get("line_spacing", 1.6))

    def _paragraph_spacing(self) -> float:
        return float(self._theme.get("paragraph_spacing", 14))

    def _heading_top_gap(self, level: int) -> float:
        gaps = {1: 32.0, 2: 26.0, 3: 20.0, 4: 16.0, 5: 14.0, 6: 12.0}
        return gaps.get(level, 16.0)

    def _heading_bottom_gap(self, level: int) -> float:
        gaps = {1: 16.0, 2: 14.0, 3: 10.0, 4: 8.0, 5: 6.0, 6: 6.0}
        return gaps.get(level, 8.0)