import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".vedh" / "vedh.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                author      TEXT,
                cover       BLOB,
                file_path   TEXT NOT NULL,
                format      TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'ok',
                language    TEXT,
                publisher   TEXT,
                description TEXT,
                tags        TEXT,
                book_type   TEXT DEFAULT 'unknown',
                is_favorite INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS reading_progress (
                id          TEXT PRIMARY KEY,
                book_id     TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                chapter     INTEGER DEFAULT 0,
                page        INTEGER DEFAULT 0,
                position    REAL DEFAULT 0.0,
                percentage  REAL DEFAULT 0.0,
                device_id   TEXT,
                updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(book_id)
            );

            CREATE TABLE IF NOT EXISTS notes (
                id          TEXT PRIMARY KEY,
                book_id     TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                content     TEXT NOT NULL,
                location    TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS highlights (
                id          TEXT PRIMARY KEY,
                book_id     TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                text        TEXT NOT NULL,
                color       TEXT DEFAULT '#FFEB3B',
                location    TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                id          TEXT PRIMARY KEY,
                book_id     TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                position    TEXT NOT NULL,
                label       TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tags (
                id       TEXT PRIMARY KEY,
                name     TEXT NOT NULL UNIQUE,
                color    TEXT NOT NULL DEFAULT '#4A6FA5',
                is_auto  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS book_tags (
                book_id  TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                tag_id   TEXT NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
                PRIMARY KEY (book_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS collections (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                icon        TEXT NOT NULL DEFAULT '•',
                is_default  INTEGER NOT NULL DEFAULT 0,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS book_collections (
                book_id         TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                collection_id   TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                PRIMARY KEY (book_id, collection_id)
            );

            CREATE TABLE IF NOT EXISTS reading_sessions (
                id          TEXT PRIMARY KEY,
                book_id     TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                started_at  TEXT NOT NULL,
                ended_at    TEXT,
                pages_read  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS devices (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                last_seen   TEXT
            );
        """)

        # Migrate existing emojis to bullets
        conn.execute("UPDATE collections SET icon = '•' WHERE icon IN ('📁', '📖', '📚', '🔖', '📋', '✅')")
        
        # Add columns if not exists
        try:
            conn.execute("ALTER TABLE books ADD COLUMN is_favorite INTEGER DEFAULT 0")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE books ADD COLUMN hash TEXT")
        except Exception:
            pass

        # Seed default collections if not already present
        _seed_defaults(conn)

    conn.close()


def _seed_defaults(conn):
    defaults = [
        ("fanfic-default",           "Fanfic",            "•", 1, 0),
        ("originals-default",        "Originals",         "•", 1, 1),
        ("currently-reading-default","Currently Reading", "•", 1, 2),
        ("tbr-default",              "TBR",               "•", 1, 3),
        ("completed-default",        "Completed",         "•", 1, 4),
    ]
    for cid, name, icon, is_default, sort_order in defaults:
        conn.execute("""
            INSERT OR IGNORE INTO collections
                (id, name, icon, is_default, sort_order)
            VALUES (?, ?, ?, ?, ?)
        """, (cid, name, icon, is_default, sort_order))

    # Seed default tags
    default_tags = [
        ("tag-fanfic",     "fanfic",     "#E91E8C", 1),
        ("tag-published",  "published",  "#4A6FA5", 1),
        ("tag-manga",      "manga",      "#E67E22", 1),
        ("tag-comic",      "comic",      "#27AE60", 1),
        ("tag-completed",  "completed",  "#27AE60", 0),
        ("tag-abandoned",  "abandoned",  "#C0392B", 0),
        ("tag-favourite",  "favourite",  "#F1C40F", 0),
    ]
    for tid, name, color, is_auto in default_tags:
        conn.execute("""
            INSERT OR IGNORE INTO tags (id, name, color, is_auto)
            VALUES (?, ?, ?, ?)
        """, (tid, name, color, is_auto))