"""Core exceptions for the Sidekick library's underlying infrastructure.

This module defines a hierarchy of custom exceptions that are used by the
core components of the Sidekick library, such as the TaskManager and
CommunicationManager.

These exceptions are intended to be relatively generic and focused on the
fundamental operations of these core components. Higher-level, application-specific
Sidekick exceptions (e.g., those related to UI interactions or specific
Sidekick features) may inherit from or wrap these core exceptions.
"""

from typing import Optional, Any

# --- Base Core Exception ---

class CoreBaseError(Exception):
    """Base class for all core errors within the Sidekick library infrastructure."""
    def __init__(self, message: str, original_exception: Optional[BaseException] = None):
        super().__init__(message)
        self.original_exception = original_exception

    def __str__(self) -> str:
        """Provide a more informative string representation."""
        parts = [super().__str__()]
        if self.original_exception:
            parts.append(f"Original Exception: {type(self.original_exception).__name__}: {self.original_exception}")
        return ". ".join(parts)


# --- Core CommunicationManager Exceptions ---

class CoreConnectionError(CoreBaseError):
    """Base class for errors related to the core communication channel.

    This exception is raised for issues encountered by a `CommunicationManager`
    instance, such as problems establishing a connection or maintaining an
    active link.
    """
    def __init__(self, message: str, url: Optional[str] = None, original_exception: Optional[BaseException] = None):
        super().__init__(message)
        self.url = url
        self.original_exception = original_exception

    def __str__(self) -> str:
        """Provide a more informative string representation."""
        parts = [super().__str__()]
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.original_exception:
            parts.append(f"Original Exception: {type(self.original_exception).__name__}: {self.original_exception}")
        return ". ".join(parts)


class CoreConnectionEstablishmentError(CoreConnectionError):
    """Base class for errors that occur specifically during the connection establishment phase.

    This type of error indicates that the `CommunicationManager` was unable to
    successfully initiate and complete the connection process to the remote endpoint.
    """
    pass


class CoreConnectionRefusedError(CoreConnectionEstablishmentError):
    """Raised when a connection attempt is actively refused by the remote endpoint.

    This typically means that no service is listening at the specified host and port,
    or a firewall is blocking the connection.

    Attributes:
        url (str): The target URL that the connection attempt was made to.
        original_exception (Optional[BaseException]): The lower-level exception
            (e.g., `ConnectionRefusedError` from the OS) that caused this failure, if any.
    """
    def __init__(self, url: str, original_exception: Optional[BaseException] = None):
        message = f"Connection was refused by the server at {url}."
        super().__init__(message, url=url, original_exception=original_exception)


class CoreConnectionTimeoutError(CoreConnectionEstablishmentError):
    """Raised when a connection attempt times out before it can be established.

    This indicates that the remote endpoint did not respond within the expected
    timeframe during the connection handshake.

    Attributes:
        url (str): The target URL that the connection attempt was made to.
        timeout_seconds (Optional[float]): The duration of the timeout in seconds, if available.
        original_exception (Optional[BaseException]): The lower-level timeout exception, if any.
    """
    def __init__(self, url: str, timeout_seconds: Optional[float] = None, original_exception: Optional[BaseException] = None):
        message = f"Connection attempt to {url} timed out"
        if timeout_seconds is not None:
            message += f" after {timeout_seconds:.2f} seconds."
        else:
            message += "."
        super().__init__(message, url=url, original_exception=original_exception)
        self.timeout_seconds = timeout_seconds


class CoreDisconnectedError(CoreConnectionError):
    """Raised when an operation is attempted on a disconnected or closed channel,
    or when an established connection is unexpectedly lost.

    This error signifies that the communication channel is not currently active
    and cannot perform the requested operation.

    Attributes:
        reason (Optional[str]): An optional string describing the reason for disconnection.
    """
    def __init__(self, message: str = "The communication channel is disconnected.", reason: Optional[str] = None, url: Optional[str] = None, original_exception: Optional[BaseException] = None):
        full_message = message
        if reason:
            full_message += f" Reason: {reason}"
        super().__init__(full_message, url=url, original_exception=original_exception)
        self.reason = reason


# --- Core TaskManager Exceptions ---

class CoreTaskManagerError(CoreBaseError):
    """Base class for errors related to the core TaskManager.

    This exception is raised for issues encountered during the operation of the
    `TaskManager`, such as problems submitting tasks or managing the event loop.
    """
    pass


class CoreLoopNotRunningError(CoreTaskManagerError, RuntimeError):
    """Raised when an operation requires the TaskManager's event loop to be running,
    but it is not.

    This might occur if `ensure_loop_running()` has not been called or if the
    loop has been stopped.
    """
    def __init__(self, message: str = "The TaskManager's event loop is not running."):
        super().__init__(message)


class CoreTaskSubmissionError(CoreTaskManagerError):
    """Raised when there is an error submitting a task to the TaskManager.

    This could be due to various reasons, such as the loop not being ready
    or an issue with the task itself during submission.

    Attributes:
        original_exception (Optional[BaseException]): The lower-level exception
            that occurred during task submission, if any.
    """
    def __init__(self, message: str = "Failed to submit task to the TaskManager.", original_exception: Optional[BaseException] = None):
        super().__init__(message)
        self.original_exception = original_exception

    def __str__(self) -> str:
        """Provide a more informative string representation."""
        parts = [super().__str__()]
        if self.original_exception:
            parts.append(f"Original Exception: {type(self.original_exception).__name__}: {self.original_exception}")
        return ". ".join(parts)
