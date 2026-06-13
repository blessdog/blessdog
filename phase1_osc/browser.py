"""Browser client — search and load devices from Ableton's browser."""

from __future__ import annotations

from dataclasses import dataclass

from .connection import AbletonOSCConnection
from .errors import BrowserError, LoadError


@dataclass
class BrowserItem:
    name: str
    uri: str
    is_loadable: bool
    child_count: int


class Browser:
    def __init__(self, conn: AbletonOSCConnection):
        self._conn = conn

    def categories(self) -> dict[str, int]:
        """List browser categories and their child counts."""
        result = self._conn.query("/live/browser/categories")
        cats = {}
        for i in range(0, len(result), 2):
            cats[str(result[i])] = int(result[i + 1])
        return cats

    def search(self, category: str, query: str, max_results: int = 20) -> list[BrowserItem]:
        """Search within a category for items matching query."""
        result = self._conn.query("/live/browser/search", category, query, max_results)
        if len(result) == 1 and result[0] == "no_results":
            return []
        if len(result) >= 2 and result[0] == "error":
            raise BrowserError(str(result[1]))
        return self._parse_items(result)

    def list_children(self, category: str, *path: str) -> list[BrowserItem]:
        """List children at a browser path."""
        result = self._conn.query("/live/browser/list_children", category, *path)
        if len(result) == 1 and result[0] == "empty":
            return []
        if len(result) >= 2 and result[0] == "error":
            raise BrowserError(str(result[1]))
        return self._parse_items(result)

    def load_by_name(self, category: str, name: str) -> tuple[bool, str]:
        """Search and load the first match. Returns (success, name_or_error)."""
        result = self._conn.query("/live/browser/load_by_name", category, name)
        status = str(result[0])
        detail = str(result[1]) if len(result) > 1 else ""
        if status == "loaded":
            return True, detail
        elif status == "not_found":
            return False, detail
        else:
            raise LoadError(detail)

    def load_by_uri(self, uri: str) -> bool:
        """Load a browser item by its exact URI."""
        result = self._conn.query("/live/browser/load_by_uri", uri)
        status = str(result[0])
        if status == "loaded":
            return True
        elif status == "not_found":
            return False
        else:
            raise LoadError(str(result[1]) if len(result) > 1 else "unknown error")

    def load_by_path(self, category: str, *path: str) -> bool:
        """Navigate an exact path and load the item."""
        result = self._conn.query("/live/browser/load_by_path", category, *path)
        status = str(result[0])
        if status == "loaded":
            return True
        elif status == "error":
            raise LoadError(str(result[1]) if len(result) > 1 else "unknown error")
        return False

    @staticmethod
    def _parse_items(result: tuple) -> list[BrowserItem]:
        """Parse flat OSC tuple into BrowserItem list (4 values per item)."""
        items = []
        for i in range(0, len(result), 4):
            if i + 3 >= len(result):
                break
            items.append(BrowserItem(
                name=str(result[i]),
                uri=str(result[i + 1]),
                is_loadable=bool(result[i + 2]),
                child_count=int(result[i + 3]),
            ))
        return items
