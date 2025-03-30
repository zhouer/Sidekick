# Sidekick Python Library (`sidekick`)

## 1. Overview

This library provides the Python interface ("Hero") for interacting with the Sidekick Visual Coding Buddy frontend UI. It allows Python scripts to easily create, update, interact with, and remove visual modules like grids, consoles, variable visualizers, and drawing canvases within the Sidekick UI.

It abstracts the underlying WebSocket communication and message formatting, offering an intuitive object-oriented API.

## 2. Features

*   **Object-Oriented API:** Control visual modules (`Grid`, `Console`, `Viz`, `Canvas`) via Python classes and methods.
*   **`ObservableValue`:** A general-purpose wrapper to track changes in Python values (primitives or containers). `Viz` module automatically subscribes to shown `ObservableValue`s for live updates.
*   **Automatic WebSocket Management:** Handles connection, keep-alive (Ping/Pong), and `atexit` cleanup.
*   **Callback Handling:** Supports receiving notifications (e.g., grid clicks, console input) via user-provided callback functions.
*   **Structured Data Visualization:** `Viz` module provides detailed, expandable views of complex Python data structures.

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
*   Changes via `.set(new_value)` (for primitives/replacement) or intercepted methods (for list/dict/set like `.append()`, `__setitem__()`, `.add()`) trigger notifications.
*   Attribute changes on wrapped objects (e.g., `obs_obj.attr = val`) do **not** trigger notifications automatically.

### 4.4. `Viz` Module Integration (`viz.py`)

*   Visualizes Python variables using `viz.show(name, value)`.
*   If `value` is an `ObservableValue`, `Viz` subscribes to it and automatically sends updates to the frontend when the observable notifies a change.
*   Uses `_get_representation` to serialize data for the frontend, including type info, unique node IDs, and the `observable_tracked` flag.

### 4.5. Callbacks (`connection.py`, `grid.py`, `console.py`)

*   `Grid` and `Console` accept an `on_message` callback during initialization.
*   The listener thread invokes the correct callback when a `notify` message (e.g., grid click, console submit) arrives from Sidekick.

## 5. API Reference

### 5.1. Top-Level Functions

*   `sidekick.set_url(url: str)`: Sets WebSocket URL (call before module creation).
*   `sidekick.close_connection()`: Manually closes WebSocket connection.

### 5.2. `sidekick.ObservableValue`

*   `ObservableValue(initial_value: Any)`
*   `.get() -> Any`
*   `.set(new_value: Any)`
*   `.subscribe(callback: Callable[[Any], None]) -> Callable[[], None]`
*   `.unsubscribe(callback: Callable[[Any], None])`
*   Intercepted Methods (list/dict/set): `.append()`, `.insert()`, `.pop()`, `.remove()`, `.clear()`, `__setitem__()`, `__delitem__()`, `.update()`, `.add()`, `.discard()`.
*   Delegated Methods/Attributes: Accesses other features of the wrapped value.

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
*   `.show(name: str, value: Any)`: Displays a variable. Auto-subscribes to `ObservableValue`.
*   `.remove_variable(name: str)`: Removes a variable display.
*   `.remove()`: Removes the Viz panel.

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
from sidekick import Console, Viz, ObservableValue

# Define a callback for console input
def process_input(msg):
    if msg['payload']['event'] == 'submit':
        text = msg['payload']['value']
        console.print(f"You typed: {text.upper()}")
        if text == 'inc':
            counter.set(counter.get() + 1)

try:
    console = Console(on_message=process_input) # Pass callback
    viz = Viz()

    console.log("Sidekick ready. Type 'inc' to increment counter.")

    # Track a primitive
    counter = ObservableValue(0)
    viz.show("counter", counter)

    # Keep script running (callbacks work in background thread)
    while True:
        time.sleep(10)

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    print("Script finished.")
```

## 7. Development Notes

*   **Structure:** Code in `libs/python/src/sidekick/`. Key files: `observable_value.py`, `connection.py`, `base_module.py`, `grid.py`, `console.py`, `viz.py`, `canvas.py`.
*   **Dependencies:** `websocket-client`. See `pyproject.toml`.
*   **Packaging:** Uses `setuptools` and `pyproject.toml`. Target PyPI name: `sidekick-py`.

## 8. Troubleshooting

*   **Connection Errors:** Ensure Sidekick server is running, URL is correct, check firewalls.
*   **Name Errors:** Check imports (`from sidekick import ...`), ensure library is installed (`pip install -e .` or `pip install sidekick-py`).
*   **Visualizations Not Updating:** Check script/server/browser console errors. For `Viz` + `ObservableValue`, ensure changes use `.set()` or intercepted methods. Attribute changes on wrapped objects need `viz.show()` to be called again.
*   **Callbacks Not Firing:** Ensure `on_message` was passed correctly during module initialization. Check server/browser logs for `notify` messages. Check script terminal for callback print statements/errors.
*   **WebSocket Disconnecting:** Check network intermediaries. Examine logs from `connection.py` for Ping timeouts.