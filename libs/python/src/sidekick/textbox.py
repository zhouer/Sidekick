"""Provides the Textbox class for creating text input fields in Sidekick.

Use the `sidekick.Textbox` class to add a single-line text input field to your
Sidekick UI panel. Users can type text into this field. When they press Enter
or the field loses focus (on-blur), the entered text is sent back to your Python
script, triggering a callback function you define, which receives a
`TextboxSubmitEvent` object.

Textboxes can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization, or by adding them as children
to a container's constructor. You can also provide an `instance_id` to uniquely
identify the textbox.

You can define the textbox's submission behavior in several ways:

1.  Using the `on_submit` parameter in the constructor:
    `query_box = sidekick.Textbox(on_submit=handle_query, instance_id="query-input")`
2.  Using the `textbox.on_submit(callback)` method after creation:
    `name_input = sidekick.Textbox()`
    `name_input.on_submit(process_name)`
3.  Using the `@textbox.submit` decorator:
    `code_input = sidekick.Textbox()`
    `@code_input.submit`
    `def execute_code(event: sidekick.TextboxSubmitEvent): print(f"Executing: {event.value}")`
"""

from . import logger
from .component import Component
from .events import TextboxSubmitEvent, ErrorEvent
from typing import Optional, Callable, Dict, Any, Union, Coroutine

class Textbox(Component):
    """Represents a single-line Textbox component instance in the Sidekick UI.

    Creates an input field where users can type text. Use the `on_submit`
    method, the `@textbox.submit` decorator, or the `on_submit` constructor
    parameter to define a Python function that receives a `TextboxSubmitEvent`
    (containing the submitted text) when the user submits it (e.g., by pressing
    Enter or when the input field loses focus).

    The `value` property allows you to programmatically get or set the text
    currently displayed in the textbox. The `placeholder` property controls
    the hint text shown when the textbox is empty.

    Attributes:
        instance_id (str): The unique identifier for this textbox instance.
        value (str): The current text content of the textbox.
        placeholder (str): The placeholder text displayed when the box is empty.
    """
    def __init__(
        self,
        value: str = "",
        placeholder: str = "",
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_submit: Optional[Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
    ):
        """Initializes the Textbox object and creates the UI element.

        This function is called when you create a new Textbox, for example:
        `user_input = sidekick.Textbox(placeholder="Enter your name", on_submit=greet_user)`

        It sends a message to the Sidekick UI to display a new text input field.

        Args:
            value (str): The text initially displayed in the input field.
                Defaults to "".
            placeholder (str): Hint text shown when the input field is empty.
                Defaults to "".
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this textbox. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this textbox
                should be placed. If `None` (the default), the textbox is added
                to the main Sidekick panel area.
            on_submit (Optional[Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call when
                the user submits text from this textbox. The function should
                accept one `TextboxSubmitEvent` object as an argument, which
                contains `instance_id`, `type`, and `value` (the submitted text).
                The callback can be a regular function or a coroutine function (async def).
                Defaults to `None`.
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call if
                an error related to this specific textbox occurs in the Sidekick UI.
                The function should take one `ErrorEvent` object as an argument.
                The callback can be a regular function or a coroutine function (async def).
                Defaults to `None`.

        Raises:
            ValueError: If the provided `instance_id` is invalid or a duplicate.
            TypeError: If `parent` is an invalid type, or if `on_submit` or
                `on_error` are provided but are not callable functions.
        """
        self._value = str(value)
        self._placeholder = str(placeholder)
        # Callback function provided by the user via on_submit or decorator.
        # Initialize here.
        self._submit_callback: Optional[Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]] = None

        # Prepare the payload for the 'spawn' command.
        spawn_payload: Dict[str, Any] = {}
        # Only include keys in the payload if they have non-default (non-empty) values,
        # as per protocol examples, to keep messages concise.
        if self._value: # Check against value (converted to str)
            spawn_payload["value"] = self._value
        if self._placeholder: # Check against placeholder (converted to str)
            spawn_payload["placeholder"] = self._placeholder

        super().__init__(
            component_type="textbox",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(
            f"Textbox '{self.instance_id}' initialized (value='{self._value}', " # Use self.instance_id
            f"placeholder='{self._placeholder}')."
        )

        # Register on_submit callback if provided in the constructor.
        if on_submit is not None:
            self.on_submit(on_submit)

    @property
    def value(self) -> str:
        """str: The current text content of the textbox.

        Reading this property returns the value stored locally in the Python object.
        This local value is updated whenever the user submits text from the UI
        (triggering an `on_submit` event that carries a `TextboxSubmitEvent` with the new value).

        Setting this property (e.g., `my_textbox.value = "New text"`) updates
        the local value and also sends a command to update the text displayed
        in the Sidekick UI's input field.
        """
        return self._value

    @value.setter
    def value(self, new_text_value: str):
        """Sets the text content displayed in the textbox."""
        new_val_str = str(new_text_value)
        # Update local state first
        self._value = new_val_str
        # Prepare payload for the 'setValue' update action.
        payload = {
            "action": "setValue",
            "options": {"value": new_val_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(f"Textbox '{self.instance_id}' value set to '{new_val_str}'.") # Use self.instance_id

    @property
    def placeholder(self) -> str:
        """str: The placeholder text displayed when the textbox is empty.

        Setting this property (e.g., `my_textbox.placeholder = "Enter command..."`)
        updates the placeholder text in the Sidekick UI.
        """
        return self._placeholder

    @placeholder.setter
    def placeholder(self, new_placeholder: str):
        """Sets the placeholder text displayed when the textbox is empty."""
        new_ph_str = str(new_placeholder)
        # Update local state
        self._placeholder = new_ph_str
        # Prepare payload for the 'setPlaceholder' update action.
        payload = {
            "action": "setPlaceholder",
            "options": {"placeholder": new_ph_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(f"Textbox '{self.instance_id}' placeholder set to '{new_ph_str}'.") # Use self.instance_id

    def on_submit(self, callback: Optional[Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]]):
        """Registers a function to call when the user submits text from this textbox.

        The submission typically happens when the user presses Enter while the
        textbox has focus, or when the input field loses focus (on-blur event).
        The provided callback function will receive a `TextboxSubmitEvent` object,
        which contains the `instance_id` of this textbox, the event `type` ("submit"),
        and the `value` (the submitted text string).

        You can also set this callback directly when creating the textbox using
        the `on_submit` parameter in its constructor.

        Args:
            callback (Optional[Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]]): The function to call on submit.
                It must accept one `TextboxSubmitEvent` argument. The callback can be a regular
                function or a coroutine function (async def). Pass `None` to remove the current callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.

        Example:
            >>> from sidekick.events import TextboxSubmitEvent
            >>>
            >>> def process_input(event: TextboxSubmitEvent):
            ...     print(f"Textbox '{event.instance_id}' submitted: {event.value}")
            ...
            >>> entry_field = sidekick.Textbox(instance_id="user-entry")
            >>> entry_field.on_submit(process_input)
            >>> # sidekick.run_forever() # Needed to process submissions
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_submit callback must be a callable function or None.")
        logger.info(f"Setting on_submit callback for textbox '{self.instance_id}'.") # Use self.instance_id
        self._submit_callback = callback

    def submit(self, func: Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]) -> Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]:
        """Decorator to register a function to call when the user submits text.

        This provides an alternative, more Pythonic syntax to `on_submit()`
        if you prefer decorators. The decorated function will receive a
        `TextboxSubmitEvent` object as its argument.

        Args:
            func (Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]): The function to register as the submit handler.
                It must accept one `TextboxSubmitEvent` argument. The callback can be a regular
                function or a coroutine function (async def).

        Returns:
            Callable[[TextboxSubmitEvent], Union[None, Coroutine[Any, Any, None]]]: The original function, allowing the decorator to be used directly.

        Raises:
            TypeError: If `func` is not a callable function.

        Example:
            >>> from sidekick.events import TextboxSubmitEvent
            >>>
            >>> name_input = sidekick.Textbox(placeholder="Enter name", instance_id="name-field")
            >>>
            >>> @name_input.submit
            ... def handle_name(event: TextboxSubmitEvent):
            ...     print(f"Hello, {event.value} (from '{event.instance_id}')!")
            ...
            >>> # sidekick.run_forever() # Needed to process submissions
        """
        self.on_submit(func) # Register the function using the standard method
        return func # Return the original function

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' messages for this textbox. (Internal).

        This method is called by the Sidekick connection manager when an event
        (like a "submit") occurs on this textbox in the UI.
        It constructs a `TextboxSubmitEvent` object and passes it to the registered callback.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        # Check if it's a submit event targeted at this textbox instance.
        if msg_type == "event" and payload and payload.get("event") == "submit":
            # The UI sends the submitted text in the 'value' field of the payload.
            submitted_value_str = payload.get("value", "") # Default to empty string if missing
            # Ensure it's a string, though protocol should guarantee it.
            submitted_value_str = str(submitted_value_str)

            logger.debug(
                f"Textbox '{self.instance_id}' received submit event with value: '{submitted_value_str}'" # Use self.instance_id
            )

            # Update the local _value to match what was submitted from the UI.
            # This ensures consistency if the user reads textbox.value after submission.
            self._value = submitted_value_str

            # Construct the TextboxSubmitEvent object
            submit_event = TextboxSubmitEvent(
                instance_id=self.instance_id,
                type="submit",
                value=self._value  # Pass the locally updated (and validated as string) value
            )
            self._invoke_callback(self._submit_callback, submit_event)
            return

        # Call the base handler for potential 'error' messages.
        super()._internal_message_handler(message)

    def _reset_specific_callbacks(self):
        """Internal: Resets textbox-specific callbacks when the component is removed."""
        super()._reset_specific_callbacks()
        self._submit_callback = None
        logger.debug(f"Textbox '{self.instance_id}': Submit callback reset.") # Use self.instance_id
