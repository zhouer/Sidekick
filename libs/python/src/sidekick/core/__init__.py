"""Core infrastructure for the Sidekick Python library.

This sub-package (`sidekick.core`) provides the fundamental, low-level
abstractions and components that underpin the main Sidekick library's
functionality. It is designed to be environment-agnostic where possible,
with concrete implementations chosen at runtime based on whether the code
is executing in a standard CPython environment or Pyodide.

Key components provided by this core package include:

-   `TaskManager`: An abstraction for managing asyncio event loops and tasks.
-   `CommunicationManager`: An abstraction for handling raw, low-level
    communication channels (e.g., WebSockets, Pyodide message bridges).
-   Factory functions (`get_task_manager`, `get_communication_manager`) to
    obtain appropriate instances of these managers.
-   Core status enumerations (`CoreConnectionStatus`) and custom exceptions
    (e.g., `CoreConnectionError`) related to these fundamental operations.
-   Utility functions like `is_pyodide()` for environment detection.

Modules within `sidekick` (like `sidekick.connection`) will build upon
these core components to implement higher-level application logic.
"""

# --- Status Enums ---
from .status import CoreConnectionStatus

# --- Core Exceptions ---
from .exceptions import (
    CoreBaseError,
    CoreConnectionError,
    CoreConnectionEstablishmentError,
    CoreConnectionRefusedError,
    CoreConnectionTimeoutError,
    CoreDisconnectedError,
    CoreTaskManagerError,
    CoreLoopNotRunningError,
    CoreTaskSubmissionError,
)

# --- Utility Functions ---
from .utils import is_pyodide

# --- Abstract Base Classes for Managers ---
from .task_manager import TaskManager
from .communication_manager import (
    CommunicationManager,
    MessageHandlerType,
    StatusChangeHandlerType,
    ErrorHandlerType
)

# --- Factory Functions ---
from .factories import get_task_manager


__all__ = [
    # Status
    'CoreConnectionStatus',

    # Exceptions
    'CoreBaseError',
    'CoreConnectionError',
    'CoreConnectionEstablishmentError',
    'CoreConnectionRefusedError',
    'CoreConnectionTimeoutError',
    'CoreDisconnectedError',
    'CoreTaskManagerError',
    'CoreLoopNotRunningError',
    'CoreTaskSubmissionError',

    # Utilities
    'is_pyodide',

    # ABCs
    'TaskManager',
    'CommunicationManager',

    # Handler Type Aliases
    'MessageHandlerType',
    'StatusChangeHandlerType',
    'ErrorHandlerType',

    # Factories
    'get_task_manager',
]
