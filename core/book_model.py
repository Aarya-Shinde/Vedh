from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
from uuid import UUID


class BlockType(Enum):
    # Phase 1 — fully implemented
    PARAGRAPH   = auto()
    HEADING     = auto()
    IMAGE       = auto()
    QUOTE       = auto()
    PAGE_BREAK  = auto()

    # Acknowledged — adapters can emit, renderer skips gracefully
    TABLE           = auto()
    CODE_BLOCK      = auto()
    FOOTNOTE_REF    = auto()
    HORIZONTAL_RULE = auto()
    CAPTION         = auto()


@dataclass
class Block:
    type: BlockType

    # Text-based blocks
    text: Optional[str] = None
    level: Optional[int] = None          # Heading level: 1-6

    # Image blocks
    image_data: Optional[bytes] = None
    image_path: Optional[str] = None
    alt_text: Optional[str] = None

    # Shared
    attrs: dict = field(default_factory=dict)   # future-proofing, anything extra


@dataclass
class Chapter:
    id: str
    title: str
    blocks: list[Block] = field(default_factory=list)
    order: int = 0


@dataclass
class BookMetadata:
    title: str
    author: str
    language: str = "en"
    publisher: Optional[str] = None
    description: Optional[str] = None
    cover_data: Optional[bytes] = None
    tags: list[str] = field(default_factory=list)


@dataclass
class Book:
    id: UUID
    metadata: BookMetadata
    file_path: str
    format: str                                  # "epub", "pdf", "cbz", etc.
    chapters: list[Chapter] = field(default_factory=list)
    status: str = "ok"                           # "ok" | "missing"

    def is_available(self) -> bool:
        return self.status == "ok"

    def all_blocks(self):
        """Flat iterator over every block in the book."""
        for chapter in self.chapters:
            yield from chapter.blocks