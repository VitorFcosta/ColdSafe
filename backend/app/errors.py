class DeviceNotFoundError(Exception):
    """Raised when a requested device is outside the single-device MVP."""


class DependencyUnavailableError(Exception):
    """Raised when required infrastructure cannot complete an operation."""
