"""Provides the Console class for displaying text output in Sidekick.

Use the `sidekick.Console` class to create a dedicated text area within the
Sidekick panel. This acts like a separate terminal or output window specifically
for your script, allowing you to display status messages, log information, or
show results without cluttering the main VS Code terminal.

The console can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization, or by adding it as a child
to a container's constructor. You can also provide an `instance_id` to uniquely
identify the console.

Key Features:

*   **Text Output:** Use the `print()` method (similar to Python's built-in `print`)
    to append text messages to the console area.
*   **Optional Text Input:** Configure the console (`show_input=True`) to include
    a text input field at the bottom. Users can type text into this field and
    submit it back to your running Python script.
*   **Input Handling:** Use the `on_submit()` method or the `on_submit`
    constructor parameter to register a callback function that gets executed
    (receiving a `ConsoleSubmitEvent` object) whenever the user submits text
    from the input field.
*   **Clearing:** Use the `clear()` method to remove all previously displayed text.

Basic Usage:
    >>> import sidekick
    >>> console = sidekick.Console(instance_id="main-log")
    >>> console.print("Script starting...")

Interactive Usage with a Parent Container:
    >>> import sidekick
    >>> from sidekick.events import ConsoleSubmitEvent # Import the event type
    >>>
    >>> my_column = sidekick.Column()
    >>>
    >>> def handle_command(event: ConsoleSubmitEvent):
    ...     print(f"Console '{event.instance_id}' received: '{event.value}'")
    ...     # Assume 'console_in_col' is accessible
    ...     console_in_col.print(f"Processing: {event.value}")
    ...
    >>> console_in_col = sidekick.Console(
    ...     show_input=True,
    ...     parent=my_column,
    ...     instance_id="command-console",
    ...     on_submit=handle_command
    ... )
    >>> # sidekick.run_forever() # Keep script running to process input
"""

from . import logger
from .component import Component
from .events import ConsoleSubmitEvent, ErrorEvent
from typing import Optional, Callable, Dict, Any, Union

class Console(Component):
    """Represents a Console component instance in the Sidekick UI panel.

    Creates a scrollable text area for displaying output and optionally an input field
    if `show_input` is set to `True`. Can be nested within layout containers.

    Attributes:
        instance_id (str): The unique identifier for this console instance.
    """
    def __init__(
        self,
        initial_text: str = "",
        show_input: bool = False,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_submit: Optional[Callable[[ConsoleSubmitEvent], None]] = None,
        on_error: Optional[Callable[[ErrorEvent], None]] = None,
    ):
        """Initializes the Console object and creates the UI element.

        This function is called when you create a new Console, for example:
        `log_area = sidekick.Console()`
        or for interactive use:
        `cmd_console = sidekick.Console(show_input=True, on_submit=process_cmd)`

        It sends a message to the Sidekick UI to display a new console area.

        Args:
            initial_text (str): Text to display in the console area immediately
                after it's created. Defaults to an empty string.
            show_input (bool): If `True`, an input field will be shown at the
                bottom of the console, allowing users to type and submit text
                back to the Python script. Defaults to `False`.
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this console. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this console
                should be placed. If `None` (the default), the console is added
                to the main Sidekick panel area.
            on_submit (Optional[Callable[[ConsoleSubmitEvent], None]]): A function to call
                when the user submits text from the input field (if `show_input`
                is `True`). The function should accept one `ConsoleSubmitEvent` object
                as an argument, which contains `instance_id`, `type`, and `value` (the
                submitted text). Defaults to `None`.
            on_error (Optional[Callable[[ErrorEvent], None]]): A function to call if
                an error related to this specific console occurs in the Sidekick UI.
                The function should take one `ErrorEvent` object as an argument.
                Defaults to `None`.

        Raises:
            ValueError: If the provided `instance_id` is invalid or a duplicate.
            SidekickConnectionError: If the library cannot connect to the
                Sidekick UI panel.
            TypeError: If `parent` is an invalid type, or if `on_submit` or
                `on_error` are provided but are not callable functions.
        """
        spawn_payload: Dict[str, Any] = {
            "showInput": bool(show_input) # Ensure it's a boolean
        }
        # Only include 'text' in payload if initial_text is provided,
        # to keep the spawn message concise, similar to protocol examples.
        if initial_text:
             spawn_payload["text"] = str(initial_text)

        # Initialize before super() in case super() triggers events or uses these.
        self._submit_callback: Optional[Callable[[ConsoleSubmitEvent], None]] = None

        super().__init__(
            component_type="console",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(
            f"Console '{self.instance_id}' initialized " # Use self.instance_id
            f"(show_input={show_input}, initial_text='{initial_text[:50]}{'...' if len(initial_text)>50 else ''}')."
        )

        # Register on_submit callback if provided in the constructor.
        if on_submit is not None:
            self.on_submit(on_submit)

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this console. (Internal).

        This method is called by the Sidekick connection manager when an event
        (like "submit") occurs on this console in the UI.
        It constructs a `ConsoleSubmitEvent` object and passes it to the registered callback.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "submit" and self._submit_callback:
                try:
                    # The UI sends the submitted text in the 'value' field.
                    submitted_text = payload.get("value")
                    if isinstance(submitted_text, str):
                        # Construct the ConsoleSubmitEvent object
                        submit_event = ConsoleSubmitEvent(
                            instance_id=self.instance_id,
                            type="submit",
                            value=submitted_text
                        )
                        self._submit_callback(submit_event)
                    else:
                         # This case should ideally not happen if UI adheres to protocol.
                         logger.warning(
                            f"Console '{self.instance_id}' received 'submit' event " # Use self.instance_id
                            f"with non-string value: {payload}"
                         )
                except Exception as e:
                    # Prevent errors in user callback from crashing the listener.
                    logger.exception(
                        f"Error occurred inside Console '{self.instance_id}' " # Use self.instance_id
                        f"on_submit callback: {e}"
                    )
            elif event_type: # An event occurred but we don't have a handler or it's an unknown type
                 logger.debug(
                    f"Console '{self.instance_id}' received unhandled event type '{event_type}' " # Use self.instance_id
                    f"or no input callback registered for 'submit'."
                 )
        # Always call the base handler for potential 'error' messages or other base handling.
        super()._internal_message_handler(message)

    def on_submit(self, callback: Optional[Callable[[ConsoleSubmitEvent], None]]):
        """Registers a function to call when the user submits text from the console's input field.

        This method is only relevant if the console was initialized with `show_input=True`.
        The provided callback function will be executed in your Python script. It will
        receive a `ConsoleSubmitEvent` object containing the `instance_id` of this
        console, the event `type` ("submit"), and the `value` (the submitted text string).

        You can also set this callback directly when creating the console using
        the `on_submit` parameter in its constructor.

        Args:
            callback (Optional[Callable[[ConsoleSubmitEvent], None]]): The function to call when
                text is submitted. It must accept one `ConsoleSubmitEvent` argument.
                Pass `None` to remove a previously registered callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.

        Example:
            >>> from sidekick.events import ConsoleSubmitEvent
            >>>
            >>> def my_command_handler(event: ConsoleSubmitEvent):
            ...     if event.value == "help":
            ...         interactive_console.print("Available commands: ...")
            ...     else:
            ...         interactive_console.print(f"Unknown command: {event.value}")
            ...
            >>> interactive_console = sidekick.Console(show_input=True, instance_id="cmd-line")
            >>> interactive_console.on_submit(my_command_handler)
            >>> # sidekick.run_forever() # Needed to process input
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_submit callback must be a callable function or None.")
        logger.info(f"Setting on_submit callback for console '{self.instance_id}'.") # Use self.instance_id
        self._submit_callback = callback

    def print(self, *args: Any, sep: str = ' ', end: str = '\n'):
        """Prints messages to this console instance in the Sidekick UI.

        This works very much like Python's built-in `print()` function.
        You can pass multiple arguments, and they will be converted to strings,
        joined by the `sep` string, and finally, the `end` string will be appended.

        Args:
            *args (Any): One or more objects to print. They will be converted to
                their string representations.
            sep (str): The separator string to place between arguments if multiple
                are provided. Defaults to a single space (' ').
            end (str): The string to append at the end of the printed output.
                Defaults to a newline character ('\\n').

        Raises:
            SidekickConnectionError: If sending the print command to the UI fails.

        Example:
            >>> log_console = sidekick.Console(instance_id="app-log")
            >>> item_id = 123
            >>> status_code = 200
            >>> log_console.print("Processing item:", item_id, "Status:", status_code)
        """
        text_to_print = sep.join(map(str, args)) + end
        # Prepare payload for the 'append' update action.
        # Keys must be camelCase per the protocol.
        payload = {
            "action": "append",
            "options": { "text": text_to_print }
        }
        self._send_update(payload)
        # No need to log every print, can be too verbose. Debug level if needed.
        # logger.debug(f"Console '{self.instance_id}' printed: '{text_to_print.strip()}'")

    def clear(self):
        """Removes all previously printed text from this console instance.

        This will make the console area empty again.

        Raises:
            SidekickConnectionError: If sending the clear command to the UI fails.
        """
        logger.info(f"Requesting clear for console '{self.instance_id}'.") # Use self.instance_id
        # Prepare payload for the 'clear' update action.
        payload = { "action": "clear" } # No options needed for clear
        self._send_update(payload)

    def _reset_specific_callbacks(self):
        """Internal: Resets console-specific callbacks when the component is removed."""
        super()._reset_specific_callbacks()
        self._submit_callback = None
        logger.debug(f"Console '{self.instance_id}': Submit callback reset.") # Use self.instance_id