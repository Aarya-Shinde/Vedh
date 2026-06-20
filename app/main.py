import sys
from pathlib import Path

# Make sure root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase, QFont
from ui.main_window import MainWindow
from storage.database import init_db
from storage.repositories import BookRepository
from core.theme_manager import ThemeManager
from core.plugin_manager import PluginManager


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Vedh")
    app.setApplicationVersion("1.0.0")

    # Init DB
    init_db()

    # Load and register bundled fonts
    try:
        font_dir = Path(__file__).parent.parent / "assets" / "fonts"
        font_dir.mkdir(parents=True, exist_ok=True)
        lora_reg = font_dir / "Lora-Regular.ttf"
        lora_ital = font_dir / "Lora-Italic.ttf"
        
        import urllib.request
        # Download Lora fonts if they do not exist
        if not lora_reg.exists():
            urllib.request.urlretrieve("https://github.com/cyrealtype/Lora-Cyrillic/raw/main/fonts/ttf/Lora-Regular.ttf", lora_reg)
        if not lora_ital.exists():
            urllib.request.urlretrieve("https://github.com/cyrealtype/Lora-Cyrillic/raw/main/fonts/ttf/Lora-Italic.ttf", lora_ital)
            
        if lora_reg.exists():
            QFontDatabase.addApplicationFont(str(lora_reg))
        if lora_ital.exists():
            QFontDatabase.addApplicationFont(str(lora_ital))
            
        motterdam_path = font_dir / "motterdam.ttf"
        if motterdam_path.exists():
            QFontDatabase.addApplicationFont(str(motterdam_path))
    except Exception as e:
        print(f"Failed to load bundled fonts: {e}")

    # Validate file paths on startup
    repo = BookRepository()
    repo.validate_paths()

    # Theme
    theme = ThemeManager()
    theme.load_defaults()
    app.setStyleSheet(theme.build_stylesheet())

    # Toast Manager
    from ui.widgets.toast import ToastManager
    ToastManager.get_instance().initialize(theme)

    # Plugins
    plugins = PluginManager()
    plugins_dir = Path(__file__).parent.parent / "plugins"
    plugins.load_from_dir(plugins_dir)

    # Launch
    window = MainWindow(theme=theme, plugins=plugins)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()