"""Custom exceptions for BlessDog OSC bridge."""


class BlessDogError(Exception):
    """Base exception for all BlessDog errors."""


class ConnectionError(BlessDogError):
    """Failed to connect to Ableton Live."""


class QueryTimeout(BlessDogError):
    """OSC query did not receive a response in time."""


class TrackNotFound(BlessDogError):
    """Referenced track index does not exist."""


class ClipNotFound(BlessDogError):
    """Referenced clip slot does not exist or is empty."""


class DeviceNotFound(BlessDogError):
    """Referenced device index does not exist."""


class SceneNotFound(BlessDogError):
    """Referenced scene index does not exist."""
