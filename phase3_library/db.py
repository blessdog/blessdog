"""SQLite database with FTS5 full-text search for the library index."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from .scanner import FileEntry

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    extension TEXT NOT NULL,
    size INTEGER,
    mtime REAL,
    file_type TEXT,
    category TEXT,
    library_source TEXT,
    library_name TEXT,
    sample_rate INTEGER,
    bit_depth INTEGER,
    channels INTEGER,
    duration_secs REAL,
    device_class TEXT,
    nksf_author TEXT,
    nksf_vendor TEXT,
    nksf_bankchain TEXT,
    nksf_types TEXT,
    nksf_characters TEXT,
    fingerprint TEXT,
    indexed_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fingerprint ON files(fingerprint);
CREATE INDEX IF NOT EXISTS idx_file_type ON files(file_type);
CREATE INDEX IF NOT EXISTS idx_category ON files(category);
CREATE INDEX IF NOT EXISTS idx_library_source ON files(library_source);
CREATE INDEX IF NOT EXISTS idx_library_name ON files(library_name);
"""

_FTS_SCHEMA = """\
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    name, category, library_name, device_class,
    nksf_bankchain, nksf_types, nksf_characters,
    content=files, content_rowid=id
);
"""

_FTS_INSERT = """\
INSERT INTO files_fts(rowid, name, category, library_name, device_class,
                      nksf_bankchain, nksf_types, nksf_characters)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_FTS_DELETE = """\
INSERT INTO files_fts(files_fts, rowid, name, category, library_name,
                      device_class, nksf_bankchain, nksf_types, nksf_characters)
VALUES ('delete', ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _fingerprint(name: str, extension: str, size: int) -> str:
    """Generate a fingerprint for duplicate detection."""
    key = f"{name}{extension}{size}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _serialize_list(value: Any) -> str | None:
    """Serialize a list to JSON string for storage."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return json.dumps(value)
    if isinstance(value, str):
        return value
    return str(value)


class LibraryDB:
    """SQLite database for the indexed music library."""

    def __init__(self, db_path: str = ":memory:"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(_SCHEMA)
        # FTS5 needs separate creation (can't be in executescript with IF NOT EXISTS
        # for virtual tables in all SQLite versions)
        try:
            self.conn.execute(_FTS_SCHEMA)
        except sqlite3.OperationalError:
            pass  # Already exists
        self.conn.commit()

    def needs_update(self, path: str, mtime: float, size: int) -> bool:
        """Check if a file needs re-indexing based on mtime and size."""
        row = self.conn.execute(
            "SELECT mtime, size FROM files WHERE path = ?", (path,)
        ).fetchone()
        if row is None:
            return True
        return row["mtime"] != mtime or row["size"] != size

    def upsert(self, entry: FileEntry, metadata: dict[str, Any]) -> None:
        """Insert or update a file entry with its metadata."""
        fp = _fingerprint(entry.name, entry.extension, entry.size)
        now = time.time()

        # Prepare values
        nksf_bankchain = _serialize_list(metadata.get("nksf_bankchain"))
        nksf_types = _serialize_list(metadata.get("nksf_types"))
        nksf_characters = _serialize_list(metadata.get("nksf_characters"))

        # Check existing
        existing = self.conn.execute(
            "SELECT id, name, category, library_name, device_class, "
            "nksf_bankchain, nksf_types, nksf_characters FROM files WHERE path = ?",
            (entry.path,)
        ).fetchone()

        if existing:
            # Delete old FTS entry
            self.conn.execute(
                _FTS_DELETE,
                (existing["id"], existing["name"], existing["category"],
                 existing["library_name"], existing["device_class"],
                 existing["nksf_bankchain"], existing["nksf_types"],
                 existing["nksf_characters"]),
            )

            # Update row
            self.conn.execute("""\
                UPDATE files SET
                    name=?, extension=?, size=?, mtime=?, file_type=?,
                    category=?, library_source=?, library_name=?,
                    sample_rate=?, bit_depth=?, channels=?, duration_secs=?,
                    device_class=?, nksf_author=?, nksf_vendor=?,
                    nksf_bankchain=?, nksf_types=?, nksf_characters=?,
                    fingerprint=?, indexed_at=?
                WHERE path=?
            """, (
                entry.name, entry.extension, entry.size, entry.mtime,
                entry.file_type, entry.category, entry.library_source,
                entry.library_name,
                metadata.get("sample_rate"), metadata.get("bit_depth"),
                metadata.get("channels"), metadata.get("duration_secs"),
                metadata.get("device_class"),
                metadata.get("nksf_author"), metadata.get("nksf_vendor"),
                nksf_bankchain, nksf_types, nksf_characters,
                fp, now, entry.path,
            ))
            row_id = existing["id"]
        else:
            cursor = self.conn.execute("""\
                INSERT INTO files (
                    path, name, extension, size, mtime, file_type,
                    category, library_source, library_name,
                    sample_rate, bit_depth, channels, duration_secs,
                    device_class, nksf_author, nksf_vendor,
                    nksf_bankchain, nksf_types, nksf_characters,
                    fingerprint, indexed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                entry.path, entry.name, entry.extension, entry.size,
                entry.mtime, entry.file_type, entry.category,
                entry.library_source, entry.library_name,
                metadata.get("sample_rate"), metadata.get("bit_depth"),
                metadata.get("channels"), metadata.get("duration_secs"),
                metadata.get("device_class"),
                metadata.get("nksf_author"), metadata.get("nksf_vendor"),
                nksf_bankchain, nksf_types, nksf_characters,
                fp, now,
            ))
            row_id = cursor.lastrowid

        # Insert FTS entry
        device_class = metadata.get("device_class") or entry.category
        self.conn.execute(
            _FTS_INSERT,
            (row_id, entry.name, entry.category, entry.library_name,
             device_class, nksf_bankchain, nksf_types, nksf_characters),
        )

    def commit(self) -> None:
        self.conn.commit()

    def search(
        self,
        query: str,
        file_type: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text search across indexed files."""
        # Build FTS5 query — quote terms for safety
        terms = query.strip().split()
        fts_query = " OR ".join(f'"{t}"' for t in terms if t)
        if not fts_query:
            return []

        sql = """\
            SELECT f.* FROM files f
            JOIN files_fts fts ON f.id = fts.rowid
            WHERE files_fts MATCH ?
        """
        params: list[Any] = [fts_query]

        if file_type:
            sql += " AND f.file_type = ?"
            params.append(file_type)
        if category:
            sql += " AND f.category LIKE ?"
            params.append(f"%{category}%")

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Summary statistics of the indexed library."""
        total = self.conn.execute("SELECT COUNT(*) as c FROM files").fetchone()["c"]

        by_type = self.conn.execute(
            "SELECT file_type, COUNT(*) as c FROM files GROUP BY file_type ORDER BY c DESC"
        ).fetchall()

        by_source = self.conn.execute(
            "SELECT library_source, COUNT(*) as c FROM files GROUP BY library_source ORDER BY c DESC"
        ).fetchall()

        top_libraries = self.conn.execute(
            "SELECT library_name, COUNT(*) as c FROM files GROUP BY library_name ORDER BY c DESC LIMIT 20"
        ).fetchall()

        top_categories = self.conn.execute(
            "SELECT category, COUNT(*) as c FROM files GROUP BY category ORDER BY c DESC LIMIT 20"
        ).fetchall()

        total_size = self.conn.execute(
            "SELECT COALESCE(SUM(size), 0) as s FROM files"
        ).fetchone()["s"]

        return {
            "total_files": total,
            "total_size_gb": round(total_size / (1024 ** 3), 2),
            "by_type": {r["file_type"]: r["c"] for r in by_type},
            "by_source": {r["library_source"]: r["c"] for r in by_source},
            "top_libraries": {r["library_name"]: r["c"] for r in top_libraries},
            "top_categories": {r["category"]: r["c"] for r in top_categories},
        }

    def browse(
        self,
        category: str | None = None,
        library_source: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Browse files by category or library source."""
        sql = "SELECT * FROM files WHERE 1=1"
        params: list[Any] = []

        if category:
            sql += " AND category LIKE ?"
            params.append(f"%{category}%")
        if library_source:
            sql += " AND library_source = ?"
            params.append(library_source)

        sql += " ORDER BY library_name, name LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def find_duplicates(self, limit: int = 50) -> list[dict[str, Any]]:
        """Find duplicate files based on fingerprint (name + ext + size)."""
        rows = self.conn.execute("""\
            SELECT fingerprint, name, extension, size, COUNT(*) as count
            FROM files
            GROUP BY fingerprint
            HAVING count > 1
            ORDER BY size * (count - 1) DESC
            LIMIT ?
        """, (limit,)).fetchall()

        results = []
        for r in rows:
            paths = self.conn.execute(
                "SELECT path, library_source FROM files WHERE fingerprint = ?",
                (r["fingerprint"],)
            ).fetchall()
            results.append({
                "name": r["name"],
                "extension": r["extension"],
                "size": r["size"],
                "count": r["count"],
                "wasted_bytes": r["size"] * (r["count"] - 1),
                "locations": [{"path": p["path"], "source": p["library_source"]} for p in paths],
            })

        return results

    def duplicate_report(self) -> dict[str, Any]:
        """Summary of all duplicate files."""
        row = self.conn.execute("""\
            SELECT COUNT(*) as groups,
                   SUM(size * (count - 1)) as wasted
            FROM (
                SELECT fingerprint, size, COUNT(*) as count
                FROM files
                GROUP BY fingerprint
                HAVING count > 1
            )
        """).fetchone()

        return {
            "duplicate_groups": row["groups"] or 0,
            "total_wasted_bytes": row["wasted"] or 0,
            "total_wasted_gb": round((row["wasted"] or 0) / (1024 ** 3), 2),
        }

    def prune_missing(self) -> int:
        """Remove entries for files that no longer exist on disk."""
        paths = self.conn.execute("SELECT id, path FROM files").fetchall()
        removed = 0
        for row in paths:
            if not os.path.exists(row["path"]):
                self.conn.execute("DELETE FROM files WHERE id = ?", (row["id"],))
                removed += 1
        if removed:
            self.conn.commit()
        return removed

    def close(self) -> None:
        self.conn.close()
