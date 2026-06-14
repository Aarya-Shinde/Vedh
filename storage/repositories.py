import json
import uuid
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from storage.database import get_connection
from core.book_model import BookMetadata


def save_cover_image(book_id: str, cover_bytes: bytes) -> Optional[str]:
    if not cover_bytes:
        return None
    cover_dir = Path.home() / ".vedh" / "covers"
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover_path = cover_dir / f"{book_id}.png"
    try:
        cover_path.write_bytes(cover_bytes)
        return str(cover_path)
    except Exception as e:
        print(f"Failed to save cover image: {e}")
        return None


class BookRepository:

    def add(self, metadata: BookMetadata, file_path: str, fmt: str) -> str:
        # Calculate SHA-256 hash of the file for duplicate check
        import hashlib
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
        except Exception:
            file_hash = None

        if file_hash:
            conn = get_connection()
            dup = conn.execute("SELECT id, title, file_path, status, cover FROM books WHERE hash = ?", (file_hash,)).fetchone()
            conn.close()
            if dup:
                cover_val = dup["cover"]
                if metadata.cover_data and not cover_val:
                    cover_val = save_cover_image(dup["id"], metadata.cover_data)
                
                conn = get_connection()
                with conn:
                    conn.execute("""
                        UPDATE books 
                        SET title = ?, author = ?, cover = COALESCE(?, cover), 
                            file_path = ?, status = 'ok', language = ?, 
                            publisher = ?, description = ?, updated_at = ?
                        WHERE id = ?
                    """, (
                        metadata.title, metadata.author, cover_val,
                        file_path, metadata.language, metadata.publisher,
                        metadata.description, datetime.now().isoformat(), dup["id"]
                    ))
                conn.close()
                return dup["id"]

        book_id = str(uuid.uuid4())
        tags = json.dumps(metadata.tags)

        # Save cover image to disk if present
        cover_val = None
        if metadata.cover_data:
            cover_val = save_cover_image(book_id, metadata.cover_data)

        conn = get_connection()
        with conn:
            conn.execute("""
                INSERT INTO books
                    (id, title, author, cover, file_path, format, language, publisher, description, tags, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                book_id,
                metadata.title,
                metadata.author,
                cover_val,
                file_path,
                fmt,
                metadata.language,
                metadata.publisher,
                metadata.description,
                tags,
                file_hash,
            ))
        conn.close()
        return book_id

    def get_all(self) -> list[sqlite3.Row]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM books ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return rows

    def get_by_id(self, book_id: str) -> Optional[sqlite3.Row]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        conn.close()
        return row

    def mark_missing(self, book_id: str):
        conn = get_connection()
        with conn:
            conn.execute(
                "UPDATE books SET status = 'missing', updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), book_id)
            )
        conn.close()

    def delete(self, book_id: str):
        conn = get_connection()
        with conn:
            # Delete cover file if it exists on disk
            row = conn.execute("SELECT cover FROM books WHERE id = ?", (book_id,)).fetchone()
            if row and row["cover"]:
                try:
                    cover_path = Path(row["cover"])
                    if cover_path.exists() and cover_path.is_file():
                        cover_path.unlink()
                except Exception as e:
                    print(f"Failed to delete cover file: {e}")
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.close()

    def toggle_favorite(self, book_id: str) -> bool:
        conn = get_connection()
        row = conn.execute("SELECT is_favorite FROM books WHERE id = ?", (book_id,)).fetchone()
        new_val = 1
        if row and row["is_favorite"]:
            new_val = 0
        with conn:
            conn.execute("UPDATE books SET is_favorite = ?, updated_at = ? WHERE id = ?", (new_val, datetime.now().isoformat(), book_id))
        conn.close()
        return bool(new_val)

    def validate_paths(self):
        """Run on startup — flag any books whose file no longer exists."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, file_path FROM books WHERE status = 'ok'"
        ).fetchall()
        conn.close()
        for row in rows:
            if not Path(row["file_path"]).exists():
                self.mark_missing(row["id"])


class ProgressRepository:

    def save(self, book_id: str, chapter: int, page: int,
             position: float, percentage: float, device_id: str = "desktop"):
        progress_id = str(uuid.uuid4())
        conn = get_connection()
        with conn:
            conn.execute("""
                INSERT INTO reading_progress
                    (id, book_id, chapter, page, position, percentage, device_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id) DO UPDATE SET
                    chapter = excluded.chapter,
                    page = excluded.page,
                    position = excluded.position,
                    percentage = excluded.percentage,
                    updated_at = excluded.updated_at
            """, (
                progress_id, book_id, chapter, page,
                position, percentage, device_id,
                datetime.now().isoformat()
            ))

            # Sync default status collections
            if percentage >= 100.0:
                conn.execute("INSERT OR IGNORE INTO book_collections (book_id, collection_id) VALUES (?, 'completed-default')", (book_id,))
                conn.execute("DELETE FROM book_collections WHERE book_id = ? AND collection_id = 'currently-reading-default'", (book_id,))
                conn.execute("DELETE FROM book_collections WHERE book_id = ? AND collection_id = 'tbr-default'", (book_id,))
            elif percentage > 0.0:
                conn.execute("INSERT OR IGNORE INTO book_collections (book_id, collection_id) VALUES (?, 'currently-reading-default')", (book_id,))
                conn.execute("DELETE FROM book_collections WHERE book_id = ? AND collection_id = 'completed-default'", (book_id,))
                conn.execute("DELETE FROM book_collections WHERE book_id = ? AND collection_id = 'tbr-default'", (book_id,))
            else:
                conn.execute("INSERT OR IGNORE INTO book_collections (book_id, collection_id) VALUES (?, 'tbr-default')", (book_id,))
                conn.execute("DELETE FROM book_collections WHERE book_id = ? AND collection_id = 'currently-reading-default'", (book_id,))
                conn.execute("DELETE FROM book_collections WHERE book_id = ? AND collection_id = 'completed-default'", (book_id,))
        conn.close()

    def get(self, book_id: str) -> Optional[sqlite3.Row]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM reading_progress WHERE book_id = ?", (book_id,)
        ).fetchone()
        conn.close()
        return row



class TagRepository:

    def get_or_create(self, name: str, color: str = "#4A6FA5",
                      is_auto: bool = False) -> str:
        conn = get_connection()
        row  = conn.execute(
            "SELECT id FROM tags WHERE name = ?", (name,)
        ).fetchone()

        if row:
            conn.close()
            return row["id"]

        tag_id = str(uuid.uuid4())
        with conn:
            conn.execute(
                "INSERT INTO tags (id, name, color, is_auto) VALUES (?,?,?,?)",
                (tag_id, name, color, int(is_auto))
            )
        conn.close()
        return tag_id

    def get_all(self) -> list:
        conn = get_connection()
        rows = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
        conn.close()
        return rows

    def add_to_book(self, book_id: str, tag_id: str):
        conn = get_connection()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO book_tags (book_id, tag_id) "
                "VALUES (?, ?)",
                (book_id, tag_id)
            )
        conn.close()

    def remove_from_book(self, book_id: str, tag_id: str):
        conn = get_connection()
        with conn:
            conn.execute(
                "DELETE FROM book_tags WHERE book_id=? AND tag_id=?",
                (book_id, tag_id)
            )
        conn.close()

    def get_for_book(self, book_id: str) -> list:
        conn = get_connection()
        rows = conn.execute("""
            SELECT t.* FROM tags t
            JOIN book_tags bt ON bt.tag_id = t.id
            WHERE bt.book_id = ?
        """, (book_id,)).fetchall()
        conn.close()
        return rows


class CollectionRepository:

    def get_all(self) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM collections ORDER BY sort_order, name"
        ).fetchall()
        conn.close()
        return rows

    def create(self, name: str, icon: str = "•") -> str:
        cid = str(uuid.uuid4())
        # Get next sort order
        conn = get_connection()
        max_order = conn.execute(
            "SELECT MAX(sort_order) FROM collections"
        ).fetchone()[0] or 0
        with conn:
            conn.execute(
                "INSERT INTO collections (id, name, icon, is_default, sort_order) "
                "VALUES (?, ?, ?, 0, ?)",
                (cid, name, icon, max_order + 1)
            )
        conn.close()
        return cid

    def rename(self, collection_id: str, new_name: str):
        conn = get_connection()
        with conn:
            conn.execute(
                "UPDATE collections SET name=? WHERE id=?",
                (new_name, collection_id)
            )
        conn.close()

    def delete(self, collection_id: str):
        conn = get_connection()
        with conn:
            conn.execute(
                "DELETE FROM collections WHERE id=? AND is_default=0",
                (collection_id,)
            )
        conn.close()

    def add_book(self, book_id: str, collection_id: str):
        conn = get_connection()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO book_collections "
                "(book_id, collection_id) VALUES (?,?)",
                (book_id, collection_id)
            )
        conn.close()

    def remove_book(self, book_id: str, collection_id: str):
        conn = get_connection()
        with conn:
            conn.execute(
                "DELETE FROM book_collections "
                "WHERE book_id=? AND collection_id=?",
                (book_id, collection_id)
            )
        conn.close()

    def get_books(self, collection_id: str) -> list:
        conn = get_connection()
        rows = conn.execute("""
            SELECT b.* FROM books b
            JOIN book_collections bc ON bc.book_id = b.id
            WHERE bc.collection_id = ?
            ORDER BY b.created_at DESC
        """, (collection_id,)).fetchall()
        conn.close()
        return rows

    def get_for_book(self, book_id: str) -> list:
        conn = get_connection()
        rows = conn.execute("""
            SELECT c.* FROM collections c
            JOIN book_collections bc ON bc.collection_id = c.id
            WHERE bc.book_id = ?
        """, (book_id,)).fetchall()
        conn.close()
        return rows


class SessionRepository:

    def start_session(self, book_id: str) -> str:
        from datetime import datetime
        session_id = str(uuid.uuid4())
        conn = get_connection()
        with conn:
            conn.execute(
                "INSERT INTO reading_sessions "
                "(id, book_id, started_at) VALUES (?,?,?)",
                (session_id, book_id, datetime.now().isoformat())
            )
        conn.close()
        return session_id

    def end_session(self, session_id: str, pages_read: int):
        from datetime import datetime
        conn = get_connection()
        with conn:
            conn.execute(
                "UPDATE reading_sessions SET ended_at=?, pages_read=? "
                "WHERE id=?",
                (datetime.now().isoformat(), pages_read, session_id)
            )
        conn.close()

    def get_all_sessions(self) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM reading_sessions WHERE ended_at IS NOT NULL "
            "ORDER BY started_at DESC"
        ).fetchall()
        conn.close()
        return rows

    def get_sessions_for_book(self, book_id: str) -> list:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM reading_sessions WHERE book_id=? "
            "AND ended_at IS NOT NULL ORDER BY started_at DESC",
            (book_id,)
        ).fetchall()
        conn.close()
        return rows


class StatsRepository:

    def get_overview(self) -> dict:
        conn = get_connection()

        total_books = conn.execute(
            "SELECT COUNT(*) FROM books WHERE status='ok'"
        ).fetchone()[0]

        completed = conn.execute(
            "SELECT COUNT(DISTINCT bt.book_id) FROM book_tags bt "
            "JOIN tags t ON t.id=bt.tag_id WHERE t.name='completed'"
        ).fetchone()[0]

        in_progress = conn.execute(
            "SELECT COUNT(*) FROM reading_progress "
            "WHERE percentage > 0 AND percentage < 100"
        ).fetchone()[0]

        total_pages = conn.execute(
            "SELECT COALESCE(SUM(pages_read), 0) FROM reading_sessions "
            "WHERE ended_at IS NOT NULL"
        ).fetchone()[0]

        # Total time in minutes
        total_minutes = conn.execute("""
            SELECT COALESCE(SUM(
                CAST((julianday(ended_at) - julianday(started_at))
                * 24 * 60 AS INTEGER)
            ), 0)
            FROM reading_sessions
            WHERE ended_at IS NOT NULL
        """).fetchone()[0]

        format_breakdown = conn.execute(
            "SELECT format, COUNT(*) as count FROM books "
            "WHERE status='ok' GROUP BY format ORDER BY count DESC"
        ).fetchall()

        type_breakdown = conn.execute(
            "SELECT book_type, COUNT(*) as count FROM books "
            "WHERE status='ok' GROUP BY book_type ORDER BY count DESC"
        ).fetchall()

        tag_breakdown = conn.execute("""
            SELECT t.name, t.color, COUNT(bt.book_id) as count
            FROM tags t
            JOIN book_tags bt ON bt.tag_id = t.id
            GROUP BY t.id ORDER BY count DESC LIMIT 10
        """).fetchall()

        top_authors = conn.execute(
            "SELECT author, COUNT(*) as count FROM books "
            "WHERE status='ok' AND author IS NOT NULL "
            "AND author != 'Unknown' "
            "GROUP BY author ORDER BY count DESC LIMIT 5"
        ).fetchall()

        conn.close()

        return {
            "total_books":       total_books,
            "completed":         completed,
            "in_progress":       in_progress,
            "total_pages":       total_pages,
            "total_minutes":     total_minutes,
            "format_breakdown":  [dict(r) for r in format_breakdown],
            "type_breakdown":    [dict(r) for r in type_breakdown],
            "tag_breakdown":     [dict(r) for r in tag_breakdown],
            "top_authors":       [dict(r) for r in top_authors],
        }

    def get_daily_pages(self, days: int = 30) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(f"""
            SELECT
                DATE(started_at) as date,
                SUM(pages_read)  as pages
            FROM reading_sessions
            WHERE ended_at IS NOT NULL
              AND started_at >= DATE('now', '-{days} days')
            GROUP BY DATE(started_at)
            ORDER BY date ASC
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_streak(self) -> int:
        """Current consecutive reading streak in days."""
        conn  = get_connection()
        rows  = conn.execute("""
            SELECT DISTINCT DATE(started_at) as date
            FROM reading_sessions
            WHERE ended_at IS NOT NULL
            ORDER BY date DESC
        """).fetchall()
        conn.close()

        if not rows:
            return 0

        from datetime import date, timedelta
        dates  = [row["date"] for row in rows]
        today  = date.today().isoformat()
        streak = 0

        # Allow today or yesterday as start of streak
        check = date.today()
        if dates[0] not in (today, (date.today() - timedelta(1)).isoformat()):
            return 0

        for d in dates:
            if d == check.isoformat():
                streak += 1
                check  -= timedelta(days=1)
            else:
                break

        return streak

    def get_most_active_day(self) -> str:
        conn = get_connection()
        row  = conn.execute("""
            SELECT
                CASE CAST(strftime('%w', started_at) AS INTEGER)
                    WHEN 0 THEN 'Sunday'
                    WHEN 1 THEN 'Monday'
                    WHEN 2 THEN 'Tuesday'
                    WHEN 3 THEN 'Wednesday'
                    WHEN 4 THEN 'Thursday'
                    WHEN 5 THEN 'Friday'
                    WHEN 6 THEN 'Saturday'
                END as day_name,
                COUNT(*) as count
            FROM reading_sessions
            WHERE ended_at IS NOT NULL
            GROUP BY day_name
            ORDER BY count DESC
            LIMIT 1
        """).fetchone()
        conn.close()
        return row["day_name"] if row else "N/A"


class ArtRepository:

    def get_all(self) -> list:
        conn = get_connection()
        rows = conn.execute("SELECT * FROM art_creations ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def add(self, title: str, description: str, src_image_path: str) -> str:
        import uuid
        import shutil
        from pathlib import Path
        
        art_id = str(uuid.uuid4())
        
        # Determine target path inside ~/.vedh/art
        art_dir = Path.home() / ".vedh" / "art"
        art_dir.mkdir(parents=True, exist_ok=True)
        
        suffix = Path(src_image_path).suffix or ".png"
        target_filename = f"{art_id}{suffix}"
        target_path = art_dir / target_filename
        
        # Copy file
        shutil.copy2(src_image_path, target_path)
        
        conn = get_connection()
        with conn:
            conn.execute("""
                INSERT INTO art_creations (id, title, description, image_path)
                VALUES (?, ?, ?, ?)
            """, (art_id, title, description, str(target_path)))
        conn.close()
        
        return art_id

    def delete(self, art_id: str):
        from pathlib import Path
        
        conn = get_connection()
        row = conn.execute("SELECT image_path FROM art_creations WHERE id = ?", (art_id,)).fetchone()
        
        if row:
            image_path = Path(row["image_path"])
            if image_path.exists():
                try:
                    image_path.unlink()
                except Exception:
                    pass
                    
            with conn:
                conn.execute("DELETE FROM art_creations WHERE id = ?", (art_id,))
        conn.close()