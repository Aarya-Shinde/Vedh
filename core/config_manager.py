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
            "line_spacing": 2.0,
            "page_width": 900.0,
            "margin_h": 100.0,
            "margin_v": 40.0,
            "auto_classify": True,
            "auto_assign": True
        }
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
                    if data.get("page_width") in (750.0, 850.0):
                        data["page_width"] = 900.0
                    if data.get("margin_h") in (48.0, 90.0):
                        data["margin_h"] = 100.0
                    if data.get("line_spacing") in (1.6, 1.8):
                        data["line_spacing"] = 2.0
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
