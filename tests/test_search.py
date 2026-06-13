"""Tests for phase3_library.db and phase3_library.search — DB, FTS5, search API."""

import json

import pytest

from phase3_library.db import LibraryDB, _fingerprint
from phase3_library.scanner import FileEntry
from phase3_library.search import LibrarySearch


@pytest.fixture
def db():
    """In-memory SQLite database."""
    d = LibraryDB(":memory:")
    yield d
    d.close()


@pytest.fixture
def sample_entries():
    """Sample FileEntry objects for testing."""
    return [
        FileEntry(
            path="/lib/kicks/hard_808.wav",
            name="hard_808",
            extension=".wav",
            size=50000,
            mtime=1700000000.0,
            file_type="sample",
            category="drums/kicks",
            library_source="drum_kit",
            library_name="808 Mafia",
        ),
        FileEntry(
            path="/lib/kicks/soft_kick.wav",
            name="soft_kick",
            extension=".wav",
            size=40000,
            mtime=1700000001.0,
            file_type="sample",
            category="drums/kicks",
            library_source="drum_kit",
            library_name="808 Mafia",
        ),
        FileEntry(
            path="/lib/bass/deep_sub.wav",
            name="deep_sub",
            extension=".wav",
            size=80000,
            mtime=1700000002.0,
            file_type="sample",
            category="bass",
            library_source="user_collection",
            library_name="My Samples",
        ),
        FileEntry(
            path="/lib/presets/warm_pad.adg",
            name="warm_pad",
            extension=".adg",
            size=12000,
            mtime=1700000003.0,
            file_type="instrument",
            category="instruments/wavetable",
            library_source="ableton_factory",
            library_name="Wavetable",
        ),
        FileEntry(
            path="/lib/ni/strings_sustain.nksf",
            name="strings_sustain",
            extension=".nksf",
            size=5000,
            mtime=1700000004.0,
            file_type="preset",
            category="strings",
            library_source="ni_library",
            library_name="Session Strings 2",
        ),
        # Duplicate of hard_808 in different location
        FileEntry(
            path="/other/kicks/hard_808.wav",
            name="hard_808",
            extension=".wav",
            size=50000,
            mtime=1700000005.0,
            file_type="sample",
            category="drums/kicks",
            library_source="user_collection",
            library_name="Backup",
        ),
    ]


def _insert_all(db, entries, metadata=None):
    """Helper to insert all entries with optional metadata."""
    for entry in entries:
        meta = (metadata or {}).get(entry.path, {})
        db.upsert(entry, meta)
    db.commit()


class TestLibraryDB:
    def test_upsert_and_search(self, db, sample_entries):
        _insert_all(db, sample_entries)
        results = db.search("808")
        assert len(results) >= 1
        names = {r["name"] for r in results}
        assert "hard_808" in names

    def test_search_by_file_type(self, db, sample_entries):
        _insert_all(db, sample_entries)
        results = db.search("808", file_type="sample")
        assert all(r["file_type"] == "sample" for r in results)

    def test_search_by_category(self, db, sample_entries):
        _insert_all(db, sample_entries)
        results = db.search("808", category="kicks")
        assert all("kicks" in r["category"] for r in results)

    def test_search_no_results(self, db, sample_entries):
        _insert_all(db, sample_entries)
        results = db.search("xyznonexistent")
        assert results == []

    def test_needs_update_new_file(self, db):
        assert db.needs_update("/new/file.wav", 1700000000.0, 100) is True

    def test_needs_update_unchanged(self, db, sample_entries):
        _insert_all(db, sample_entries[:1])
        entry = sample_entries[0]
        assert db.needs_update(entry.path, entry.mtime, entry.size) is False

    def test_needs_update_modified(self, db, sample_entries):
        _insert_all(db, sample_entries[:1])
        entry = sample_entries[0]
        assert db.needs_update(entry.path, entry.mtime + 1, entry.size) is True
        assert db.needs_update(entry.path, entry.mtime, entry.size + 1) is True

    def test_upsert_updates_existing(self, db, sample_entries):
        entry = sample_entries[0]
        db.upsert(entry, {})
        db.commit()

        # Modify and re-upsert
        updated = FileEntry(
            path=entry.path,
            name=entry.name,
            extension=entry.extension,
            size=99999,
            mtime=entry.mtime + 100,
            file_type=entry.file_type,
            category=entry.category,
            library_source=entry.library_source,
            library_name=entry.library_name,
        )
        db.upsert(updated, {"sample_rate": 44100})
        db.commit()

        # Should still be one row
        count = db.conn.execute("SELECT COUNT(*) as c FROM files WHERE path = ?", (entry.path,)).fetchone()["c"]
        assert count == 1

        row = db.conn.execute("SELECT size, sample_rate FROM files WHERE path = ?", (entry.path,)).fetchone()
        assert row["size"] == 99999
        assert row["sample_rate"] == 44100

    def test_stats(self, db, sample_entries):
        _insert_all(db, sample_entries)
        stats = db.stats()
        assert stats["total_files"] == 6
        assert "sample" in stats["by_type"]
        assert "drum_kit" in stats["by_source"]
        assert stats["total_size_gb"] >= 0

    def test_browse_by_category(self, db, sample_entries):
        _insert_all(db, sample_entries)
        results = db.browse(category="kicks")
        assert len(results) >= 2
        assert all("kicks" in r["category"] for r in results)

    def test_browse_by_source(self, db, sample_entries):
        _insert_all(db, sample_entries)
        results = db.browse(library_source="ni_library")
        assert len(results) >= 1
        assert all(r["library_source"] == "ni_library" for r in results)

    def test_find_duplicates(self, db, sample_entries):
        _insert_all(db, sample_entries)
        dupes = db.find_duplicates()
        # hard_808.wav exists in two locations with same size
        assert len(dupes) >= 1
        dupe_names = {d["name"] for d in dupes}
        assert "hard_808" in dupe_names

    def test_duplicate_report(self, db, sample_entries):
        _insert_all(db, sample_entries)
        report = db.duplicate_report()
        assert report["duplicate_groups"] >= 1
        assert report["total_wasted_bytes"] > 0

    def test_fingerprint(self):
        fp1 = _fingerprint("kick", ".wav", 1000)
        fp2 = _fingerprint("kick", ".wav", 1000)
        fp3 = _fingerprint("kick", ".wav", 2000)
        assert fp1 == fp2
        assert fp1 != fp3


class TestLibrarySearch:
    def test_search(self, db, sample_entries):
        _insert_all(db, sample_entries)
        ls = LibrarySearch(db)
        results = ls.search("808")
        assert len(results) >= 1
        # Results should be slimmed down
        assert "name" in results[0]
        assert "path" in results[0]

    def test_stats(self, db, sample_entries):
        _insert_all(db, sample_entries)
        ls = LibrarySearch(db)
        stats = ls.stats()
        assert stats["total_files"] == 6

    def test_browse(self, db, sample_entries):
        _insert_all(db, sample_entries)
        ls = LibrarySearch(db)
        results = ls.browse(category="kicks")
        assert len(results) >= 2

    def test_duplicates(self, db, sample_entries):
        _insert_all(db, sample_entries)
        ls = LibrarySearch(db)
        report = ls.duplicates()
        assert report["duplicate_groups"] >= 1
        assert "top_duplicates" in report

    def test_search_with_nksf_metadata(self, db, sample_entries):
        """NKSF metadata is searchable via FTS."""
        entry = sample_entries[4]  # strings_sustain.nksf
        db.upsert(entry, {
            "nksf_author": "Native Instruments",
            "nksf_types": json.dumps(["Strings", "Ensemble"]),
            "nksf_bankchain": json.dumps(["Session Strings 2", "Sustain"]),
        })
        db.commit()

        ls = LibrarySearch(db)
        results = ls.search("Strings Ensemble")
        assert len(results) >= 1

    def test_search_limit(self, db, sample_entries):
        _insert_all(db, sample_entries)
        ls = LibrarySearch(db)
        results = ls.search("808", limit=1)
        assert len(results) <= 1

    def test_search_empty_query(self, db, sample_entries):
        _insert_all(db, sample_entries)
        ls = LibrarySearch(db)
        results = ls.search("")
        assert results == []

    def test_search_multiple_terms(self, db, sample_entries):
        _insert_all(db, sample_entries)
        ls = LibrarySearch(db)
        results = ls.search("deep sub")
        names = {r["name"] for r in results}
        assert "deep_sub" in names
