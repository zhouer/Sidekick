# Sidekick Python Library (`sidekick`)

## 1. Overview

This library provides the Python interface ("Hero") for interacting with the Sidekick Visual Coding Buddy frontend UI. It allows Python scripts to easily create, update, interact with, and remove visual modules like grids, consoles, variable visualizers, and drawing canvases within the Sidekick UI.

It abstracts the underlying WebSocket communication and message formatting, offering an intuitive object-oriented API.

## 2. Features

*   **Object-Oriented API:** Control visual modules (`Grid`, `Console`, `Viz`, `Canvas`) via Python classes and methods.
*   **`ObservableValue`:** A general-purpose wrapper to track changes in Python values (primitives or containers). Notifies subscribers with detailed change information (type, path, new value).
*   **Automatic WebSocket Management:** Handles connection, keep-alive (Ping/Pong), and `atexit` cleanup.
*   **Callback Handling:** Supports receiving notifications (e.g., grid clicks, console input) via user-provided callback functions.
*   **Structured Data Visualization:** `Viz` module provides detailed, expandable views of complex Python data structures, reacting to granular changes from `ObservableValue`.

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

*   **Singleton:** Manages a single, shared WebSocket connection (`ws://localhost:5163` by default).
*   **Lazy Connection:** Connects automatically on the first relevant action (usually module creation).
*   **Configuration:** Use `sidekick.set_url(url)` *before* creating modules to change the target server.
*   **Keep-Alive:** Uses WebSocket Ping/Pong for connection maintenance and failure detection.
*   **Listener Thread:** A background thread listens for incoming messages from Sidekick.
*   **Cleanup:** `atexit` handler ensures graceful connection closure.

### 4.2. Visual Modules (`grid.py`, `console.py`, `viz.py`, `canvas.py`)

*   Represented by Python classes (`Grid`, `Console`, `Viz`, `Canvas`).
*   **Lifecycle:** Instantiation (`spawn`), method calls (`update`), `.remove()` (`remove`).
*   **Identification:** Each instance uses a unique `target_id`.

### 4.3. `ObservableValue` (`observable_value.py`)

*   Standalone wrapper for *any* Python value (`ObservableValue(initial_value)`).
*   Notifies subscribers (`subscribe(callback)`) when the value changes.
*   **Detailed Notifications:** The callback function receives a dictionary containing details about the change, including:
    *   `type`: The type of operation (e.g., `"set"`, `"setitem"`, `"append"`, `"clear"`).
    *   `path`: A list representing the index/key path to the changed element (empty for root changes).
    *   `value`: The new value (or the element added/inserted).
    *   `key`: The dictionary key involved (for dict operations).
    *   `length`: The new length of the container (if applicable).
    *   `old_value`: The previous value (optional, where available).
*   Changes via `.set(new_value)` or intercepted methods (like `.append()`, `__setitem__()`, `.add()`) trigger these detailed notifications.
*   Attribute changes on wrapped objects (e.g., `obs_obj.attr = val`) do **not** trigger notifications automatically.

### 4.4. `Viz` Module Integration (`viz.py`)

*   Visualizes Python variables using `viz.show(name, value)`. This sends an initial `"set"` update message.
*   If `value` is an `ObservableValue`, `Viz` subscribes to it.
*   When the `ObservableValue` notifies a change, `Viz` receives the detailed change dictionary and translates it into a corresponding `update` message for the Sidekick frontend, including the `change_type`, `path`, and relevant value representations. This allows the frontend to potentially highlight the specific part that changed.
*   Uses `_get_representation` to serialize Python data structures (including the internal value of observables) for the frontend, adding type info, unique IDs, and the `observable_tracked` flag.

### 4.5. Callbacks (`connection.py`, `grid.py`, `console.py`)

*   `Grid` and `Console` accept an `on_message` callback during initialization for user interactions from the Sidekick UI.
*   The listener thread invokes the correct callback when a `notify` message (e.g., grid click, console submit) arrives from Sidekick. (This is distinct from `ObservableValue` callbacks).

## 5. API Reference

### 5.1. Top-Level Functions

*   `sidekick.set_url(url: str)`: Sets WebSocket URL (call before module creation).
*   `sidekick.close_connection()`: Manually closes WebSocket connection.

### 5.2. `sidekick.ObservableValue`

*   `ObservableValue(initial_value: Any)`
*   `.get() -> Any`
*   `.set(new_value: Any)`: Sets the value and triggers a `"set"` notification.
*   `.subscribe(callback: Callable[[Dict[str, Any]], None]) -> Callable[[], None]`: Registers a callback to receive detailed change dictionaries. Returns an unsubscribe function.
*   `.unsubscribe(callback: Callable[[Dict[str, Any]], None])`: Removes a callback.
*   Intercepted Methods (trigger detailed notifications like `"append"`, `"setitem"`, `"add_set"`, etc.): `.append()`, `.insert()`, `.pop()`, `.remove()`, `.clear()`, `__setitem__()`, `__delitem__()`, `.update()` (triggers multiple `setitem`), `.add()`, `.discard()`.
*   Delegated Methods/Attributes: Accesses other features of the wrapped value (does not trigger notifications).

### 5.3. `sidekick.Grid`

*   `Grid(width: int, height: int, instance_id: Optional[str] = None, on_message: Optional[Callable[[Dict[str, Any]], None]] = None)`
    *   `on_message`: Handles grid notifications (clicks).
*   `.set_color(x, y, color)`, `.set_text(x, y, text)`, `.clear_cell(x, y)`, `.fill(color)`, `.remove()`

### 5.4. `sidekick.Console`

*   `Console(instance_id: Optional[str] = None, initial_text: str = "", on_message: Optional[Callable[[Dict[str, Any]], None]] = None)`
    *   `on_message`: Handles console notifications (user input).
*   `.print(*args, sep=' ', end='')`, `.log(message)`, `.clear()`, `.remove()`

### 5.5. `sidekick.Viz`

*   `Viz(instance_id: Optional[str] = None)`
*   `.show(name: str, value: Any)`: Displays a variable, sending a full `"set"` update. Auto-subscribes to `ObservableValue`.
*   `.remove_variable(name: str)`: Removes a variable display by sending an `update` message with `change_type: "remove_variable"`. Also unsubscribes if the variable was an `ObservableValue`.
*   `.remove()`: Removes the Viz panel and cleans up all associated variables/subscriptions.

### 5.6. `sidekick.Canvas`

*   `Canvas(width: int, height: int, bg_color: Optional[str] = None, instance_id: Optional[str] = None)`
*   `.clear(color: Optional[str] = None)`
*   `.config(stroke_style: Optional[str], fill_style: Optional[str], line_width: Optional[int])`
*   `.draw_line(x1, y1, x2, y2)`
*   `.draw_rect(x, y, width, height, filled: bool = False)`
*   `.draw_circle(cx, cy, radius, filled: bool = False)`
*   `.remove()`

## 6. Basic Usage Example

```python
import time
from sidekick import Console, Viz, ObservableValue, set_url

# Optional: Set URL if not default
# set_url("ws://...")

# Define a callback for console input
def process_console_input(msg):
    if msg.get('payload', {}).get('event') == 'submit':
        text = msg['payload']['value']
        console.print(f"You typed: {text.upper()}")
        if text == 'inc':
            # counter.set triggers 'set' notification
            counter.set(counter.get() + 1)
        elif text == 'add':
            # obs_list.append triggers 'append' notification
            obs_list.append(len(obs_list) + 10)
        elif text == 'change':
             # obs_dict['a'] triggers 'setitem' notification
             obs_dict['a'] = obs_dict['a'] + 1

# Optional: Define a callback for ObservableValue changes (if needed beyond Viz)
# def handle_counter_change(change_details):
#     print(f"Counter Changed: {change_details}")

try:
    console = Console(on_message=process_console_input)
    viz = Viz()

    console.log("Sidekick ready.")
    console.print("Commands: 'inc', 'add', 'change'")

    # Track a primitive
    counter = ObservableValue(0)
    # viz.show subscribes Viz's internal handler
    viz.show("counter", counter)
    # You could also subscribe your own handler:
    # unsubscribe_counter = counter.subscribe(handle_counter_change)

    # Track a list
    obs_list = ObservableValue([10, 20])
    viz.show("observed_list", obs_list)

    # Track a dictionary
    obs_dict = ObservableValue({'a': 1, 'b': 2})
    viz.show("observed_dict", obs_dict)


    # Keep script running (callbacks work in background thread)
    while True:
        time.sleep(5)
        # Example of non-observable update (need explicit show)
        # normal_var = time.time()
        # viz.show("current_time", normal_var)

except KeyboardInterrupt:
    print("Exiting...")
except Exception as e:
    print(f"An error occurred: {e}")

finally:
    # Clean up (optional, connection closes via atexit)
    # if 'unsubscribe_counter' in locals(): unsubscribe_counter()
    # viz.remove()
    # console.remove()
    print("Script finished.")
```

## 7. Development Notes

*   **Structure:** Code in `libs/python/src/sidekick/`. Key files: `observable_value.py`, `connection.py`, `base_module.py`, `grid.py`, `console.py`, `viz.py`, `canvas.py`.
*   **Dependencies:** `websocket-client`. See `pyproject.toml`.
*   **Packaging:** Uses `setuptools` and `pyproject.toml`. Target PyPI name: `sidekick-py` (tentative).

## 8. Troubleshooting

*   **Connection Errors:** Ensure Sidekick server is running, URL is correct (`ws://localhost:5163` default), check firewalls.
*   **Name Errors:** Check imports (`from sidekick import ...`), ensure library is installed (`pip install -e ./libs/python` or `pip install sidekick-py`).
*   **Visualizations Not Updating:** Check script/server/browser console errors. For `Viz` + `ObservableValue`, ensure changes use `.set()` or intercepted methods (`.append`, `[]=` etc.). Attribute changes on wrapped objects (e.g., `my_obj.attr = 1`) are *not* tracked automatically and require `viz.show()` again. Verify the detailed update messages are being sent (check Python logs if DEBUG level is enabled).
*   **Incorrect Highlighting:** Ensure the frontend (`VizModule.tsx`) correctly parses the `path` from the update message and applies highlighting based on path matching. Check CSS animation definitions.
*   **Callbacks Not Firing:** Ensure `on_message` was passed correctly during `Grid`/`Console` initialization for UI interactions. For `ObservableValue`, ensure `.subscribe()` was called and the modifying action is one that triggers notifications. Check script terminal for callback print statements/errors.
*   **WebSocket Disconnecting:** Check network intermediaries. Examine logs from `connection.py` for Ping timeouts or other errors.