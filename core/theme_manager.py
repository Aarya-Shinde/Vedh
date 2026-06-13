import json
from pathlib import Path
from typing import Optional


THEMES_DIR = Path(__file__).parent.parent / "themes"


class ThemeManager:

    def __init__(self):
        self._app_theme: dict = {}
        self._reader_theme: dict = {}
        self._app_theme_name: str = "dark"
        self._reader_theme_name: str = "default"

    # ── Loading ────────────────────────────────────────────────────────────

    def load_app_theme(self, name: str):
        path = THEMES_DIR / "app" / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"App theme not found: {name}")
        with open(path) as f:
            self._app_theme = json.load(f)
        self._app_theme_name = name
        from core.config_manager import ConfigManager
        ConfigManager().set("app_theme", name)

    def load_reader_theme(self, name: str):
        path = THEMES_DIR / "reader" / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Reader theme not found: {name}")
        with open(path) as f:
            self._reader_theme = json.load(f)
        self._reader_theme_name = name
        from core.config_manager import ConfigManager
        ConfigManager().set("reader_theme", name)

    def load_defaults(self):
        from core.config_manager import ConfigManager
        cfg = ConfigManager()
        self.load_app_theme(cfg.get("app_theme", "dark"))
        self.load_reader_theme(cfg.get("reader_theme", "default"))

        # Load other settings from config into self._reader_theme
        self._reader_theme["font_family"] = cfg.get("font_family", "Georgia")
        self._reader_theme["font_size"] = cfg.get("font_size", 18.0)
        self._reader_theme["line_spacing"] = cfg.get("line_spacing", 1.6)
        self._reader_theme["page_width"] = cfg.get("page_width", 750.0)
        self._reader_theme["margin_h"] = cfg.get("margin_h", 48.0)
        self._reader_theme["margin_v"] = cfg.get("margin_v", 40.0)

    # ── Accessors ──────────────────────────────────────────────────────────

    def app(self, key: str, fallback: str = "#000000") -> str:
        return self._app_theme.get(key, fallback)

    def reader(self, key: str, fallback=None):
        return self._reader_theme.get(key, fallback)

    def app_theme(self) -> dict:
        return dict(self._app_theme)

    def reader_theme(self) -> dict:
        return dict(self._reader_theme)

    # ── Discovery ──────────────────────────────────────────────────────────

    def available_app_themes(self) -> list[str]:
        return [p.stem for p in (THEMES_DIR / "app").glob("*.json")]

    def available_reader_themes(self) -> list[str]:
        return [p.stem for p in (THEMES_DIR / "reader").glob("*.json")]

    # ── Qt stylesheet ──────────────────────────────────────────────────────

    def build_stylesheet(self) -> str:
        t = self._app_theme
        return f"""
            QMainWindow, QWidget {{
                background-color: {t.get('window_bg', '#0F0F0F')};
                color: {t.get('text_primary', '#EEEEEE')};
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 13px;
            }}
            QScrollBar:vertical {{
                background: {t.get('window_bg', '#0F0F0F')};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {t.get('scrollbar', '#2A2A2A')};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t.get('scrollbar_hover', '#3A3A3A')};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background: {t.get('window_bg', '#0F0F0F')};
                height: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{
                background: {t.get('scrollbar', '#2A2A2A')};
                border-radius: 3px;
            }}
            QToolTip {{
                background-color: {t.get('card_bg', '#1A1A1A')};
                color: {t.get('text_primary', '#EEEEEE')};
                border: 1px solid {t.get('card_border', '#2A2A2A')};
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """