from abc import ABC, abstractmethod
from pathlib import Path
import importlib.util
import sys


class Plugin(ABC):
    name: str = "unnamed"
    version: str = "0.1.0"

    def on_book_import(self, book_id: str, file_path: str):
        pass

    def on_book_open(self, book_id: str):
        pass

    def on_page_change(self, book_id: str, chapter: int, page: int):
        pass

    # Reserved — not active yet
    # def on_text_selected(self, text: str, location: str):
    #     pass


class PluginManager:

    def __init__(self):
        self._plugins: list[Plugin] = []

    def load_from_dir(self, plugins_dir: Path):
        if not plugins_dir.exists():
            return
        for path in plugins_dir.glob("*.py"):
            self._load_file(path)

    def _load_file(self, path: Path):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        try:
            spec.loader.exec_module(module)
            for attr in vars(module).values():
                if (isinstance(attr, type)
                        and issubclass(attr, Plugin)
                        and attr is not Plugin):
                    instance = attr()
                    self._plugins.append(instance)
                    print(f"[PluginManager] Loaded: {instance.name}")
        except Exception as e:
            print(f"[PluginManager] Failed to load {path.name}: {e}")

    def emit_book_import(self, book_id: str, file_path: str):
        for p in self._plugins:
            try:
                p.on_book_import(book_id, file_path)
            except Exception as e:
                print(f"[Plugin:{p.name}] on_book_import error: {e}")

    def emit_book_open(self, book_id: str):
        for p in self._plugins:
            try:
                p.on_book_open(book_id)
            except Exception as e:
                print(f"[Plugin:{p.name}] on_book_open error: {e}")

    def emit_page_change(self, book_id: str, chapter: int, page: int):
        for p in self._plugins:
            try:
                p.on_page_change(book_id, chapter, page)
            except Exception as e:
                print(f"[Plugin:{p.name}] on_page_change error: {e}")