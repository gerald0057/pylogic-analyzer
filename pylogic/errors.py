class PylogicError(Exception):
    """Base exception for pylogic."""
    pass


class ChannelNotFoundError(PylogicError):
    """Raised when a channel name is not found in the waveform."""
    pass


class DslFormatError(PylogicError):
    """Raised when a .dsl file has invalid format."""
    pass
