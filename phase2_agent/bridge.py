"""AbletonBridge — lazy-connect lifecycle manager.

Wraps the Phase 1 OSC connection and domain objects into a single
facade. Connection is deferred until the first tool call via
ensure_connected().
"""

from __future__ import annotations

from phase1_osc.browser import Browser
from phase1_osc.clips import Clips
from phase1_osc.connection import AbletonOSCConnection
from phase1_osc.devices import Devices
from phase1_osc.discovery import Discovery
from phase1_osc.scenes import Scenes
from phase1_osc.tracks import Tracks
from phase1_osc.transport import Transport
from phase1_osc.view import View


class AbletonBridge:
    """Single entry point to all Ableton Live functionality.

    Domain objects are instantiated eagerly (they're cheap — just store
    a reference to the connection). The actual OSC connection is
    established lazily on the first ensure_connected() call.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        send_port: int = 11000,
        recv_port: int = 11001,
        timeout: float = 5.0,
    ):
        self.conn = AbletonOSCConnection(
            host=host,
            send_port=send_port,
            recv_port=recv_port,
            timeout=timeout,
        )
        self.transport = Transport(self.conn)
        self.tracks = Tracks(self.conn)
        self.clips = Clips(self.conn)
        self.devices = Devices(self.conn)
        self.scenes = Scenes(self.conn)
        self.discovery = Discovery(self.conn)
        self.view = View(self.conn)
        self.browser = Browser(self.conn)

    @property
    def connected(self) -> bool:
        return self.conn.connected

    def ensure_connected(self) -> None:
        """Connect to Ableton Live if not already connected."""
        if not self.conn.connected:
            self.conn.connect()

    def disconnect(self) -> None:
        """Shut down the OSC connection."""
        self.conn.disconnect()
