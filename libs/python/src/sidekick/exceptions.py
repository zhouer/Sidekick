"""Custom application-level exceptions for the Sidekick Python library.

This module defines specific error types that users of the Sidekick library
might encounter, particularly those related to establishing and maintaining
a connection to the Sidekick service (which includes the UI panel and its
communication layer).

These exceptions provide more context than generic Python errors and can help
users understand and potentially handle different failure scenarios when
interacting with Sidekick. They may wrap or be triggered by lower-level
exceptions from the `sidekick.core` package.
"""

from typing import Optional, Any

# Import core exceptions to potentially wrap them or for type checking if needed,
# though direct wrapping might happen in ConnectionService.
# from .core.exceptions import CoreConnectionError # Example if needed

class SidekickError(Exception):
    """Base class for all application-level errors specific to the Sidekick library.

    Catching this exception can be a way to handle any error explicitly raised
    by the Sidekick library itself, distinguishing it from general Python errors
    or errors from other libraries.
    """
    pass


class SidekickConnectionError(SidekickError):
    """Base error for all Sidekick connection-related problems at the application level.

    Catch this exception type if you want to handle any issue related to
    establishing or maintaining the connection to the full Sidekick service,
    including communication with the UI panel.

    Example:
        >>> import sidekick
        >>> try:
        ...     console = sidekick.Console() # Connection to Sidekick service happens here
        ...     console.print("Connected to Sidekick!")
        ... except sidekick.SidekickConnectionError as e:
        ...     print(f"Could not use Sidekick: {e}")
    """
    def __init__(self, message: str, original_exception: Optional[BaseException] = None):
        super().__init__(message)
        self.original_exception = original_exception

    def __str__(self) -> str:
        """Provide a more informative string representation."""
        parts = [super().__str__()]
        if self.original_exception: # pragma: no cover
            # This part is more for debugging, might not always be user-facing nicely
            parts.append(
                f"Underlying issue: {type(self.original_exception).__name__}: {self.original_exception}"
            )
        return ". ".join(parts)


class SidekickConnectionRefusedError(SidekickConnectionError):
    """Raised when the library fails to connect to the Sidekick service.

    This usually means the Sidekick WebSocket server (typically run by the
    VS Code extension) wasn't running or couldn't be reached at the
    configured URL (e.g., "ws://localhost:5163" by default), or the
    underlying connection attempt was actively refused.

    Common Causes:
    1.  The Sidekick panel isn't open and active in VS Code.
    2.  The Sidekick VS Code extension isn't running correctly or has
        encountered an error starting its server.
    3.  The WebSocket server couldn't start (e.g., the port is already in use).
        Check VS Code's "Sidekick Server" output channel for details.
    4.  A firewall is blocking the connection.
    5.  An incorrect URL was configured via `sidekick.set_url()`.

    Attributes:
        url (Optional[str]): The WebSocket URL that the connection attempt was made to, if available.
    """
    def __init__(self, message: str, url: Optional[str] = None, original_exception: Optional[BaseException] = None):
        super().__init__(message, original_exception=original_exception)
        self.url = url

    # __str__ is inherited and will include original_exception if present.


class SidekickTimeoutError(SidekickConnectionError):
    """Raised when a Sidekick operation times out at the application level.

    A common scenario for this error is when the connection to the Sidekick
    server (WebSocket) succeeds, but the Sidekick UI panel itself doesn't
    respond by announcing its readiness (e.g., via a "system/announce" message)
    within an expected timeframe.

    Common Causes:
    1.  The Sidekick panel is open in VS Code, but its web content (HTML/JS)
        hasn't finished loading or initializing (e.g., due to slow system
        performance or an internal UI error).
    2.  An error within the Sidekick UI panel's JavaScript code is preventing
        it from signaling readiness. Check the Webview Developer Tools in VS Code
        (Command Palette -> "Developer: Open Webview Developer Tools") for errors.

    Attributes:
        timeout_seconds (Optional[float]): The duration of the timeout in seconds, if specified.
    """
    def __init__(self, message: str, timeout_seconds: Optional[float] = None, original_exception: Optional[BaseException] = None):
        super().__init__(message, original_exception=original_exception)
        self.timeout_seconds = timeout_seconds


class SidekickDisconnectedError(SidekickConnectionError):
    """Raised when the connection to the Sidekick service is lost *after* it
    was successfully established and active.

    This indicates that communication was previously working, but the connection
    broke unexpectedly. This can happen if you try to send a command or if the
    background communication layer detects the disconnection.

    Common Causes:
    1.  The Sidekick panel was closed in VS Code while your script was running.
    2.  The Sidekick VS Code extension crashed, was disabled, or VS Code itself was closed.
    3.  A network interruption occurred (less common for local connections).
    4.  An unrecoverable internal error occurred in the communication channel.

    **Important:** The library will **not** automatically try to reconnect if this
    error occurs.

    Attributes:
        reason (Optional[str]): A short description of why the disconnection occurred
                                or was detected, if available.
    """
    def __init__(self, message: str = "Connection to the Sidekick service was lost.", reason: Optional[str] = None, original_exception: Optional[BaseException] = None):
        full_message = message
        if reason:
            full_message += f" Reason: {reason}"
        super().__init__(full_message, original_exception=original_exception)
        self.reason = reason
