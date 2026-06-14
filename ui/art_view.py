import os
from datetime import datetime
from pathlib import Path
from math import cos, sin, pi

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QScrollArea, QFrame, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QSize, QPointF, QVariantAnimation, QEasingCurve, QUrl
from PyQt6.QtGui import (
    QPainter, QColor, QPixmap, QFont, QLinearGradient, QRadialGradient,
    QPainterPath, QPen, QBrush, QKeySequence, QShortcut, QImage
)
from PyQt6.QtMultimedia import QSoundEffect

from core.theme_manager import ThemeManager
from storage.repositories import ArtRepository


class ArtBookWidget(QWidget):
    """
    A custom-painted 3D book display.
    Renders curved pages using organic Bezier S-curve paths, curved page thickness,
    and a highly realistic 3D page turning animation.
    Supports hover-based 3D parallax effects, dynamic specular highlights,
    procedural watercolor paper texture overlays, and low-latency flip sound effects.
    """

    page_clicked = pyqtSignal(int)  # Emits -1 for left page click, 1 for right page click

    def __init__(self, theme: ThemeManager):
        super().__init__()
        self.theme = theme
        self.current_art = None
        self.prev_art = None
        self.current_pixmap = None
        self.prev_pixmap = None
        
        # Layout mode (True = Double spread, False = Single page detail)
        self.is_double_page = True
        
        # Generate procedural watercolor paper grain texture
        self.paper_pixmap = self._create_paper_texture()
        
        # Audio Player (low-latency QSoundEffect)
        self.sound_effect = QSoundEffect(self)
        sound_path = os.path.abspath(os.path.join("assets", "audio", "page_flip.wav"))
        if os.path.exists(sound_path):
            self.sound_effect.setSource(QUrl.fromLocalFile(sound_path))
            self.sound_effect.setVolume(0.35)
        
        # Interactive hover parallax state
        self.mouse_dx = 0.0
        self.mouse_dy = 0.0
        self.start_dx = 0.0
        self.start_dy = 0.0
        self.reset_anim = None
        self.setMouseTracking(True)
        
        # Animation state
        self.anim_progress = 1.0
        self.anim_direction = 1  # 1 = next, -1 = prev
        self.anim = None
        
        self.setMinimumSize(740, 460)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _create_paper_texture(self):
        """Generates a tileable watercolor paper grain texture with fine organic fibers procedurally."""
        size = 256
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Deterministic seed for consistent texture mapping
        import random
        random.seed(42)
        
        # Draw soft noise dots
        for _ in range(9000):
            x = random.randint(0, size - 1)
            y = random.randint(0, size - 1)
            opacity = random.randint(3, 11)
            color = QColor(0, 0, 0, opacity) if random.random() > 0.5 else QColor(255, 255, 255, opacity)
            painter.setPen(QPen(color, 1.0))
            painter.drawPoint(x, y)
            
        # Draw fine organic paper fibers
        for _ in range(120):
            x1 = random.randint(0, size - 1)
            y1 = random.randint(0, size - 1)
            length = random.randint(4, 14)
            angle = random.uniform(0, 2 * pi)
            x2 = int(x1 + length * cos(angle))
            y2 = int(y1 + length * sin(angle))
            opacity = random.randint(2, 6)
            painter.setPen(QPen(QColor(110, 100, 90, opacity), 0.8))
            painter.drawLine(x1, y1, x2, y2)
            
        painter.end()
        return QPixmap.fromImage(img)

    def set_artwork(self, art_dict: dict | None, direction: int = 0):
        if self.current_art == art_dict:
            return

        self.prev_art = self.current_art
        self.prev_pixmap = self.current_pixmap
        
        self.current_art = art_dict
        if art_dict:
            img_path = art_dict.get("image_path")
            if img_path and os.path.exists(img_path):
                self.current_pixmap = QPixmap(img_path)
            else:
                self.current_pixmap = None
        else:
            self.current_pixmap = None

        if direction != 0 and self.prev_art is not None and self.current_art is not None:
            self.anim_direction = direction
            if self.anim and self.anim.state() == QVariantAnimation.State.Running:
                self.anim.stop()
                
            self.anim = QVariantAnimation(self)
            self.anim.setStartValue(0.0)
            self.anim.setEndValue(1.0)
            self.anim.setDuration(950)
            self.anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self.anim.valueChanged.connect(self._on_anim_value)
            self.anim.finished.connect(self._on_anim_finished)
            self.anim_progress = 0.0
            
            # Play sound effect synchronized with page turn start
            if hasattr(self, "sound_effect") and self.sound_effect.isLoaded():
                self.sound_effect.play()
                
            self.anim.start()
        else:
            self.prev_art = None
            self.prev_pixmap = None
            self.anim_progress = 1.0
            self.update()

    def _on_anim_value(self, val):
        self.anim_progress = val
        self.update()

    def _on_anim_finished(self):
        self.anim_progress = 1.0
        self.prev_art = None
        self.prev_pixmap = None
        self.update()

    def mouseMoveEvent(self, event):
        W = float(self.width())
        H = float(self.height())
        cx = W / 2.0
        cy = H / 2.0
        
        # Calculate cursor offset relative to center (-1.0 to 1.0)
        self.mouse_dx = (event.position().x() - cx) / cx if cx > 0 else 0.0
        self.mouse_dy = (event.position().y() - cy) / cy if cy > 0 else 0.0
        
        self.mouse_dx = max(-1.0, min(1.0, self.mouse_dx))
        self.mouse_dy = max(-1.0, min(1.0, self.mouse_dy))
        self.update()

    def leaveEvent(self, event):
        self.start_dx = self.mouse_dx
        self.start_dy = self.mouse_dy
        
        if self.reset_anim and self.reset_anim.state() == QVariantAnimation.State.Running:
            self.reset_anim.stop()
            
        self.reset_anim = QVariantAnimation(self)
        self.reset_anim.setStartValue(1.0)
        self.reset_anim.setEndValue(0.0)
        self.reset_anim.setDuration(250)
        self.reset_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.reset_anim.valueChanged.connect(self._on_reset_val)
        self.reset_anim.start()

    def _on_reset_val(self, val):
        self.mouse_dx = self.start_dx * val
        self.mouse_dy = self.start_dy * val
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            W = float(self.width())
            cx = W / 2.0
            
            # Click interactive page flip detection
            if event.position().x() < cx:
                self.page_clicked.emit(-1)
            else:
                self.page_clicked.emit(1)

    def format_date(self, date_str):
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%B %d, %Y")
        except Exception:
            return date_str or "Unknown Date"

    def draw_artwork_details(self, painter, art_dict, page_rect):
        """Draws detailed metadata, title, format, and description on the left page."""
        if not art_dict:
            return
            
        t = self.theme
        is_dark = "Dark" in t.app("name", "dark")
        
        title_color = QColor(t.app("text_primary"))
        muted_color = QColor(t.app("text_muted"))
        accent_color = QColor(t.app("accent"))
        
        margin_left = page_rect.left() + 35.0
        top = page_rect.top() + 45.0
        width = page_rect.width() - 70.0
        
        # 1. Title
        title_font = QFont("Georgia", 15, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(title_color)
        title_text = art_dict.get("title", "Untitled Creation")
        painter.drawText(QRectF(margin_left, top, width, 55.0), Qt.TextFlag.TextWordWrap, title_text)
        
        top += 60.0
        
        # 2. Accent Separator Line
        painter.setPen(QPen(accent_color, 1.5))
        painter.drawLine(QPointF(margin_left, top), QPointF(margin_left + 70.0, top))
        
        top += 25.0
        
        # 3. Metadata list
        meta_font = QFont("Inter", 9)
        painter.setFont(meta_font)
        
        file_size_str = "Unknown Size"
        file_format = "PNG Image"
        img_path = art_dict.get("image_path", "")
        if img_path and os.path.exists(img_path):
            sz = os.path.getsize(img_path)
            file_size_str = f"{sz / 1024:.1f} KB"
            ext = os.path.splitext(img_path)[1].upper().replace(".", "")
            file_format = f"{ext} Image"
            
        metadata = [
            ("COLLECTION", "Creations Gallery"),
            ("FORMAT", file_format),
            ("FILE SIZE", file_size_str),
            ("EXHIBITED", self.format_date(art_dict.get("created_at", "")))
        ]
        
        for label, val in metadata:
            painter.setPen(QPen(accent_color, 1.0))
            painter.drawText(QRectF(margin_left, top, width, 18.0), Qt.AlignmentFlag.AlignLeft, label)
            
            painter.setPen(QPen(title_color, 1.0))
            painter.drawText(QRectF(margin_left + 85.0, top, width - 85.0, 18.0), Qt.AlignmentFlag.AlignLeft, val)
            
            top += 24.0
            
        top += 15.0
        
        # 4. Description
        desc_font = QFont("Georgia", 10)
        desc_font.setItalic(True)
        painter.setFont(desc_font)
        painter.setPen(muted_color)
        
        desc_text = (
            "A fine creation added to the personal archives. "
            "Exhibited beautifully on the dynamic 3D virtual canvas "
            "as part of the curated collections."
        )
        painter.drawText(QRectF(margin_left, top, width, 100.0), Qt.TextFlag.TextWordWrap, desc_text)

    def draw_artwork_single(self, painter, art_dict, page_rect, clip_path, draw_width=None, lift_y=0.0):
        """Draws the full artwork centered and scaled within a single page, complete with pencil frames."""
        if not art_dict:
            return
            
        normal_page_w = page_rect.width()
        if normal_page_w <= 0.0:
            return
            
        px = self.current_pixmap if art_dict == self.current_art else self.prev_pixmap
        if not px or px.isNull():
            return
            
        painter.save()
        painter.setClipPath(clip_path)
        
        normal_page_h = page_rect.height()
        
        # Framing margins
        padding = 24.0
        target_w = normal_page_w - padding * 2.0
        target_h = normal_page_h - padding * 2.0
        
        scaled_pix = px.scaled(
            QSize(int(target_w), int(target_h)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        img_w = float(scaled_pix.width())
        img_h = float(scaled_pix.height())
        
        if draw_width is not None:
            scale_x = draw_width / normal_page_w
            painter.translate(page_rect.left(), page_rect.top() - lift_y)
            painter.scale(scale_x, 1.0)
            
            img_x = (normal_page_w - img_w) / 2.0
            img_y = (normal_page_h - img_h) / 2.0
            painter.drawPixmap(QPointF(img_x, img_y), scaled_pix)
            
            # Subtle pencil border outlines
            painter.setPen(QPen(QColor(0, 0, 0, 20), 1.0))
            painter.drawRect(QRectF(img_x - 3, img_y - 3, img_w + 6, img_h + 6))
            painter.setPen(QPen(QColor(0, 0, 0, 35), 1.2))
            painter.drawRect(QRectF(img_x, img_y, img_w, img_h))
        else:
            img_x = page_rect.left() + (normal_page_w - img_w) / 2.0
            img_y = page_rect.top() + (normal_page_h - img_h) / 2.0
            painter.drawPixmap(QPointF(img_x, img_y), scaled_pix)
            
            # Subtle pencil border outlines
            painter.setPen(QPen(QColor(0, 0, 0, 20), 1.0))
            painter.drawRect(QRectF(img_x - 3, img_y - 3, img_w + 6, img_h + 6))
            painter.setPen(QPen(QColor(0, 0, 0, 35), 1.2))
            painter.drawRect(QRectF(img_x, img_y, img_w, img_h))
            
        painter.restore()

    def draw_artwork_half(self, painter, art_dict, is_left, page_rect, clip_path, draw_width=None, lift_y=0.0):
        """Draws half of the double-page artwork spread, complete with pencil frames."""
        if not art_dict:
            return
            
        normal_page_w = page_rect.width()
        if normal_page_w <= 0.0:
            return
            
        px = self.current_pixmap if art_dict == self.current_art else self.prev_pixmap
        if not px or px.isNull():
            return
            
        painter.save()
        painter.setClipPath(clip_path)
        
        double_w = normal_page_w * 2.0
        double_h = page_rect.height()
        
        scaled_pix = px.scaled(
            QSize(int(double_w), int(double_h)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        img_w = float(scaled_pix.width())
        img_h = float(scaled_pix.height())
        
        if draw_width is not None:
            scale_x = draw_width / normal_page_w
            painter.translate(page_rect.left(), page_rect.top() - lift_y)
            painter.scale(scale_x, 1.0)
            
            cx_local = 0.0 if not is_left else normal_page_w
            img_x = cx_local - (img_w / 2.0)
            img_y = (double_h - img_h) / 2.0
            painter.drawPixmap(QPointF(img_x, img_y), scaled_pix)
            
            # Pencil frame outline
            painter.setPen(QPen(QColor(0, 0, 0, 35), 1.2))
            painter.drawRect(QRectF(img_x, img_y, img_w, img_h))
        else:
            cx = page_rect.right() if is_left else page_rect.left()
            img_x = cx - (img_w / 2.0)
            img_y = page_rect.top() + (double_h - img_h) / 2.0
            painter.drawPixmap(QPointF(img_x, img_y), scaled_pix)
            
            # Pencil frame outline
            painter.setPen(QPen(QColor(0, 0, 0, 35), 1.2))
            painter.drawRect(QRectF(img_x, img_y, img_w, img_h))
            
        painter.restore()

    def draw_page_content(self, painter, art_dict, is_left, rect, path, draw_width=None, lift_y=0.0):
        """Renders either the Double Spread halves or Single Detail page based on configuration."""
        if rect.width() <= 0.0 or rect.height() <= 0.0:
            return
            
        if self.is_double_page:
            self.draw_artwork_half(painter, art_dict, is_left, rect, path, draw_width, lift_y)
        else:
            if is_left:
                painter.save()
                painter.setClipPath(path)
                if draw_width is not None:
                    scale_x = draw_width / rect.width()
                    painter.translate(rect.left(), rect.top() - lift_y)
                    painter.scale(scale_x, 1.0)
                    offset_rect = QRectF(0.0, 0.0, rect.width(), rect.height())
                    self.draw_artwork_details(painter, art_dict, offset_rect)
                else:
                    self.draw_artwork_details(painter, art_dict, rect)
                painter.restore()
            else:
                self.draw_artwork_single(painter, art_dict, rect, path, draw_width, lift_y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W = float(self.width())
        H = float(self.height())

        # Book boundaries
        book_w = min(W - 40.0, 840.0)
        book_h = min(H - 40.0, 500.0)
        
        # Base Coordinates
        bx = (W - book_w) / 2.0
        by = (H - book_h) / 2.0
        cx = W / 2.0

        is_dark = "Dark" in self.theme.app("name", "dark")
        page_color = QColor("#FDFBF7") if not is_dark else QColor("#D5D2C7")
        cover_color = QColor("#3C2E24") if not is_dark else QColor("#1C1511")
        
        page_w = book_w / 2.0
        page_h = book_h

        # Compute dynamic 3D Parallax offset displacements
        shadow_x = bx - 12.0 - self.mouse_dx * 6.0
        shadow_y = by + 12.0 - self.mouse_dy * 6.0
        
        cover_x = bx + self.mouse_dx * 4.0
        cover_y = by + self.mouse_dy * 4.0
        
        pages_x = bx + self.mouse_dx * 8.0
        pages_y = by + self.mouse_dy * 8.0
        pages_cx = cx + self.mouse_dx * 8.0

        # 1. Soft Ambient Drop Shadow under the cover
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_x, shadow_y, book_w + 24.0, book_h + 12.0, 18.0, 18.0)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 50 if not is_dark else 85))

        # 2. Leather Hardcover with 3D Page Crease Bevel
        cover_path = QPainterPath()
        # Left side cover curve
        cover_path.moveTo(pages_cx, pages_y + 24.0)
        cover_path.cubicTo(
            pages_cx - page_w * 0.3, pages_y + 28.0,
            pages_cx - page_w * 0.75, pages_y - 12.0,
            pages_x - 8.0, pages_y + 6.0
        )
        cover_path.lineTo(pages_x - 8.0, pages_y + page_h + 12.0)
        cover_path.cubicTo(
            pages_cx - page_w * 0.75, pages_y + page_h - 4.0,
            pages_cx - page_w * 0.3, pages_y + page_h + 28.0,
            pages_cx, pages_y + page_h + 24.0
        )
        # Right side cover curve
        cover_path.cubicTo(
            pages_cx + page_w * 0.3, pages_y + page_h + 28.0,
            pages_cx + page_w * 0.75, pages_y + page_h - 4.0,
            pages_x + book_w + 8.0, pages_y + page_h + 12.0
        )
        cover_path.lineTo(pages_x + book_w + 8.0, pages_y + 6.0)
        cover_path.cubicTo(
            pages_cx + page_w * 0.75, pages_y - 12.0,
            pages_cx + page_w * 0.3, pages_y + 28.0,
            pages_cx, pages_y + 24.0
        )
        cover_path.closeSubpath()

        painter.fillPath(cover_path, cover_color)
        cover_stroke_color = QColor("#D4AF37") if is_dark else QColor(0, 0, 0, 30)
        painter.strokePath(cover_path, QPen(cover_stroke_color, 1.2))

        # Draw realistic cover spine hinge/crease lines next to binding
        painter.setPen(QPen(cover_color.darker(125), 1.6))
        painter.drawLine(QPointF(pages_cx - 16.0, pages_y + 12.0), QPointF(pages_cx - 16.0, pages_y + page_h + 16.0))
        painter.drawLine(QPointF(pages_cx + 16.0, pages_y + 12.0), QPointF(pages_cx + 16.0, pages_y + page_h + 16.0))

        # 3. Stacked Page Edges (Thickness) with fine leaf stack lines
        for offset in range(3, 0, -1):
            x_off = float(offset) * 2.0
            y_off = float(offset) * 1.5
            thick_path = QPainterPath()
            thick_path.moveTo(pages_cx, pages_y + 20.0 + y_off)
            
            # Left page bottom S-curve stack
            thick_path.cubicTo(
                pages_cx - page_w * 0.3, pages_y + 24.0 + y_off,
                pages_cx - page_w * 0.75, pages_y - 8.0 + y_off,
                pages_x + x_off, pages_y + 10.0 + y_off
            )
            thick_path.lineTo(pages_x + x_off, pages_y + page_h + 10.0 - y_off)
            thick_path.cubicTo(
                pages_cx - page_w * 0.75, pages_y + page_h - 8.0 - y_off,
                pages_cx - page_w * 0.3, pages_y + page_h + 24.0 - y_off,
                pages_cx, pages_y + page_h + 20.0 - y_off
            )
            # Right page bottom S-curve stack
            thick_path.cubicTo(
                pages_cx + page_w * 0.3, pages_y + page_h + 24.0 - y_off,
                pages_cx + page_w * 0.75, pages_y + page_h - 8.0 - y_off,
                pages_x + book_w - x_off, pages_y + page_h + 10.0 - y_off
            )
            thick_path.lineTo(pages_x + book_w - x_off, pages_y + 10.0 + y_off)
            thick_path.cubicTo(
                pages_cx + page_w * 0.75, pages_y - 8.0 + y_off,
                pages_cx + page_w * 0.3, pages_y + 24.0 + y_off,
                pages_cx, pages_y + 20.0 + y_off
            )
            thick_path.closeSubpath()
            
            # Fill thickness side base
            painter.fillPath(thick_path, page_color.darker(104 + (offset * 2)))
            
            # Draw fine horizontal lines inside page edge stack for realism
            painter.save()
            painter.setClipPath(thick_path)
            painter.setPen(QPen(page_color.darker(118), 0.6))
            for y_line in range(int(pages_y + 6.0), int(pages_y + page_h + 16.0), 3):
                painter.drawLine(QPointF(bx, float(y_line)), QPointF(bx + book_w, float(y_line)))
            painter.restore()

        # 4. Define 3D Curved Paths for Left and Right Open Page Surfaces (S-Curves)
        left_rect = QRectF(pages_x, pages_y, page_w, page_h)
        right_rect = QRectF(pages_cx, pages_y, page_w, page_h)

        left_page_path = QPainterPath()
        left_page_path.moveTo(pages_cx, pages_y + 20.0)
        left_page_path.cubicTo(
            pages_cx - page_w * 0.3, pages_y + 24.0,
            pages_cx - page_w * 0.75, pages_y - 8.0,
            pages_x, pages_y + 10.0
        )
        left_page_path.lineTo(pages_x, pages_y + page_h + 10.0)
        left_page_path.cubicTo(
            pages_cx - page_w * 0.75, pages_y + page_h - 8.0,
            pages_cx - page_w * 0.3, pages_y + page_h + 24.0,
            pages_cx, pages_y + page_h + 20.0
        )
        left_page_path.closeSubpath()
        
        right_page_path = QPainterPath()
        right_page_path.moveTo(pages_cx, pages_y + 20.0)
        right_page_path.cubicTo(
            pages_cx + page_w * 0.3, pages_y + 24.0,
            pages_cx + page_w * 0.75, pages_y - 8.0,
            pages_x + book_w, pages_y + 10.0
        )
        right_page_path.lineTo(pages_x + book_w, pages_y + page_h + 10.0)
        right_page_path.cubicTo(
            pages_cx + page_w * 0.75, pages_y + page_h - 8.0,
            pages_cx + page_w * 0.3, pages_y + page_h + 24.0,
            pages_cx, pages_y + page_h + 20.0
        )
        right_page_path.closeSubpath()

        # Combined S-curve perimeter path to outline the outer edges of the book ONLY
        perimeter_path = QPainterPath()
        perimeter_path.moveTo(pages_cx, pages_y + 20.0)
        perimeter_path.cubicTo(
            pages_cx - page_w * 0.3, pages_y + 24.0,
            pages_cx - page_w * 0.75, pages_y - 8.0,
            pages_x, pages_y + 10.0
        )
        perimeter_path.lineTo(pages_x, pages_y + page_h + 10.0)
        perimeter_path.cubicTo(
            pages_cx - page_w * 0.75, pages_y + page_h - 8.0,
            pages_cx - page_w * 0.3, pages_y + page_h + 24.0,
            pages_cx, pages_y + page_h + 20.0
        )
        perimeter_path.cubicTo(
            pages_cx + page_w * 0.3, pages_y + page_h + 24.0,
            pages_cx + page_w * 0.75, pages_y + page_h - 8.0,
            pages_x + book_w, pages_y + page_h + 10.0
        )
        perimeter_path.lineTo(pages_x + book_w, pages_y + 10.0)
        perimeter_path.cubicTo(
            pages_cx + page_w * 0.75, pages_y - 8.0,
            pages_cx + page_w * 0.3, pages_y + 24.0,
            pages_cx, pages_y + 20.0
        )
        perimeter_path.closeSubpath()

        # Draw a soft drop shadow from the elevated pages block onto the leather cover
        page_shadow_path = QPainterPath()
        page_shadow_path.addPath(perimeter_path.translated(0.0, 3.5))
        painter.fillPath(page_shadow_path, QColor(0, 0, 0, 45 if not is_dark else 75))

        # 5. Draw Page Surfaces
        if self.anim_progress >= 1.0 or self.prev_art is None:
            # Static View: Entire spread is filled as a continuous single surface
            painter.fillPath(perimeter_path, page_color)
            
            if self.current_art:
                self.draw_page_content(painter, self.current_art, True, left_rect, left_page_path)
                self.draw_page_content(painter, self.current_art, False, right_rect, right_page_path)
        else:
            # Interactive Page Turning (Drawing Book flipping physics)
            p = self.anim_progress
            theta = p * pi
            lift_y = 52.0 * sin(theta)  # Vertical lift distance
            
            # Compute physical folding crease coordinates
            flip_x = pages_cx + page_w * cos(theta)
            
            if self.anim_direction == 1:
                # Next Page Turn (Right-to-Left)
                # Background left page shows OLD art
                painter.fillPath(left_page_path, page_color)
                self.draw_page_content(painter, self.prev_art, True, left_rect, left_page_path)
                
                # Background right page shows NEW art
                painter.fillPath(right_page_path, page_color)
                self.draw_page_content(painter, self.current_art, False, right_rect, right_page_path)
                
                # Construct Arched, Curling Page Path
                flip_path = QPainterPath()
                if p < 0.5:
                    # Page lifting off right side
                    flip_w = flip_x - pages_cx
                    flip_rect = QRectF(pages_cx, pages_y, flip_w, page_h)
                    
                    flip_path.moveTo(pages_cx, pages_y + 20.0)
                    flip_path.quadTo(pages_cx + flip_w * 0.5, pages_y - 12.0 - lift_y, flip_x, pages_y + 10.0 - lift_y)
                    flip_path.lineTo(flip_x, pages_y + page_h + 10.0 - lift_y)
                    flip_path.quadTo(pages_cx + flip_w * 0.5, pages_y + page_h - 12.0 - lift_y, pages_cx, pages_y + page_h + 20.0)
                    flip_path.closeSubpath()
                    
                    painter.fillPath(flip_path, page_color)
                    self.draw_page_content(painter, self.prev_art, False, flip_rect, flip_path, draw_width=flip_w, lift_y=lift_y)
                    
                    # Draw specular highlight catching on the turning page
                    flip_grad = QLinearGradient(pages_cx, 0, flip_x, 0)
                    flip_grad.setColorAt(0.0, QColor(0, 0, 0, 15))
                    flip_grad.setColorAt(0.5, QColor(255, 255, 255, 30))
                    flip_grad.setColorAt(1.0, QColor(0, 0, 0, 25))
                    painter.save()
                    painter.setClipPath(flip_path)
                    painter.fillRect(flip_rect, QBrush(flip_grad))
                    painter.restore()

                    # Draw lift shadow cast on right page
                    shadow_w = 45.0 * sin(theta)
                    shadow_grad = QLinearGradient(flip_x, 0, flip_x + shadow_w, 0)
                    shadow_grad.setColorAt(0.0, QColor(0, 0, 0, int(75 * sin(theta))))
                    shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
                    painter.fillRect(QRectF(flip_x, pages_y + 10.0, shadow_w, page_h), QBrush(shadow_grad))
                else:
                    # Page landing on left side
                    flip_w = pages_cx - flip_x
                    flip_rect = QRectF(flip_x, pages_y, flip_w, page_h)
                    
                    flip_path.moveTo(flip_x, pages_y + 10.0 - lift_y)
                    flip_path.quadTo(flip_x + flip_w * 0.5, pages_y - 12.0 - lift_y, pages_cx, pages_y + 20.0)
                    flip_path.lineTo(pages_cx, pages_y + page_h + 20.0)
                    flip_path.quadTo(flip_x + flip_w * 0.5, pages_y + page_h - 12.0 - lift_y, flip_x, pages_y + page_h + 10.0 - lift_y)
                    flip_path.closeSubpath()
                    
                    painter.fillPath(flip_path, page_color)
                    self.draw_page_content(painter, self.current_art, True, flip_rect, flip_path, draw_width=flip_w, lift_y=lift_y)
                    
                    # Draw specular highlight catching on the landing page
                    flip_grad = QLinearGradient(flip_x, 0, pages_cx, 0)
                    flip_grad.setColorAt(0.0, QColor(0, 0, 0, 25))
                    flip_grad.setColorAt(0.5, QColor(255, 255, 255, 30))
                    flip_grad.setColorAt(1.0, QColor(0, 0, 0, 15))
                    painter.save()
                    painter.setClipPath(flip_path)
                    painter.fillRect(flip_rect, QBrush(flip_grad))
                    painter.restore()

                    # Draw lift shadow cast on left page
                    shadow_w = 45.0 * sin(theta)
                    shadow_grad = QLinearGradient(flip_x - shadow_w, 0, flip_x, 0)
                    shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
                    shadow_grad.setColorAt(1.0, QColor(0, 0, 0, int(75 * sin(theta))))
                    painter.fillRect(QRectF(flip_x - shadow_w, pages_y + 10.0, shadow_w, page_h), QBrush(shadow_grad))
            else:
                # Previous Page Turn (Left-to-Right)
                # Background left page shows NEW art
                painter.fillPath(left_page_path, page_color)
                self.draw_page_content(painter, self.current_art, True, left_rect, left_page_path)
                
                # Background right page shows OLD art
                painter.fillPath(right_page_path, page_color)
                self.draw_page_content(painter, self.prev_art, False, right_rect, right_page_path)
                
                # Construct Arched, Curling Page Path
                flip_path = QPainterPath()
                if p < 0.5:
                    # Page lifting off left side
                    flip_w = pages_cx - flip_x
                    flip_rect = QRectF(flip_x, pages_y, flip_w, page_h)
                    
                    flip_path.moveTo(flip_x, pages_y + 10.0 - lift_y)
                    flip_path.quadTo(flip_x + flip_w * 0.5, pages_y - 12.0 - lift_y, pages_cx, pages_y + 20.0)
                    flip_path.lineTo(pages_cx, pages_y + page_h + 20.0)
                    flip_path.quadTo(flip_x + flip_w * 0.5, pages_y + page_h - 12.0 - lift_y, flip_x, pages_y + page_h + 10.0 - lift_y)
                    flip_path.closeSubpath()
                    
                    painter.fillPath(flip_path, page_color)
                    self.draw_page_content(painter, self.prev_art, True, flip_rect, flip_path, draw_width=flip_w, lift_y=lift_y)
                    
                    # Specular highlight
                    flip_grad = QLinearGradient(flip_x, 0, pages_cx, 0)
                    flip_grad.setColorAt(0.0, QColor(0, 0, 0, 15))
                    flip_grad.setColorAt(0.5, QColor(255, 255, 255, 30))
                    flip_grad.setColorAt(1.0, QColor(0, 0, 0, 25))
                    painter.save()
                    painter.setClipPath(flip_path)
                    painter.fillRect(flip_rect, QBrush(flip_grad))
                    painter.restore()

                    # Draw lift shadow cast on left page
                    shadow_w = 45.0 * sin(theta)
                    shadow_grad = QLinearGradient(flip_x - shadow_w, 0, flip_x, 0)
                    shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
                    shadow_grad.setColorAt(1.0, QColor(0, 0, 0, int(75 * sin(theta))))
                    painter.fillRect(QRectF(flip_x - shadow_w, pages_y + 10.0, shadow_w, page_h), QBrush(shadow_grad))
                else:
                    # Page landing on right side
                    flip_w = flip_x - pages_cx
                    flip_rect = QRectF(pages_cx, pages_y, flip_w, page_h)
                    
                    flip_path.moveTo(pages_cx, pages_y + 20.0)
                    flip_path.quadTo(pages_cx + flip_w * 0.5, pages_y - 12.0 - lift_y, flip_x, pages_y + 10.0 - lift_y)
                    flip_path.lineTo(flip_x, pages_y + page_h + 10.0 - lift_y)
                    flip_path.quadTo(pages_cx + flip_w * 0.5, pages_y + page_h - 12.0 - lift_y, pages_cx, pages_y + page_h + 20.0)
                    flip_path.closeSubpath()
                    
                    painter.fillPath(flip_path, page_color)
                    self.draw_page_content(painter, self.current_art, False, flip_rect, flip_path, draw_width=flip_w, lift_y=lift_y)
                    
                    # Specular highlight
                    flip_grad = QLinearGradient(pages_cx, 0, flip_x, 0)
                    flip_grad.setColorAt(0.0, QColor(0, 0, 0, 25))
                    flip_grad.setColorAt(0.5, QColor(255, 255, 255, 30))
                    flip_grad.setColorAt(1.0, QColor(0, 0, 0, 15))
                    painter.save()
                    painter.setClipPath(flip_path)
                    painter.fillRect(flip_rect, QBrush(flip_grad))
                    painter.restore()

                    # Draw lift shadow cast on right page
                    shadow_w = 45.0 * sin(theta)
                    shadow_grad = QLinearGradient(flip_x, 0, flip_x + shadow_w, 0)
                    shadow_grad.setColorAt(0.0, QColor(0, 0, 0, int(75 * sin(theta))))
                    shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
                    painter.fillRect(QRectF(flip_x, pages_y + 10.0, shadow_w, page_h), QBrush(shadow_grad))

        # Stroke ONLY the perimeter (outer boundaries), ensuring no divider line cuts the artwork
        border_pen = QPen(page_color.darker(115), 1.0)
        painter.strokePath(perimeter_path, border_pen)

        # 6. Apply Procedural Parchment/Watercolor Paper Texture Overlay
        painter.save()
        painter.setClipPath(perimeter_path)
        painter.setOpacity(0.35 if not is_dark else 0.22)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        painter.drawTiledPixmap(QRectF(pages_x, pages_y + 10.0, book_w, page_h), self.paper_pixmap)
        painter.restore()

        # 7. Subtle Crease Fold Gutter (Only drawn DURING page turns to visualize geometry, absent when settled)
        if self.anim_progress < 1.0:
            spine_shadow = QLinearGradient(pages_cx - 32.0, 0.0, pages_cx + 32.0, 0.0)
            if is_dark:
                spine_shadow.setColorAt(0.0, QColor(0, 0, 0, 0))
                spine_shadow.setColorAt(0.5, QColor(0, 0, 0, 35))
                spine_shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
            else:
                spine_shadow.setColorAt(0.0, QColor(0, 0, 0, 0))
                spine_shadow.setColorAt(0.5, QColor(0, 0, 0, 20))
                spine_shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(QRectF(pages_cx - 32.0, pages_y + 10.0, 64.0, page_h + 8.0), QBrush(spine_shadow))

        # 8. 3D Curvature Specular Lighting (Highlight peaks shift dynamically with mouse DX)
        left_peak = 0.5 + self.mouse_dx * 0.08
        right_peak = 0.5 + self.mouse_dx * 0.08
        
        # Left Page Curve Shadows/Highlights (Clipped to left page for artwork blending)
        painter.save()
        painter.setClipPath(left_page_path)
        left_grad = QLinearGradient(pages_x, 0.0, pages_cx, 0.0)
        left_grad.setColorAt(0.0, QColor(0, 0, 0, int(20 - self.mouse_dx * 6)))
        left_grad.setColorAt(left_peak, QColor(255, 255, 255, int(28 + self.mouse_dy * 4 if not is_dark else 15)))
        left_grad.setColorAt(1.0, QColor(0, 0, 0, int(25 + self.mouse_dx * 6)))
        painter.fillRect(QRectF(pages_x, pages_y + 10.0, page_w, page_h + 8.0), QBrush(left_grad))
        painter.restore()

        # Right Page Curve Shadows/Highlights (Clipped to right page for artwork blending)
        painter.save()
        painter.setClipPath(right_page_path)
        right_grad = QLinearGradient(pages_cx, 0.0, pages_x + book_w, 0.0)
        right_grad.setColorAt(0.0, QColor(0, 0, 0, int(25 - self.mouse_dx * 6)))
        right_grad.setColorAt(right_peak, QColor(255, 255, 255, int(28 + self.mouse_dy * 4 if not is_dark else 15)))
        right_grad.setColorAt(1.0, QColor(0, 0, 0, int(20 + self.mouse_dx * 6)))
        painter.fillRect(QRectF(pages_cx, pages_y + 10.0, page_w, page_h + 8.0), QBrush(right_grad))
        painter.restore()


class ThumbnailCard(QWidget):
    """Horizontal thumbnail list card with hover delete button overlay."""

    clicked = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, art_dict: dict, theme: ThemeManager, is_selected: bool):
        super().__init__()
        self.art_id = art_dict["id"]
        self.theme = theme
        self.is_selected = is_selected
        self.setFixedSize(54, 76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.img_label = QLabel()
        self.img_label.setFixedSize(54, 76)
        self.img_label.setStyleSheet("border-radius: 6px; background: rgba(0,0,0,0.1);")
        
        img_path = art_dict.get("image_path")
        if img_path and os.path.exists(img_path):
            px = QPixmap(img_path)
            if not px.isNull():
                self.img_label.setPixmap(px.scaled(
                    54, 76, 
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                    Qt.TransformationMode.SmoothTransformation
                ))
        layout.addWidget(self.img_label)

        # Delete button overlay
        self.del_btn = QPushButton("✕", self)
        self.del_btn.setFixedSize(16, 16)
        self.del_btn.move(34, 4)
        self.del_btn.hide()
        self.del_btn.clicked.connect(self._on_delete)
        
        self.del_btn.setStyleSheet("""
            QPushButton {
                background: #E06D83;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 9px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #ff4d6d;
            }
        """)

        self._apply_style()

    def enterEvent(self, event):
        self.del_btn.show()

    def leaveEvent(self, event):
        self.del_btn.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.art_id)

    def _on_delete(self):
        self.delete_requested.emit(self.art_id)

    def _apply_style(self):
        t = self.theme
        border = f"2px solid {t.app('accent')}" if self.is_selected else f"1px solid {t.app('card_border')}"
        self.setStyleSheet(f"""
            ThumbnailCard {{
                border: {border};
                border-radius: 6px;
            }}
            ThumbnailCard:hover {{
                border: 2px solid {t.app('accent')};
            }}
        """)


class ArtView(QWidget):
    """
    Unified Art Gallery View showing a 3D book canvas,
    side navigation flip-buttons, and a bottom horizontal carousel of thumbnails.
    """

    def __init__(self, theme: ThemeManager):
        super().__init__()
        self.theme = theme
        self.repo = ArtRepository()
        self.artworks = []
        self._selected_art_id = None

        self._build_ui()
        self._apply_theme()
        self.refresh()
        self._setup_shortcuts()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header (Consistent with library/settings views)
        header = QWidget()
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)

        self.title_label = QLabel("Art Gallery")
        self.title_label.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {self.theme.app('text_primary')};")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.layout_toggle_btn = QPushButton("Double")
        self.layout_toggle_btn.setFixedHeight(34)
        self.layout_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.layout_toggle_btn.clicked.connect(self._on_toggle_layout)
        header_layout.addWidget(self.layout_toggle_btn)

        # Spacer between buttons
        header_layout.addSpacing(10)

        self.upload_btn = QPushButton("＋  Upload")
        self.upload_btn.setFixedHeight(34)
        self.upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upload_btn.clicked.connect(self._on_upload)
        header_layout.addWidget(self.upload_btn)

        main_layout.addWidget(header)

        # 2. Divider
        self.divider = QWidget()
        self.divider.setFixedHeight(1)
        main_layout.addWidget(self.divider)

        # 3. Canvas Container (Book & side navigation arrows)
        canvas_container = QWidget()
        cc_layout = QHBoxLayout(canvas_container)
        cc_layout.setContentsMargins(24, 20, 24, 5)
        cc_layout.setSpacing(16)

        # Left Flip Button
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(40, 60)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.clicked.connect(self._on_prev)
        cc_layout.addWidget(self.prev_btn)

        # Center book & captions container
        center_book_layout = QVBoxLayout()
        center_book_layout.setContentsMargins(0, 0, 0, 0)
        center_book_layout.setSpacing(6)
        
        self.book_canvas = ArtBookWidget(self.theme)
        self.book_canvas.page_clicked.connect(self._on_page_clicked)
        center_book_layout.addWidget(self.book_canvas, 1)
        
        # Caption below the book
        self.caption_label = QLabel("")
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_book_layout.addWidget(self.caption_label)

        self.date_label = QLabel("")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_book_layout.addWidget(self.date_label)

        cc_layout.addLayout(center_book_layout, 1)

        # Right Flip Button
        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(40, 60)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.clicked.connect(self._on_next)
        cc_layout.addWidget(self.next_btn)

        main_layout.addWidget(canvas_container, 1)

        # 4. Horizontal Thumbnail Carousel at bottom
        self.carousel_area = QScrollArea()
        self.carousel_area.setFixedHeight(110)
        self.carousel_area.setWidgetResizable(True)
        self.carousel_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.carousel_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.carousel_container = QWidget()
        self.carousel_layout = QHBoxLayout(self.carousel_container)
        self.carousel_layout.setContentsMargins(24, 10, 24, 10)
        self.carousel_layout.setSpacing(12)
        self.carousel_layout.addStretch()
        
        self.carousel_area.setWidget(self.carousel_container)
        main_layout.addWidget(self.carousel_area)

    def _setup_shortcuts(self):
        # Arrow Keys Shortcuts
        self.prev_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.prev_shortcut.activated.connect(self._on_prev)
        self.next_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.next_shortcut.activated.connect(self._on_next)

    def _apply_theme(self):
        t = self.theme
        is_dark = "Dark" in t.app("name", "dark")
        btn_txt_color = "#181614" if is_dark else "#FFFFFF"
        
        self.setStyleSheet(f"ArtView {{ background: {t.app('window_bg')}; }}")
        self.divider.setStyleSheet(f"background: {t.app('divider')};")
        
        self.upload_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.app('accent')};
                color: {btn_txt_color};
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {t.app('accent_hover')};
            }}
        """)

        self.layout_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.app('card_bg')};
                color: {t.app('text_primary')};
                border: 1px solid {t.app('card_border')};
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {t.app('card_hover')};
                border: 1px solid {t.app('accent')};
            }}
        """)

        arrow_style = f"""
            QPushButton {{
                background: {t.app('card_bg')};
                color: {t.app('text_primary')};
                border: 1px solid {t.app('card_border')};
                border-radius: 20px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {t.app('card_hover')};
                border: 1px solid {t.app('accent')};
            }}
        """
        self.prev_btn.setStyleSheet(arrow_style)
        self.next_btn.setStyleSheet(arrow_style)
        
        self.carousel_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: {t.app('card_bg')};
                border-top: 1px solid {t.app('divider')};
            }}
        """)
        self.carousel_container.setStyleSheet(f"background: {t.app('card_bg')};")

        self.caption_label.setStyleSheet(f"""
            font-size: 15px;
            font-family: 'Georgia';
            font-weight: bold;
            color: {t.app('text_primary')};
            background: transparent;
        """)
        self.date_label.setStyleSheet(f"""
            font-size: 11px;
            font-family: 'Georgia';
            font-style: italic;
            color: {t.app('text_muted')};
            background: transparent;
        """)

    def refresh(self, animate_dir: int = 0):
        self.artworks = self.repo.get_all()
        
        # Clear list layout (except stretch)
        while self.carousel_layout.count() > 1:
            item = self.carousel_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        selected_art = None
        for art in self.artworks:
            is_selected = (art["id"] == self._selected_art_id)
            card = ThumbnailCard(art, self.theme, is_selected)
            card.clicked.connect(lambda aid: self._on_art_card_clicked(aid))
            card.delete_requested.connect(self._on_art_delete)
            self.carousel_layout.insertWidget(self.carousel_layout.count() - 1, card)
            
            if is_selected:
                selected_art = art

        # Update showcase book
        if selected_art:
            self.book_canvas.set_artwork(selected_art, animate_dir)
            self._update_captions(selected_art)
        elif self.artworks:
            first_art = self.artworks[0]
            self._selected_art_id = first_art["id"]
            self.book_canvas.set_artwork(first_art, 0)
            self._update_captions(first_art)
            self.refresh()
        else:
            self._selected_art_id = None
            self.book_canvas.set_artwork(None, 0)
            self.caption_label.setText("")
            self.date_label.setText("")

    def _update_captions(self, art_dict):
        self.caption_label.setText(art_dict.get("title", "Untitled"))
        
        created_str = art_dict.get("created_at", "")
        try:
            dt = datetime.fromisoformat(created_str)
            date_text = dt.strftime("%B %d, %Y")
        except Exception:
            date_text = created_str or "Unknown Date"
        self.date_label.setText(f"Exhibited on {date_text}")

    def _on_art_card_clicked(self, art_id: str):
        if self._selected_art_id == art_id:
            return
            
        current_idx = next((i for i, a in enumerate(self.artworks) if a["id"] == self._selected_art_id), 0)
        target_idx = next((i for i, a in enumerate(self.artworks) if a["id"] == art_id), 0)
        
        direction = 1 if target_idx < current_idx else -1
        
        self._selected_art_id = art_id
        self.refresh(animate_dir=direction)

    def _on_toggle_layout(self):
        self.book_canvas.is_double_page = not self.book_canvas.is_double_page
        if self.book_canvas.is_double_page:
            self.layout_toggle_btn.setText("Double")
        else:
            self.layout_toggle_btn.setText("Single")
        self.book_canvas.update()

    def _on_page_clicked(self, direction):
        if direction == -1:
            self._on_prev()
        else:
            self._on_next()

    def _on_prev(self):
        if not self.artworks or not self._selected_art_id:
            return
        idx = next((i for i, a in enumerate(self.artworks) if a["id"] == self._selected_art_id), 0)
        if idx < len(self.artworks) - 1:
            self._selected_art_id = self.artworks[idx + 1]["id"]
            self.refresh(animate_dir=-1)
        else:
            self._selected_art_id = self.artworks[0]["id"]
            self.refresh(animate_dir=-1)

    def _on_next(self):
        if not self.artworks or not self._selected_art_id:
            return
        idx = next((i for i, a in enumerate(self.artworks) if a["id"] == self._selected_art_id), 0)
        if idx > 0:
            self._selected_art_id = self.artworks[idx - 1]["id"]
            self.refresh(animate_dir=1)
        else:
            self._selected_art_id = self.artworks[-1]["id"]
            self.refresh(animate_dir=1)

    def _on_upload(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Upload Art Creations", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not file_paths:
            return

        last_id = None
        for fp in file_paths:
            title = Path(fp).stem
            try:
                last_id = self.repo.add(title, "", fp)
            except Exception as e:
                QMessageBox.critical(self, "Upload Failed", f"Failed to upload '{Path(fp).name}': {e}")

        if last_id:
            self._selected_art_id = last_id
            self.refresh(animate_dir=1)

    def _on_art_delete(self, art_id: str):
        confirm = QMessageBox.question(
            self, "Delete Creation",
            "Are you sure you want to delete this artwork from your gallery?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self.repo.delete(art_id)
                if self._selected_art_id == art_id:
                    self._selected_art_id = None
                self.refresh(animate_dir=0)
            except Exception as e:
                QMessageBox.critical(self, "Delete Failed", f"Failed to delete art: {e}")
