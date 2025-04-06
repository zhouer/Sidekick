# Sidekick/libs/python/src/sidekick/console.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Console(BaseModule):
    """
    Represents a Console module instance in the Sidekick UI.

    Allows printing text output to a scrolling area and optionally receiving
    user input via a text field. Callbacks can be registered for input events
    and errors.

    This class can either create a new console instance in Sidekick or attach
    to a pre-existing one.

    Attributes:
        target_id (str): The unique identifier for this console instance.
    """
    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        initial_text: str = "",
        show_input: bool = False
    ):
        """
        Initializes or attaches to a Console module in the Sidekick UI.

        Args:
            instance_id (Optional[str]): A specific ID for this console instance.
                - If `spawn=True`: Optional. Auto-generated if None.
                - If `spawn=False`: **Required**.
            spawn (bool): If True (default), creates a new console instance.
                If False, attaches to an existing one. `initial_text` and `show_input`
                are ignored if `spawn=False`.
            initial_text (str): Text line to display immediately upon creation.
                Only used if `spawn=True`. Defaults to "".
            show_input (bool): If True, displays a text input field in Sidekick.
                Defaults to False. Only used if `spawn=True`.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is None, or if
                        `show_input` is missing/invalid when `spawn` is True.
        """
        spawn_payload: Dict[str, Any] = {}
        if spawn:
            # Validate showInput during spawn
            if show_input is None or not isinstance(show_input, bool):
                 raise ValueError(f"Console spawn requires a boolean 'show_input', got {show_input}")
            spawn_payload["showInput"] = show_input # camelCase key
            if initial_text:
                 spawn_payload["text"] = initial_text

        # Initialize the base class
        super().__init__(
            module_type="console",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None
        )
        self._input_text_callback: Optional[Callable[[str], None]] = None
        connection.logger.info(f"Console '{self.target_id}' initialized (spawn={spawn}, show_input={show_input if spawn else 'N/A'}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages for this console instance."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "inputText" and self._input_text_callback:
                try:
                    value = payload.get("value")
                    if isinstance(value, str):
                        self._input_text_callback(value)
                    else:
                         connection.logger.warning(f"Console '{self.target_id}' received inputText event with non-string value: {payload}")
                except Exception as e:
                    connection.logger.exception(f"Error in Console '{self.target_id}' on_input_text callback: {e}")
            else:
                 connection.logger.debug(f"Console '{self.target_id}' received unhandled event type '{event_type}'.")

        # Call base handler for error messages
        super()._internal_message_handler(message)

    def on_input_text(self, callback: Optional[Callable[[str], None]]):
        """
        Registers a function to be called when text is submitted via the
        input field in the Sidekick UI (only applicable if `show_input=True`).

        The callback function will receive one string argument: the text entered
        by the user.

        Args:
            callback: A function accepting a single string argument, or None to unregister.
        """
        if callback is not None and not callable(callback):
            raise TypeError("Input text callback must be callable or None")
        connection.logger.info(f"Setting on_input_text callback for console '{self.target_id}'.")
        self._input_text_callback = callback

    # on_error is inherited from BaseModule

    def print(self, *args: Any, sep: str = ' ', end: str = ''):
        """
        Prints text to this console module instance in Sidekick.

        Args:
            *args (Any): Objects to print (converted to string).
            sep (str): Separator between objects. Defaults to ' '.
            end (str): String appended at the end. Defaults to ''.
        """
        text_to_print = sep.join(map(str, args)) + end
        payload = {
            "action": "append",
            "options": { "text": text_to_print } # camelCase key
        }
        self._send_update(payload)

    def log(self, message: Any):
        """A convenient shortcut to print a single message."""
        self.print(message)

    def clear(self):
        """Removes all text from this console instance in Sidekick."""
        connection.logger.info(f"Requesting clear for console '{self.target_id}'.")
        payload = { "action": "clear" }
        self._send_update(payload)

    def _reset_specific_callbacks(self):
        """Resets console-specific callbacks on removal."""
        self._input_text_callback = None

    # remove() is inherited from BaseModule