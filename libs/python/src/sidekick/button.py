"""Provides the Button class for creating clickable buttons in Sidekick.

Use the `sidekick.Button` class to add a standard clickable button to your
Sidekick UI panel. Clicking the button in the UI triggers a callback function
in your Python script, which receives a `ButtonClickEvent` object.

Buttons can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization, or by adding them as children
to a container's constructor. You can also provide an `instance_id` to uniquely
identify the button.

You can define the button's click behavior in several ways:

1.  Using the `on_click` parameter in the constructor:
    `button = sidekick.Button("Run", on_click=my_run_function, instance_id="run-btn")`
2.  Using the `button.on_click(callback)` method after creation:
    `button = sidekick.Button("Submit")`
    `button.on_click(handle_submission)`
3.  Using the `@button.click` decorator:
    `button = sidekick.Button("Decorated")`
    `@button.click`
    `def decorated_handler(event: sidekick.ButtonClickEvent): print(f"Button '{event.instance_id}' clicked!")`
"""

from . import logger
from .component import Component
from .events import ButtonClickEvent, ErrorEvent
from typing import Optional, Callable, Dict, Any, Union, Coroutine

class Button(Component):
    """Represents a clickable Button component instance in the Sidekick UI.

    Creates a button with a text label. Use the `on_click` method, the
    `@button.click` decorator, or the `on_click` constructor parameter
    to define what happens in Python when the button is clicked in the UI.
    The callback function will receive a `ButtonClickEvent` object.

    Attributes:
        instance_id (str): The unique identifier for this button instance.
        text (str): The text label currently displayed on the button.
    """
    def __init__(
        self,
        text: str = "",
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_click: Optional[Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
    ):
        """Initializes the Button object and creates the UI element.

        This function is called when you create a new Button, for example:
        `my_button = sidekick.Button("Click Here", on_click=handle_my_click)`

        It sends a message to the Sidekick UI to display a new button.

        Args:
            text (str): The initial text label displayed on the button.
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this button. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this button
                should be placed. If `None` (the default), the button is added
                to the main Sidekick panel area.
            on_click (Optional[Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call when
                this button is clicked in the Sidekick UI. The function should
                accept one `ButtonClickEvent` object as an argument. The callback can be a regular
                function or a coroutine function (async def). Defaults to `None`.
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call if
                an error related to this specific button occurs in the Sidekick UI.
                The function should take one `ErrorEvent` object as an argument. The callback can be a regular
                function or a coroutine function (async def). Defaults to `None`.

        Raises:
            ValueError: If the provided `instance_id` is invalid or a duplicate.
            TypeError: If `parent` is an invalid type, or if `on_click` or
                `on_error` are provided but are not callable functions.
        """
        self._text = str(text)
        # Callback function provided by the user via on_click or decorator.
        # Initialize here before super() in case super() somehow triggers an event.
        self._click_callback: Optional[Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]] = None

        # Prepare the payload for the 'spawn' command.
        spawn_payload: Dict[str, Any] = {
            "text": self._text
        }

        super().__init__(
            component_type="button",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(f"Button '{self.instance_id}' initialized with text '{self._text}'.") # Use self.instance_id

        # Register on_click callback if provided in the constructor.
        if on_click is not None:
            self.on_click(on_click)

    @property
    def text(self) -> str:
        """str: The text label currently displayed on the button.

        Setting this property updates the button's text in the Sidekick UI.
        For example:
        `my_button.text = "Submit Now"`
        """
        return self._text

    @text.setter
    def text(self, new_text: str):
        """Sets the text label displayed on the button."""
        new_text_str = str(new_text)
        # Update local state first
        self._text = new_text_str
        # Prepare payload for the 'setText' update action.
        payload = {
            "action": "setText",
            "options": {"text": new_text_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(f"Button '{self.instance_id}' text set to '{new_text_str}'.") # Use self.instance_id

    def on_click(self, callback: Optional[Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]]):
        """Registers a function to be called when this button is clicked.

        The provided callback function will be executed in your Python script
        when the user clicks this specific button in the Sidekick UI. The callback
        function will receive a `ButtonClickEvent` object, which contains the
        `instance_id` of this button and the event `type` ("click").

        You can also set this callback directly when creating the button using
        the `on_click` parameter in its constructor.

        Args:
            callback (Optional[Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]]): The function to call on click.
                It should accept one `ButtonClickEvent` argument. The callback can be a regular
                function or a coroutine function (async def). Pass `None` to remove the current callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.

        Example:
            >>> from sidekick.events import ButtonClickEvent
            >>>
            >>> def my_action(event: ButtonClickEvent):
            ...     print(f"Button '{event.instance_id}' was pressed!")
            ...
            >>> my_btn = sidekick.Button("Do Action", instance_id="action-button")
            >>> my_btn.on_click(my_action)
            >>> # sidekick.run_forever() # Needed to process clicks
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for button '{self.instance_id}'.") # Use self.instance_id
        self._click_callback = callback

    def click(self, func: Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]) -> Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]:
        """Decorator to register a function to be called when this button is clicked.

        This provides an alternative, more Pythonic way to set the click handler
        if you prefer decorators. The decorated function will receive a
        `ButtonClickEvent` object as its argument.

        Args:
            func (Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]): The function to register as the click handler.
                It should accept one `ButtonClickEvent` argument. The callback can be a regular
                function or a coroutine function (async def).

        Returns:
            Callable[[ButtonClickEvent], Union[None, Coroutine[Any, Any, None]]]: The original function, allowing the decorator to be used directly.

        Raises:
            TypeError: If `func` is not a callable function.

        Example:
            >>> from sidekick.events import ButtonClickEvent
            >>>
            >>> my_button = sidekick.Button("Run Me", instance_id="decorated-btn")
            >>>
            >>> @my_button.click
            ... def handle_button_press(event: ButtonClickEvent):
            ...     print(f"Button '{event.instance_id}' (decorated) was clicked!")
            ...     # Perform some action...
            ...
            >>> # sidekick.run_forever() # Needed to process clicks
        """
        self.on_click(func) # Register the function using the standard method
        return func # Return the original function

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' messages for this button. (Internal).

        This method is called by the Sidekick connection manager when an event
        (like a "click") occurs on this button in the UI.
        It constructs a `ButtonClickEvent` object and passes it to the registered callback.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event" and payload and payload.get("event") == "click":
            logger.debug(f"Button '{self.instance_id}' received click event.")
            click_event = ButtonClickEvent(
                instance_id=self.instance_id,
                type="click"
            )
            self._invoke_callback(self._click_callback, click_event)
        else:
            super()._internal_message_handler(message)

    def _reset_specific_callbacks(self):
        """Internal: Resets button-specific callbacks when the component is removed."""
        super()._reset_specific_callbacks()
        self._click_callback = None
        logger.debug(f"Button '{self.instance_id}': Click callback reset.") # Use self.instance_id
