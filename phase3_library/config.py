"""Library configuration — scan paths, DB location, skip patterns."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


_DEFAULT_SCAN_PATHS = [
    "/Volumes/NI Libraries/",
    "~/Desktop/Manual Library/Music/",
    "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/",
    "/Library/Application Support/Native Instruments/",
    "~/Library/Application Support/Native Instruments/",
]

_DEFAULT_SKIP_PATTERNS = [
    ".previews",
    "__MACOSX",
    ".DS_Store",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
]

_CONFIG_DIR = Path("~/.blessdog").expanduser()


@dataclass
class LibraryConfig:
    scan_paths: list[str] = field(default_factory=list)
    db_path: str = str(_CONFIG_DIR / "library.db")
    skip_patterns: list[str] = field(default_factory=lambda: list(_DEFAULT_SKIP_PATTERNS))

    @classmethod
    def default(cls) -> LibraryConfig:
        """Auto-detect which scan paths actually exist."""
        paths = []
        for p in _DEFAULT_SCAN_PATHS:
            expanded = os.path.expanduser(p)
            if os.path.isdir(expanded):
                paths.append(expanded)
        return cls(scan_paths=paths)

    def save(self, path: str | Path | None = None) -> None:
        """Write config to JSON file."""
        dest = Path(path) if path else _CONFIG_DIR / "config.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({
            "scan_paths": self.scan_paths,
            "db_path": self.db_path,
            "skip_patterns": self.skip_patterns,
        }, indent=2))

    @classmethod
    def load(cls, path: str | Path | None = None) -> LibraryConfig:
        """Load config from JSON file, falling back to defaults."""
        src = Path(path) if path else _CONFIG_DIR / "config.json"
        if not src.exists():
            return cls.default()
        data = json.loads(src.read_text())
        return cls(
            scan_paths=data.get("scan_paths", []),
            db_path=data.get("db_path", str(_CONFIG_DIR / "library.db")),
            skip_patterns=data.get("skip_patterns", list(_DEFAULT_SKIP_PATTERNS)),
        )
