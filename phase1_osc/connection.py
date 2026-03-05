"""Core OSC connection layer for Ableton Live communication."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from .errors import ConnectionError, QueryTimeout

logger = logging.getLogger(__name__)

DEFAULT_SEND_PORT = 11000
DEFAULT_RECV_PORT = 11001
DEFAULT_HOST = "127.0.0.1"
DEFAULT_TIMEOUT = 5.0


class AbletonOSCConnection:
    """Bidirectional OSC connection to Ableton Live via AbletonOSC.

    Sends commands/queries to Ableton on port 11000 and receives responses
    on port 11001. Supports both request-response queries and persistent
    listener subscriptions.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        send_port: int = DEFAULT_SEND_PORT,
        recv_port: int = DEFAULT_RECV_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.host = host
        self.send_port = send_port
        self.recv_port = recv_port
        self.timeout = timeout

        self._client: SimpleUDPClient | None = None
        self._server: ThreadingOSCUDPServer | None = None
        self._server_thread: threading.Thread | None = None

        # Query correlation: address → (Event, result list)
        self._pending: dict[str, tuple[threading.Event, list]] = {}
        self._pending_lock = threading.Lock()

        # Persistent listeners: address → list of callbacks
        self._listeners: dict[str, list[Callable]] = {}
        self._listeners_lock = threading.Lock()

        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Establish connection to Ableton Live.

        Creates the UDP client, starts the response listener server,
        and verifies connectivity with a test query.
        """
        if self._connected:
            return

        self._client = SimpleUDPClient(self.host, self.send_port)

        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._handle_response)

        try:
            self._server = ThreadingOSCUDPServer(
                (self.host, self.recv_port), dispatcher
            )
        except OSError as e:
            raise ConnectionError(
                f"Could not bind to {self.host}:{self.recv_port} — {e}"
            ) from e

        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._server_thread.start()

        # Health check
        try:
            result = self.query("/live/test")
            logger.info("Connected to Ableton Live: %s", result)
            self._connected = True
        except QueryTimeout:
            self.disconnect()
            raise ConnectionError(
                "No response from Ableton Live. "
                "Is it running with AbletonOSC control surface enabled?"
            )

    def disconnect(self) -> None:
        """Shut down the connection."""
        if self._server:
            self._server.shutdown()
            self._server = None
        self._server_thread = None
        self._client = None
        self._connected = False

    def send(self, address: str, *args: Any) -> None:
        """Fire-and-forget OSC message."""
        if not self._client:
            raise ConnectionError("Not connected")
        logger.debug("SEND %s %s", address, args)
        self._client.send_message(address, list(args))

    def query(self, address: str, *args: Any, timeout: float | None = None) -> tuple:
        """Send an OSC message and wait for the response.

        Returns the response arguments as a tuple.
        """
        if not self._client:
            raise ConnectionError("Not connected")

        timeout = timeout or self.timeout
        event = threading.Event()
        result: list = []

        with self._pending_lock:
            self._pending[address] = (event, result)

        logger.debug("QUERY %s %s", address, args)
        self._client.send_message(address, list(args))

        if not event.wait(timeout):
            with self._pending_lock:
                self._pending.pop(address, None)
            raise QueryTimeout(f"No response for {address} within {timeout}s")

        with self._pending_lock:
            self._pending.pop(address, None)

        return tuple(result)

    def add_listener(self, address: str, callback: Callable) -> None:
        """Register a persistent callback for an OSC address."""
        with self._listeners_lock:
            self._listeners.setdefault(address, []).append(callback)

    def remove_listener(self, address: str, callback: Callable | None = None) -> None:
        """Remove a listener. If callback is None, removes all for that address."""
        with self._listeners_lock:
            if callback is None:
                self._listeners.pop(address, None)
            elif address in self._listeners:
                try:
                    self._listeners[address].remove(callback)
                except ValueError:
                    pass
                if not self._listeners[address]:
                    del self._listeners[address]

    def _handle_response(self, address: str, *args: Any) -> None:
        """Default dispatcher handler — routes to pending queries first,
        then to persistent listeners."""
        logger.debug("RECV %s %s", address, args)

        # Check pending queries first
        with self._pending_lock:
            pending = self._pending.get(address)
            if pending:
                event, result = pending
                result.extend(args)
                event.set()
                return

        # Then check persistent listeners
        with self._listeners_lock:
            listeners = self._listeners.get(address, [])
            for cb in listeners:
                try:
                    cb(address, *args)
                except Exception:
                    logger.exception("Listener error for %s", address)

    def __enter__(self) -> AbletonOSCConnection:
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disconnect()
