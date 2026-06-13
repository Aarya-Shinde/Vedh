import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".vedh" / "config.json"

class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._config = {
            "username": "Reader",
            "app_theme": "dark",
            "reader_theme": "default",
            "font_family": "Georgia",
            "font_size": 18.0,
            "line_spacing": 1.6,
            "page_width": 750.0,
            "margin_h": 48.0,
            "margin_v": 40.0,
            "auto_classify": True,
            "auto_assign": True
        }
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
                    self._config.update(data)
            except Exception as e:
                print(f"[ConfigManager] Error loading config: {e}")

    def save(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self._config, f, indent=4)
        except Exception as e:
            print(f"[ConfigManager] Error saving config: {e}")

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value
        self.save()
