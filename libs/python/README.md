# Sidekick Python Library

## 1. Overview

This library provides the Python interface ("Hero") for interacting with the Sidekick Visual Coding Buddy frontend UI. It allows Python scripts to easily create, update, interact with, and remove visual modules like grids, consoles, variable visualizers, and drawing canvases within the Sidekick UI.

It abstracts the underlying WebSocket communication and message formatting , offering an intuitive object-oriented API.

## 2. Features

*   **Object-Oriented API:** Control visual modules (`Grid`, `Console`, `Viz`, `Canvas`, `Control`) via Python classes and methods (using `snake_case`).
*   **`ObservableValue`:** A general-purpose wrapper to track changes in Python values (primitives or containers). Notifies subscribers with detailed change information (`type`, `path`, `value`, `key`, `old_value`, `length`).
*   **Automatic WebSocket Management:** Handles connection (`ws://localhost:5163` default), keep-alive (Ping/Pong), listener thread, and `atexit` cleanup.
*   **Callback Handling:** Supports receiving notifications from interactive modules (`Grid`, `Console`, `Control`) via user-provided `on_message` callbacks.
*   **Structured Data Visualization (`Viz`):** Provides detailed, expandable views of Python data structures, reacting to granular changes from `ObservableValue`. Sends updates using a structured `action`/`variableName`/`options` payload.
*   **Basic 2D Drawing (`Canvas`):** Allows drawing lines, rectangles, and circles. Commands include unique IDs for reliable frontend processing.
*   **Dynamic UI Controls (`Control`):** Add buttons and text inputs dynamically, receiving interaction events.

## 3. Installation

**Development (Recommended):**

Install in editable mode from the project root (`Sidekick/`) directory:

```bash
pip install -e libs/python
```

This links the installed package to your source code, so changes are immediately reflected.

**Distribution (PyPI):**

```bash
pip install sidekick-py
```
*(Note: PyPI package name might need confirmation)*

## 4. Core Concepts

### 4.1. Connection Management (`connection.py`)

*   **Singleton:** Manages a single, shared WebSocket connection.
*   **Lazy Connection:** Connects automatically on the first relevant action (usually module instantiation).
*   **URL Configuration:** Use `sidekick.set_url(url)` *before* creating modules to change the target server.
*   **Keep-Alive:** Uses WebSocket Ping/Pong for reliable connection maintenance (disables underlying socket timeout after connection).
*   **Listener Thread:** A background thread listens for incoming messages (`notify`, `error`) from Sidekick.
*   **Message Dispatch:** Incoming `notify` messages with a `src` field matching a registered module's ID are dispatched to that module's `on_message` callback (if provided). `error` messages or messages without `src` are currently logged.
*   **Cleanup:** `atexit` handler ensures graceful connection closure on script exit.

### 4.2. Base Module (`base_module.py`)

*   Provides common functionality for all module classes (`Grid`, `Console`, etc.).
*   Handles `instance_id` generation (stores as `self.target_id`), `spawn` command sending, and `on_message` callback registration via `connection.register_message_handler`.
*   Provides `_send_command(method, payload)` and `_send_update(payload)` helpers for sending messages with the correct structure (`module`, `target`). Payloads sent should use `camelCase` keys.
*   The `remove()` method handles unregistering the callback and sending the `remove` command.

### 4.3. Communication Protocol & Payloads

*   Communication uses JSON messages over WebSocket.
*   Messages from Python (Hero) to Sidekick have `module`, `method` ("spawn", "update", "remove"), and `target` fields.
*   Messages from Sidekick to Python (Hero) have `module`, `method` ("notify", "error"), and `src` fields.
*   **Crucially, the `payload` object within all messages MUST use `camelCase` keys.**
*   `update` payloads generally follow a pattern:
    *   `action`: A string indicating the specific update operation (e.g., "setCell", "clear", "append", "config", "add", "set").
    *   `options`: An object containing parameters for the action (e.g., coordinates, color, text, styles).
    *   Some payloads (like `viz` and `control`) might have top-level identifiers (`variableName`, `controlId`) alongside `action` and `options`.
*   Refer to the `protocol.md` document for the detailed structure of each module's payload.

### 4.4. `ObservableValue` (`observable_value.py`)

*   Wraps *any* Python value (`ObservableValue(initial_value)`).
*   Provides `.subscribe(callback)` to register listeners and returns an `unsubscribe` function.
*   Notifies subscribers when the value changes via `.set()` or intercepted container methods (e.g., `list.append`, `dict.__setitem__`, `set.add`, `dict.update`).
*   The `callback` receives a `change_details` dictionary containing detailed information about the change (`type`, `path`, `value`, `key`, `old_value`, `length`).
*   Direct attribute changes on wrapped objects (e.g., `obs_obj.attr = val`) do **not** trigger notifications automatically. Use `.set()` or `viz.show()` again in such cases.
*   The `type` field in `change_details` corresponds to the Python operation (e.g., "set", "setitem", "append"). Note that the `viz` module translates this into the `action` field in its WebSocket payload.

### 4.5. `Viz` Module Integration (`viz.py`)

*   Visualizes Python variables using `viz.show(name, value)`.
*   Sends an initial `update` message with `action: "set"`, `variableName: name`, and `options` containing the full `valueRepresentation` and `length`.
*   If `value` is an `ObservableValue`, `Viz` subscribes to it using its internal `_handle_observable_update` callback.
*   When the `ObservableValue` notifies a change (`change_details`), `_handle_observable_update` translates this into an `update` WebSocket message with the appropriate `action` (derived from `change_details['type']`), `variableName`, and `options` (containing `path`, `valueRepresentation`, `keyRepresentation`, `length` as needed). This allows the frontend to perform granular updates and highlighting.
*   Uses a helper `_get_representation` to serialize Python data, handling depth/item limits, recursion, and adding the `observableTracked` flag for `ObservableValue` data.

## 5. API Reference

*(Note: All methods sending `update` messages construct payloads with `camelCase` keys and the `action`/`options` structure where applicable).*

### 5.1. Top-Level Functions (`connection.py`)

*   `sidekick.set_url(url: str)`: Sets WebSocket URL (call before module creation).
*   `sidekick.close_connection()`: Manually closes WebSocket connection and cleans up.
*   `sidekick.activate_connection()`: Manually marks the connection as active (usually done by module constructors).
*   `sidekick.get_connection() -> Optional[WebSocket]`: Gets the current connection object (internal use mainly).
*   `sidekick.register_message_handler(id, handler)`: (Internal use mainly).
*   `sidekick.unregister_message_handler(id)`: (Internal use mainly).
*   `sidekick.get_next_command_id() -> int`: Generates a unique ID for commands like Canvas drawing.

### 5.2. `sidekick.ObservableValue`

*   `ObservableValue(initial_value: Any)`
*   `.get() -> Any`: Returns the current internal value.
*   `.set(new_value: Any)`: Sets the value and triggers a `"set"` notification.
*   `.subscribe(callback: Callable[[Dict[str, Any]], None]) -> Callable[[], None]`: Registers a callback for change notifications. Returns an unsubscribe function.
*   `.unsubscribe(callback: Callable[[Dict[str, Any]], None])`: Removes a specific callback.
*   Intercepted Methods (trigger detailed notifications): `.append()`, `.insert()`, `.pop()`, `.remove()` (list), `.clear()`, `.__setitem__()`, `.__delitem__()`, `.update()` (dict - triggers multiple `setitem`), `.add()`, `.discard()` (set).
*   Delegated Methods/Attributes (`__getattr__`, `__len__`, etc.): Access features of the wrapped value (does *not* trigger notifications).

### 5.3. `sidekick.Grid`

*   `Grid(width: int, height: int, instance_id: Optional[str] = None, on_message: Optional[Callable] = None)`: Creates a grid. `on_message` handles click notifications (`{'event': 'click', 'x': ..., 'y': ...}`).
*   `.set_color(x: int, y: int, color: Optional[str])`: Sets cell background color. Sends `action: "setCell"`. `None` clears color.
*   `.set_text(x: int, y: int, text: Optional[str])`: Sets cell text. Sends `action: "setCell"`. `None` or `""` clears text.
*   `.clear()`: Clears the entire grid (all cells to default). Sends `action: "clear"`.
*   `.remove()`: Removes the grid module.

### 5.4. `sidekick.Console`

*   `Console(instance_id: Optional[str] = None, initial_text: str = "", on_message: Optional[Callable] = None)`: Creates a console. `on_message` handles input submissions (`{'event': 'submit', 'value': ...}`).
*   `.print(*args, sep=' ', end='')`: Appends text to the console. Sends `action: "append"`.
*   `.log(message: Any)`: Convenience method for `.print(message)`.
*   `.clear()`: Clears the console output. Sends `action: "clear"`.
*   `.remove()`: Removes the console module.

### 5.5. `sidekick.Viz`

*   `Viz(instance_id: Optional[str] = None)`: Creates a variable visualizer panel.
*   `.show(name: str, value: Any)`: Displays/updates a variable. Sends `action: "set"`. Auto-subscribes to `ObservableValue`.
*   `.remove_variable(name: str)`: Removes a variable display. Sends `action: "removeVariable"`. Unsubscribes if applicable.
*   `.remove()`: Removes the Viz panel and cleans up all variables/subscriptions.

### 5.6. `sidekick.Canvas`

*   `Canvas(width: int, height: int, bg_color: Optional[str] = None, instance_id: Optional[str] = None)`: Creates a drawing canvas.
*   `._send_canvas_command(action: str, options: Optional[Dict] = None)`: Internal helper sending `update` payload with `action`, `options`, and unique `commandId`.
*   `.clear(color: Optional[str] = None)`: Clears the canvas. Sends `action: "clear"`.
*   `.config(stroke_style: Optional[str], fill_style: Optional[str], line_width: Optional[int])`: Configures drawing styles. Sends `action: "config"`. Keys in `options` are `strokeStyle`, `fillStyle`, `lineWidth`.
*   `.draw_line(x1, y1, x2, y2)`: Draws a line. Sends `action: "line"`.
*   `.draw_rect(x, y, width, height, filled: bool = False)`: Draws a rectangle. Sends `action: "rect"`.
*   `.draw_circle(cx, cy, radius, filled: bool = False)`: Draws a circle. Sends `action: "circle"`.
*   `.remove()`: Removes the canvas module.

### 5.7. `sidekick.Control`

*   `Control(instance_id: Optional[str] = None, on_message: Optional[Callable] = None)`: Creates a panel for dynamic controls. `on_message` handles interaction notifications (`{'event': 'click'/'submit', 'controlId': ..., 'value'?: ...}`).
*   `.add_button(control_id: str, text: str)`: Adds a button. Sends `action: "add"`.
*   `.add_text_input(control_id: str, placeholder: str = "", initial_value: str = "", button_text: str = "Submit")`: Adds a text input with button. Sends `action: "add"`. Uses `initialValue`, `buttonText` in config.
*   `.remove_control(control_id: str)`: Removes a specific control. Sends `action: "remove"`.
*   `.remove()`: Removes the control panel module.

## 6. Development Notes

*   **Structure:** Code in `libs/python/src/sidekick/`. Key files: `connection.py`, `base_module.py`, `observable_value.py`, `viz.py`, `grid.py`, `console.py`, `canvas.py`, `control.py`, `utils.py`.
*   **Dependencies:** `websocket-client`. See `pyproject.toml`.
*   **Payload Keys:** Remember that all keys within the `payload` dictionary sent via `_send_command` or `_send_update` **must be camelCase** to match the protocol and frontend expectations. Python method parameters use `snake_case`.

## 7. Troubleshooting

*   **Connection Errors:** Check server status, URL (`ws://localhost:5163`), firewalls. Enable DEBUG logging for `SidekickConn`.
*   **Module Not Appearing/Updating:** Verify `instance_id`/`target_id` match. Check Python logs (`DEBUG` level) for sent messages. Check browser console for errors in the frontend reducer or component rendering. Ensure payload keys are `camelCase`.
*   **Viz Not Auto-Updating:** Ensure you passed an `ObservableValue` to `viz.show()`. Ensure changes are made via `.set()` or intercepted methods (not direct attribute mutation). Check Python logs for `_handle_observable_update` calls and subsequent WebSocket messages. Check browser console for errors in `updateRepresentationAtPath`.
*   **Callbacks Not Firing:** Ensure `on_message` was passed correctly during module creation. Check Python `DEBUG` logs for received `notify` messages and whether the correct handler is invoked. Check callback implementation for errors.
*   **Canvas Drawing Issues:** Verify `commandId` is being sent (check `DEBUG` logs). Check browser console for errors in `CanvasModule.tsx`'s command processing loop.