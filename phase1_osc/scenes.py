"""Scene management — fire, create, delete, duplicate."""

from __future__ import annotations

from .connection import AbletonOSCConnection
from .errors import SceneNotFound


class Scenes:
    def __init__(self, conn: AbletonOSCConnection):
        self._conn = conn

    def count(self) -> int:
        result = self._conn.query("/live/song/get/num_scenes")
        return int(result[0])

    def get_names(self) -> list[str]:
        """Return scene names. AbletonOSC has no bulk scene-name endpoint,
        so we generate numbered names from the scene count."""
        num = self.count()
        return [f"Scene {i + 1}" for i in range(num)]

    def fire(self, index: int) -> None:
        self._validate_index(index)
        self._conn.send("/live/scene/fire", index)

    def create(self, index: int = -1) -> None:
        self._conn.send("/live/song/create_scene", index)

    def delete(self, index: int) -> None:
        self._validate_index(index)
        self._conn.send("/live/song/delete_scene", index)

    def duplicate(self, index: int) -> None:
        self._validate_index(index)
        self._conn.send("/live/song/duplicate_scene", index)

    def _validate_index(self, index: int) -> None:
        num = self.count()
        if index < 0 or index >= num:
            raise SceneNotFound(f"Scene {index} not found (have {num} scenes)")
