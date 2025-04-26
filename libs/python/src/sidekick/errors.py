"""Custom exceptions for the Sidekick library.

This module defines specific error types for connection problems, making it easier
for users to catch and potentially handle different failure scenarios.
"""

class SidekickConnectionError(Exception):
    """Base error for all Sidekick connection-related problems.

    Catch this exception type if you want to handle any issue related to
    establishing or maintaining the connection to the Sidekick panel.

    Example:
        >>> try:
        ...     console = sidekick.Console() # Connection happens here
        ...     console.print("Connected!")
        ... except sidekick.SidekickConnectionError as e:
        ...     print(f"Could not connect to Sidekick: {e}")
    """
    pass

class SidekickConnectionRefusedError(SidekickConnectionError):
    """Raised when the library fails to connect to the Sidekick server initially.

    This usually means the Sidekick WebSocket server wasn't running or couldn't
    be reached at the configured URL (`ws://localhost:5163` by default).

    Common Causes:

    1. The Sidekick panel isn't open and active in VS Code.
    2. The Sidekick VS Code extension isn't running correctly or has encountered an error.
    3. The WebSocket server couldn't start (e.g., the port is already in use by another
       application). Check VS Code's "Sidekick Server" output channel for details.
    4. A firewall is blocking the connection between your script and VS Code.
    5. The URL was changed via `sidekick.set_url()` to an incorrect address.

    Attributes:
        url (str): The WebSocket URL that the connection attempt was made to.
        original_exception (Exception): The lower-level error that caused the failure
            (e.g., `ConnectionRefusedError` from the OS, `TimeoutError` from the
            `websocket` library).
    """
    def __init__(self, url: str, original_exception: Exception):
        self.url = url
        self.original_exception = original_exception
        # User-friendly error message suggesting common fixes.
        super().__init__(
            f"Failed to connect to Sidekick server at {url}. "
            f"Reason: {original_exception}. "
            f"Is the Sidekick panel open in VS Code? "
            f"Check the URL, potential port conflicts (default 5163), and firewall settings."
        )

class SidekickTimeoutError(SidekickConnectionError):
    """Raised when connection to the server succeeds, but the Sidekick UI panel doesn't respond.

    After successfully connecting to the WebSocket server (run by the VS Code extension),
    the library waits a short time (a few seconds) for the Sidekick UI panel itself
    (the web content inside the panel) to finish loading and send back a signal
    confirming it's ready to receive commands. If this signal doesn't arrive
    within the timeout period, this error is raised.

    Common Causes:

    1. The Sidekick panel is open in VS Code, but it hasn't finished loading its
       HTML/JavaScript content yet (e.g., due to slow system performance or
       network issues if loading remote resources, though usually local).
    2. There's an error within the Sidekick UI panel's JavaScript code preventing
       it from initializing correctly. Check the Webview Developer Tools in VS Code
       (Command Palette -> "Developer: Open Webview Developer Tools") for errors.

    Attributes:
        timeout (float): The number of seconds the library waited for the UI response.
    """
    def __init__(self, timeout: float):
        self.timeout = timeout
        # User-friendly message explaining the timeout.
        super().__init__(
            f"Connected to the Sidekick server, but timed out after {timeout:.1f} seconds "
            f"waiting for the Sidekick UI panel itself to signal it's ready. "
            f"Is the panel visible and fully loaded in VS Code? Check Webview Developer Tools for errors."
        )

class SidekickDisconnectedError(SidekickConnectionError):
    """Raised when the connection is lost *after* it was successfully established.

    This indicates that communication was working previously, but the connection
    broke unexpectedly. This can happen if you try to send a command or if the
    background listener thread detects the disconnection.

    Common Causes:

    1. The Sidekick panel was closed in VS Code while your script was still running.
    2. The Sidekick VS Code extension crashed, was disabled, or VS Code was closed.
    3. A network interruption occurred between the Python script and VS Code (less
       common for local connections but possible).
    4. An internal error occurred while trying to send or receive a message over
       the established connection.

    **Important:** The library will **not** automatically try to reconnect if this
    error occurs. Any further attempts to use Sidekick modules (like `grid.set_color()`)
    will also fail until the script is potentially restarted and a new connection
    is established.

    Attributes:
        reason (str): A short description of why the disconnection occurred or was detected.
    """
    def __init__(self, reason: str = "Connection lost"):
        self.reason = reason
        # User-friendly message explaining the disconnection.
        super().__init__(
            f"Sidekick connection lost: {reason}. "
            f"The connection was active but is now broken. "
            f"The library will not automatically reconnect."
        )