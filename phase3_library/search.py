"""Search API — high-level wrapper combining DB queries for MCP tool responses."""

from __future__ import annotations

import sys
import time
from typing import Any

from .config import LibraryConfig
from .db import LibraryDB
from .metadata import extract_metadata
from .scanner import scan


class LibrarySearch:
    """Facade for library search operations."""

    def __init__(self, db: LibraryDB):
        self.db = db

    def search(
        self,
        query: str,
        file_type: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text search across the indexed library."""
        results = self.db.search(query, file_type=file_type, category=category, limit=limit)
        # Slim down results for MCP response
        return [_slim(r) for r in results]

    def stats(self) -> dict[str, Any]:
        """Library summary statistics."""
        return self.db.stats()

    def browse(
        self,
        category: str | None = None,
        library_source: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Browse by category or library source."""
        results = self.db.browse(category=category, library_source=library_source, limit=limit)
        return [_slim(r) for r in results]

    def duplicates(self, limit: int = 50) -> dict[str, Any]:
        """Duplicate report with top offenders."""
        report = self.db.duplicate_report()
        report["top_duplicates"] = self.db.find_duplicates(limit=limit)
        return report

    def reindex(self, config: LibraryConfig) -> dict[str, int]:
        """Run an incremental reindex of all configured paths."""
        indexed = 0
        skipped = 0
        errors = 0
        batch = 0

        t0 = time.time()

        for entry in scan(config):
            if self.db.needs_update(entry.path, entry.mtime, entry.size):
                try:
                    metadata = extract_metadata(entry.path, entry.extension)
                    self.db.upsert(entry, metadata)
                    indexed += 1
                except Exception:
                    errors += 1
            else:
                skipped += 1

            batch += 1
            if batch % 1000 == 0:
                self.db.commit()

        self.db.commit()
        elapsed = round(time.time() - t0, 1)

        return {
            "indexed": indexed,
            "skipped": skipped,
            "errors": errors,
            "elapsed_secs": elapsed,
        }


def _slim(row: dict[str, Any]) -> dict[str, Any]:
    """Slim a full DB row down to the fields useful for MCP responses."""
    result = {
        "name": row["name"],
        "path": row["path"],
        "file_type": row["file_type"],
        "category": row["category"],
        "library_source": row["library_source"],
        "library_name": row["library_name"],
    }
    # Include audio details if present
    if row.get("duration_secs"):
        result["duration_secs"] = row["duration_secs"]
    if row.get("sample_rate"):
        result["sample_rate"] = row["sample_rate"]
    # Include device class if present
    if row.get("device_class"):
        result["device_class"] = row["device_class"]
    # Include NI metadata if present
    if row.get("nksf_author"):
        result["nksf_author"] = row["nksf_author"]
    if row.get("nksf_types"):
        result["nksf_types"] = row["nksf_types"]
    return result


# ── CLI entry point ────────────────────────────────────────────────────

def main() -> None:
    """Run a full reindex from the command line."""
    config = LibraryConfig.default()
    if not config.scan_paths:
        print("No scan paths found. Check that library drives are mounted.")
        sys.exit(1)

    print(f"Scan paths: {config.scan_paths}")
    print(f"Database: {config.db_path}")

    db = LibraryDB(config.db_path)
    search = LibrarySearch(db)

    print("Indexing...")
    result = search.reindex(config)
    print(f"Done: {result}")

    stats = search.stats()
    print(f"Total files: {stats['total_files']}")
    print(f"Total size: {stats['total_size_gb']} GB")
    print(f"By type: {stats['by_type']}")
    print(f"By source: {stats['by_source']}")

    db.close()


if __name__ == "__main__":
    main()
