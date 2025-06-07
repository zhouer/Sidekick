"""Defines structured event objects for Sidekick Python library callbacks.

This module uses Python's `dataclasses` to create clear, type-hinted event
objects that are passed to user-defined callback functions registered with
Sidekick components (e.g., `on_click`, `on_submit`, `on_error`).

Using structured event objects provides several benefits:

- **API Consistency:** All event callbacks receive a single event object argument.
- **Type Safety:** Clear type hints improve code understanding and help static analysis.
- **Extensibility:** Adding new information to events in the future can be done
  by adding fields to these dataclasses without breaking existing callback signatures.
- **Rich Context:** Event objects can carry common contextual information like the
  ID of the component instance that triggered the event and the type of the event,
  in addition to event-specific data.
"""

from dataclasses import dataclass, field
# field can be used for more advanced dataclass features if needed in the future,
# like default_factory or custom metadata, but not strictly necessary for this initial proposal.

# --- Base Event Class ---

@dataclass
class BaseSidekickEvent:
    """
    Base class for all Sidekick events.

    Attributes:
        instance_id (str): The unique identifier of the Python component instance
                           that is associated with this event (e.g., the button that
                           was clicked, or the grid that reported an error from the UI).
        type (str): A string indicating the specific type of event
                    (e.g., "click", "submit", "error").
    """
    instance_id: str
    type: str


# --- Component-Specific Interaction Event Classes ---

@dataclass
class ButtonClickEvent(BaseSidekickEvent):
    """
    Event dispatched when a `sidekick.Button` is clicked in the UI.

    Attributes:
        instance_id (str): The ID of the `Button` instance that was clicked.
        type (str): Always "click" for this event type.
    """
    # No button-specific payload for a simple click,
    # but future enhancements could add fields here (e.g., modifier keys).
    pass


@dataclass
class GridClickEvent(BaseSidekickEvent):
    """
    Event dispatched when a cell in a `sidekick.Grid` is clicked in the UI.

    Attributes:
        instance_id (str): The ID of the `Grid` instance where the click occurred.
        type (str): Always "click" for this event type.
        x (int): The 0-based column index of the clicked cell.
        y (int): The 0-based row index of the clicked cell.
    """
    x: int
    y: int


@dataclass
class CanvasClickEvent(BaseSidekickEvent):
    """
    Event dispatched when a `sidekick.Canvas` is clicked in the UI.

    Attributes:
        instance_id (str): The ID of the `Canvas` instance that was clicked.
        type (str): Always "click" for this event type.
        x (int): The x-coordinate of the click relative to the canvas's top-left origin.
        y (int): The y-coordinate of the click relative to the canvas's top-left origin.
    """
    x: int
    y: int


@dataclass
class TextboxSubmitEvent(BaseSidekickEvent):
    """
    Event dispatched when text is submitted from a `sidekick.Textbox` in the UI
    (e.g., by pressing Enter or on blur).

    Attributes:
        instance_id (str): The ID of the `Textbox` instance from which text was submitted.
        type (str): Always "submit" for this event type.
        value (str): The text string that was submitted by the user.
    """
    value: str


@dataclass
class ConsoleSubmitEvent(BaseSidekickEvent):
    """
    Event dispatched when text is submitted from a `sidekick.Console`'s input
    field (if `show_input=True`) in the UI.

    Attributes:
        instance_id (str): The ID of the `Console` instance from which text was submitted.
        type (str): Always "submit" for this event type.
        value (str): The text string that was submitted by the user.
    """
    value: str


# --- Error Event Class ---

@dataclass
class ErrorEvent(BaseSidekickEvent):
    """
    Event dispatched when an error related to a specific Sidekick component
    is reported back from the Sidekick UI.

    Attributes:
        instance_id (str): The ID of the component instance that encountered or
                           reported the error in the UI.
        type (str): Always "error" for this event type.
        message (str): A string describing the error that occurred.
    """
    message: str
