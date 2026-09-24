class StudioError(Exception):
    """A failure the page can explain to the user in one line."""


class InvalidJob(StudioError, ValueError):
    """The form asked for something the backend cannot take."""


class UnsupportedMode(InvalidJob):
    """The active backend declares no such mode."""


class MissingPrompt(StudioError):
    """The run has nothing to make. The mode words the message."""


class UnreadableImage(StudioError):
    """A reference image the server could not decode."""


class ReferenceExpired(StudioError):
    """A batch came back for a reference the server no longer holds."""


class Cancelled(StudioError):
    """The run stopped because the page asked it to."""


class BackendBusy(StudioError):
    """A run or a switch was asked for while a run is in flight."""


class UnknownBackend(StudioError):
    """No backend is registered under that id."""


class BackendChanged(StudioError):
    """The page was built for a backend that is no longer the active one."""
