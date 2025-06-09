# Sidekick Python Library - User Guide

Welcome to the Sidekick Python Library! This guide will walk you through everything you need to know to use Sidekick to bring your Python code to life with interactive visualizations.

**Table of Contents**

*   [Chapter 1: Getting Started with Sidekick](#chapter-1-getting-started-with-sidekick)
    *   [1.1 What is Sidekick?](#11-what-is-sidekick)
    *   [1.2 Installation](#12-installation)
    *   [1.3 Your First Sidekick Program](#13-your-first-sidekick-program)
    *   [1.4 Sidekick Basic Concepts](#14-sidekick-basic-concepts)
*   [Chapter 2: Sidekick Core Components](#chapter-2-sidekick-core-components)
    *   [2.1 `Grid` - Interactive Grid](#21-grid---interactive-grid)
    *   [2.2 `Console` - Text Console](#22-console---text-console)
    *   [2.3 `Canvas` - 2D Drawing Surface](#23-canvas---2d-drawing-surface)
    *   [2.4 `Viz` - Data Structure Visualizer](#24-viz---data-structure-visualizer)
    *   [2.5 `Label` - Text Label](#25-label---text-label)
    *   [2.6 `Button` - Clickable Button](#26-button---clickable-button)
    *   [2.7 `Textbox` - Single-Line Text Input](#27-textbox---single-line-text-input)
    *   [2.8 `Markdown` - Markdown Renderer](#28-markdown---markdown-renderer)
*   [Chapter 3: Handling User Interactions (Events)](#chapter-3-handling-user-interactions-events)
    *   [3.1 Event Handling Fundamentals](#31-event-handling-fundamentals)
    *   [3.2 Registering Event Handlers](#32-registering-event-handlers)
    *   [3.3 Common Event Handling Examples](#33-common-event-handling-examples)
    *   [3.4 Handling Component Errors (`on_error`)](#34-handling-component-errors-on_error)
*   [Chapter 4: Layout Management](#chapter-4-layout-management)
    *   [4.1 Layout Containers: `Row` and `Column`](#41-layout-containers-row-and-column)
    *   [4.2 Adding Components to Layouts](#42-adding-components-to-layouts)
    *   [4.3 Nested Layouts](#43-nested-layouts)
    *   [4.4 Declarative Layout Style Examples](#44-declarative-layout-style-examples)
*   [Chapter 5: Advanced Features](#chapter-5-advanced-features)
    *   [5.1 Reactive `Viz` with `ObservableValue`](#51-reactive-viz-with-observablevalue)
    *   [5.2 `Canvas` Double Buffering for Smooth Animations](#52-canvas-double-buffering-for-smooth-animations)
    *   [5.3 `sidekick.submit_task()` for Background Coroutines](#53-sidekicksubmit_task-for-background-coroutines)
    *   [5.4 `sidekick.submit_interval()` for Periodic Tasks & Animations](#54-sidekicksubmit_interval-for-periodic-tasks--animations)
    *   [5.5 `await sidekick.run_forever_async()` for Pyodide](#55-await-sidekickrun_forever_async-for-pyodide)
    *   [5.6 Custom Connection (`sidekick.set_url`)](#56-custom-connection-sidekickset_url)
    *   [5.7 Clearing the UI](#57-clearing-the-ui)
*   [Chapter 6: Sidekick Python API Reference](#chapter-6-sidekick-python-api-reference)
    *   [6.1 Global Functions](#61-global-functions)
    *   [6.2 Component Base Class (`sidekick.Component`)](#62-component-base-class-sidekickcomponent)
    *   [6.3 Core Visualization Components API](#63-core-visualization-components-api)
    *   [6.4 UI Input/Display Components API](#64-ui-inputdisplay-components-api)
    *   [6.5 Layout Components API](#65-layout-components-api)
    *   [6.6 Event Objects](#66-event-objects)
    *   [6.7 `sidekick.ObservableValue` API](#67-sidekickobservablevalue-api)
    *   [6.8 Exception Classes](#68-exception-classes)
*   [Chapter 7: Troubleshooting and Help](#chapter-7-troubleshooting-and-help)
    *   [7.1 Frequently Asked Questions (FAQ) & Troubleshooting](#71-frequently-asked-questions-faq--troubleshooting)
    *   [7.2 Getting More Help](#72-getting-more-help)

---

## Chapter 1: Getting Started with Sidekick

### 1.1 What is Sidekick?

Sidekick is your friendly visual coding buddy designed to make programming more tangible and less abstract. It provides an **interactive panel** directly within your VS Code editor (or as a standalone web app) where your Python code can create visualizations, display data, and respond to user input in real-time.

**Core Ideas:**

*   **See Your Code:** Watch loops draw patterns, data structures change, and algorithms execute step-by-step.
*   **Interactive Learning:** Perfect for learners, educators, parents teaching coding, and anyone who benefits from seeing code in action.
*   **Simplified UI:** Focus on programming logic, not complex UI framework details. Sidekick offers an intuitive, Pythonic API.
*   **Integrated Experience:** Visualize and interact without leaving your development environment.

### 1.2 Installation

To use Sidekick, you need two main parts: the Python library and the VS Code extension (recommended for the best experience).

1.  **Install the Python Library:**
    Open your terminal or command prompt and run:
    ```shell
    pip install sidekick-py
    ```

2.  **Install the VS Code Extension:**
    *   Open Visual Studio Code.
    *   Go to the Extensions view (Ctrl+Shift+X or Cmd+Shift+X).
    *   Search for "Sidekick - Your Visual Coding Buddy".
    *   Click "Install".

    *(Optional Cloud Connection: If you're unable to use the VS Code extension or are running your Python script in an environment where it can't connect locally, Sidekick may attempt to connect to a cloud-based relay server. If this happens, the Python library will print a UI URL in your console for you to open in a web browser.)*

### 1.3 Your First Sidekick Program

Let's create a very simple Sidekick program to see it in action.

1.  **Open Sidekick Panel in VS Code:**
    *   Use the command palette (Ctrl+Shift+P or Cmd+Shift+P).
    *   Type `Sidekick: Show Panel` and select it.
    *   The Sidekick panel should appear, typically beside your editor.

2.  **Create a Python file** (e.g., `hello_sidekick.py`) with the following code:

    ```python
    import sidekick
    import time

    # Create a label component
    greeting_label = sidekick.Label("Hello from Sidekick!")
    greeting_label.text = "Preparing to count..."

    # Create a console
    console = sidekick.Console()
    console.print("Script started!")

    # A simple loop to show updates
    for i in range(5):
        greeting_label.text = f"Count: {i+1}"
        console.print(f"Current count is {i+1}")
        time.sleep(1) # Pause for a second

    greeting_label.text = "Done counting!"
    console.print("Script finished.")

    # Always call sidekick.run_forever() at the end of your script if you
    # want the UI to remain visible or interactive after the main logic.
    sidekick.run_forever()
    ```

3.  **Run the Python script:**
    Execute your `hello_sidekick.py` file from your terminal:
    ```shell
    python hello_sidekick.py
    ```
    Or use the "Run Python File" button in VS Code.

4.  **Observe:**
    Look at the Sidekick panel in VS Code. You should see the label text update as the loop runs, and messages appearing in the console area.

### 1.4 Sidekick Basic Concepts

*   **"Hero" and "Sidekick":**
    *   **Hero:** Your Python script using the `sidekick-py` library. It contains the logic and controls what's displayed.
    *   **Sidekick:** The UI panel (in VS Code or browser) that renders the visual components and sends user interactions back to the Hero.

*   **Communication Flow:**
    *   **Command Flow (Python → UI):** When you create a component (e.g., `sidekick.Button()`) or call its methods (e.g., `label.text = "New"`), the Python library sends commands to the Sidekick UI to create or update visual elements.
    *   **Event Flow (UI → Python):** When a user interacts with a component in the UI (e.g., clicks a button), the UI sends an event message back to your Python script, which can then be handled by a callback function you've defined.

*   **`instance_id`:**
    Every Sidekick component has a unique `instance_id`. This ID is crucial for the system to distinguish between different UI elements, especially if you have multiple components of the same type (e.g., several buttons).
    *   You can provide a custom `instance_id` when creating a component:
        ```python
        my_button = sidekick.Button("Submit", instance_id="submit-form-button")
        ```
    *   If you don't provide one, Sidekick will auto-generate a unique ID (e.g., "button-1").
    Event objects received in callbacks will contain the `instance_id` of the component that triggered the event.

*   **Script Lifecycle & Interactivity:**
    *   **Implicit Connection Activation:** When you create your first Sidekick component (e.g., `my_label = sidekick.Label()`) or explicitly call `sidekick.activate_connection()`, the library non-blockingly initiates the connection to a Sidekick service (VS Code extension or cloud relay).
    *   **Waiting for Connection (CPython, Optional):** If your script needs to ensure the connection is fully active *before* proceeding with critical UI interactions, you can call `sidekick.wait_for_connection()`. This function will block the calling thread until the connection is established or fails.
    *   **`sidekick.run_forever()` / `await sidekick.run_forever_async()`:** You **must** call one of these at the end of your script if you want it to handle UI interactions (like button clicks) or if you simply want the Sidekick UI to remain visible after your script's main logic has finished.
        *   `sidekick.run_forever()` (for CPython): Internally calls `sidekick.wait_for_connection()` and then blocks the main thread, keeping your script alive to listen for and process events.
        *   `await sidekick.run_forever_async()` (for Pyodide/asyncio scripts): Asynchronously waits for connection and then keeps the script alive for events.
        Without one of these, your script might finish prematurely, and interactive elements would stop working or UI might disappear. You can typically stop a script running with `run_forever()` by pressing `Ctrl+C` in the terminal.
    *   **`sidekick.shutdown()`:** To programmatically stop the Sidekick connection and allow your script to exit (even if `run_forever()` or `run_forever_async()` was called), you can call `sidekick.shutdown`. This is often used within an event handler, for example, when a "Quit" button is clicked.

---

## Chapter 2: Sidekick Core Components

Sidekick provides several built-in components to visualize data and create simple UIs.

### 2.1 `Grid` - Interactive Grid

Displays and interacts with a 2D grid of cells. Ideal for visualizing maps, game boards, matrices, or simple pixel art.

*   **Constructor:** `Grid(num_columns: int, num_rows: int, instance_id: Optional[str] = None, parent: Optional[Component] = None, on_click: Optional[Callable] = None, ...)`
*   **Key Methods/Properties:**
    *   `set_color(x, y, color)`: Sets the background color of a cell. `color` can be a CSS color string (e.g., 'red', '#FF0000') or `None` to clear.
    *   `set_text(x, y, text)`: Sets the text content of a cell. `text` can be a string or `None` to clear.
    *   `clear_cell(x, y)`: Clears both color and text of a cell.
    *   `clear()`: Clears the entire grid.
    *   `on_click(callback)` / `@grid.click`: Registers a handler for cell clicks (see Chapter 3).
    *   `.num_columns` (read-only): Number of columns.
    *   `.num_rows` (read-only): Number of rows.
*   **Coordinates:** `x` is the 0-based column index (left to right), `y` is the 0-based row index (top to bottom).

**Example:**
```python
import sidekick
import random

grid = sidekick.Grid(5, 5, instance_id="color-grid")

def change_color(event): # event will be a GridClickEvent
    colors = ["khaki", "lavender", "peachpuff", "pink", "plum"]
    grid.set_color(event.x, event.y, random.choice(colors))
    print(f"Cell ({event.x}, {event.y}) clicked!")

grid.on_click(change_color)
grid.set_text(2, 2, "Center")

sidekick.run_forever()
```

### 2.2 `Console` - Text Console

Displays text output, similar to a standard terminal, and optionally provides a field for user text input.

*   **Constructor:** `Console(text: str = "", show_input: bool = False, instance_id: Optional[str] = None, parent: Optional[Component] = None, on_submit: Optional[Callable] = None, ...)`
*   **Key Methods/Properties:**
    *   `print(*args, sep=' ', end='\n')`: Appends text to the console, similar to Python's built-in print.
    *   `clear()`: Removes all text from the console.
    *   `on_submit(callback)` / `@console.submit`: Registers a handler for text submissions if `show_input=True` (see Chapter 3).

**Example:**
```python
import sidekick
import time

log_console = sidekick.Console(show_input=True, instance_id="app-log")

def handle_input(event): # event will be a ConsoleSubmitEvent
    log_console.print(f"You typed: {event.value}")
    if event.value.lower() == "quit":
        sidekick.shutdown()

log_console.on_submit(handle_input)
log_console.print("Welcome! Type 'quit' to exit.")
log_console.print("Logging system ready...")
time.sleep(1)
log_console.print("Component A initialized.")

sidekick.run_forever()
```

### 2.3 `Canvas` - 2D Drawing Surface

Provides a blank rectangular area for programmatic 2D drawing.

*   **Constructor:** `Canvas(width: int, height: int, instance_id: Optional[str] = None, parent: Optional[Component] = None, on_click: Optional[Callable] = None, ...)`
*   **Key Methods/Properties:**
    *   `draw_line(x1, y1, x2, y2, line_color=None, line_width=None)`
    *   `draw_rect(x, y, width, height, fill_color=None, line_color=None, line_width=None)`
    *   `draw_circle(cx, cy, radius, fill_color=None, line_color=None, line_width=None)`
    *   `draw_polygon(points: List[Tuple[int,int]], fill_color=None, ...)`
    *   `draw_ellipse(cx, cy, radius_x, radius_y, fill_color=None, ...)`
    *   `draw_text(x, y, text, text_color=None, text_size=None)`
    *   `clear()`: Clears the entire canvas.
    *   `buffer()`: Context manager for double buffering (see Chapter 5).
    *   `on_click(callback)` / `@canvas.click`: Registers a handler for canvas clicks (see Chapter 3).
    *   `.width`, `.height` (read-only).
*   **Coordinates:** Origin (0,0) is top-left. X increases to the right, Y increases downwards.

**Example:**
```python
import sidekick

drawing_area = sidekick.Canvas(300, 200, instance_id="my-drawing")

# Draw a red diagonal line
drawing_area.draw_line(10, 10, 290, 190, line_color="red", line_width=2)

# Draw a filled blue rectangle
drawing_area.draw_rect(50, 50, 100, 75, fill_color="blue", line_color="darkblue", line_width=3)

# Draw some text
drawing_area.draw_text(60, 150, "Sidekick Canvas!", text_color="green", text_size=20)

# Use run_forever() if you want the canvas to remain visible after the script's main logic.
sidekick.run_forever()
```

### 2.4 `Viz` - Data Structure Visualizer

Displays Python variables (lists, dicts, sets, objects) in an interactive, collapsible tree view.

*   **Constructor:** `Viz(instance_id: Optional[str] = None, parent: Optional[Component] = None, ...)`
*   **Key Methods/Properties:**
    *   `show(name: str, value: Any)`: Displays or updates a variable in the Viz panel.
    *   `remove_variable(name: str)`: Removes a variable from the display.
*   Works best with `ObservableValue` for automatic updates (see Chapter 5).

**Example:**
```python
import sidekick

data_viewer = sidekick.Viz(instance_id="data-inspector")

my_list = [1, 2, {"nested": True, "items": [10, 20]}]
my_dict = {"name": "Sidekick", "version": "0.0.6", "features": ["Grid", "Canvas", "Viz"]}

class MyObject:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.description = "A custom object"

my_obj = MyObject(100, 200)

data_viewer.show("My List Data", my_list)
data_viewer.show("Configuration", my_dict)
data_viewer.show("Custom Object", my_obj)

# To update, call show again (or use ObservableValue)
my_list.append(3)
data_viewer.show("My List Data", my_list) # Re-show to see the '3'

# Keeps the script alive for the Viz panel to remain visible and updatable.
sidekick.run_forever()
```

### 2.5 `Label` - Text Label

Displays a single line of static or dynamic text.

*   **Constructor:** `Label(text: str = "", instance_id: Optional[str] = None, parent: Optional[Component] = None, ...)`
*   **Key Methods/Properties:**
    *   `.text`: Get or set the displayed text.

**Example:**
```python
import sidekick
import time

status_label = sidekick.Label("Status: Initializing...", instance_id="app-status")
time.sleep(1)
status_label.text = "Status: Ready"

# To keep the label visible after the script finishes its main logic:
sidekick.run_forever()
```

### 2.6 `Button` - Clickable Button

Creates a standard clickable button.

*   **Constructor:** `Button(text: str = "", instance_id: Optional[str] = None, parent: Optional[Component] = None, on_click: Optional[Callable] = None, ...)`
*   **Key Methods/Properties:**
    *   `.text`: Get or set the button's label.
    *   `on_click(callback)` / `@button.click`: Registers a handler for button clicks (see Chapter 3).

**Example:**
```python
import sidekick

counter = 0
info_label = sidekick.Label("Counter: 0")

def increment_counter(event): # event is ButtonClickEvent
    global counter
    counter += 1
    info_label.text = f"Counter: {counter}"

action_button = sidekick.Button("Increment", on_click=increment_counter)

sidekick.run_forever()
```

### 2.7 `Textbox` - Single-Line Text Input

A single-line text input field.

*   **Constructor:** `Textbox(value: str = "", placeholder: str = "", instance_id: Optional[str] = None, parent: Optional[Component] = None, on_submit: Optional[Callable] = None, ...)`
*   **Key Methods/Properties:**
    *   `.value`: Get or set the text content.
    *   `.placeholder`: Get or set the placeholder text.
    *   `on_submit(callback)` / `@textbox.submit`: Registers a handler for text submission (Enter/blur) (see Chapter 3).

**Example:**
```python
import sidekick

output_label = sidekick.Label("Type your name below.")
name_input = sidekick.Textbox(placeholder="Enter your name here")

def greet_user(event): # event is TextboxSubmitEvent
    output_label.text = f"Hello, {event.value}!"
    name_input.value = "" # Clear the textbox after submission

name_input.on_submit(greet_user)

sidekick.run_forever()
```

### 2.8 `Markdown` - Markdown Renderer

Displays text formatted with Markdown.

*   **Constructor:** `Markdown(text: str = "", instance_id: Optional[str] = None, parent: Optional[Component] = None, ...)`
*   **Key Methods/Properties:**
    *   `.text`: Get or set the Markdown text.

**Example:**
```python
import sidekick

md_content = """
# Markdown Example
This is a **Sidekick Markdown** component.
- Item 1
- Item 2
"""

md_display = sidekick.Markdown(md_content)
# To update:
# md_display.text = "## New Content\\n*Updated*"

# To keep the Markdown content visible after the script finishes its main logic:
sidekick.run_forever()
```

---

## Chapter 3: Handling User Interactions (Events)

Sidekick components like `Button`, `Grid`, `Canvas`, `Textbox`, and `Console` (with input enabled) can trigger events based on user interactions. Your Python script can respond to these events using callback functions.

### 3.1 Event Handling Fundamentals

*   **Callback Functions:** A callback function is a Python function that you define and then tell Sidekick to execute when a specific event occurs.
*   **Event Objects:** When an event happens, Sidekick calls your callback function and passes it an **event object**. This object contains information about the event, such as:
    *   `instance_id`: The ID of the component instance that triggered the event.
    *   `type`: A string indicating the type of event (e.g., "click", "submit").
    *   **Event-specific data:**
        *   `GridClickEvent`: `.x`, `.y` (cell coordinates)
        *   `CanvasClickEvent`: `.x`, `.y` (click coordinates on canvas)
        *   `TextboxSubmitEvent`, `ConsoleSubmitEvent`: `.value` (the submitted text)
        *   `ErrorEvent`: `.message` (error description)

    You should import these event types from `sidekick.events` for type hinting:
    ```python
    from sidekick.events import ButtonClickEvent, GridClickEvent # etc.
    ```

### 3.2 Registering Event Handlers

There are three main ways to register an event handler for a component:

1.  **Using the `on_<event_name>()` method:**
    This is useful if you create the component first and define the handler later, or if you want to change the handler dynamically.

    ```python
    import sidekick
    from sidekick.events import ButtonClickEvent

    my_button = sidekick.Button("Click Me")
    status_label = sidekick.Label("Status: Waiting")

    def handle_button_click(event: ButtonClickEvent):
        status_label.text = f"Button '{event.instance_id}' clicked!"

    my_button.on_click(handle_button_click) # Register the handler
    sidekick.run_forever()
    ```

2.  **Passing `on_<event_name>` in the constructor:**
    This is convenient for setting the handler when you create the component.

    ```python
    import sidekick
    from sidekick.events import ButtonClickEvent

    status_label = sidekick.Label("Status: Waiting")

    def handle_button_click(event: ButtonClickEvent):
        status_label.text = f"Button '{event.instance_id}' clicked!"

    my_button = sidekick.Button("Click Me", on_click=handle_button_click)
    sidekick.run_forever()
    ```

3.  **Using a decorator (`@component_instance.<event_name>`):**
    This offers a more Pythonic syntax for associating a handler function with a specific component instance's event.

    ```python
    import sidekick
    from sidekick.events import ButtonClickEvent

    my_button = sidekick.Button("Click Me")
    status_label = sidekick.Label("Status: Waiting")

    @my_button.click # Decorator for the 'click' event of 'my_button'
    def handle_button_click(event: ButtonClickEvent):
        status_label.text = f"Button '{event.instance_id}' (decorated) clicked!"

    sidekick.run_forever()
    ```
    Available decorators include:
    *   `@button_instance.click`
    *   `@grid_instance.click`
    *   `@canvas_instance.click`
    *   `@textbox_instance.submit`
    *   `@console_instance.submit`

    To remove a handler set via any of these methods, you can typically call the `on_<event_name>(None)`. For example, `my_button.on_click(None)`.

### 3.3 Common Event Handling Examples

*   **Button Click:**
    ```python
    import sidekick
    from sidekick.events import ButtonClickEvent

    btn = sidekick.Button("Press")
    @btn.click
    def on_btn_press(event: ButtonClickEvent):
        print(f"Button '{event.instance_id}' was pressed.")
    sidekick.run_forever()
    ```

*   **Grid Cell Click:**
    ```python
    import sidekick
    from sidekick.events import GridClickEvent

    game_board = sidekick.Grid(3, 3)
    @game_board.click
    def on_cell_select(event: GridClickEvent):
        game_board.set_text(event.x, event.y, "X")
        print(f"Grid cell ({event.x}, {event.y}) selected.")
    sidekick.run_forever()
    ```

*   **Textbox Submission:**
    ```python
    import sidekick
    from sidekick.events import TextboxSubmitEvent

    user_cmd_box = sidekick.Textbox(placeholder="Enter command...")
    @user_cmd_box.submit
    def process_command(event: TextboxSubmitEvent):
        print(f"Command received: {event.value}")
        user_cmd_box.value = "" # Clear after submit
    sidekick.run_forever()
    ```

### 3.4 Handling Component Errors (`on_error`)

Sometimes, an error might occur in the Sidekick UI related to a specific component (e.g., while trying to render it or process an update command received from your Python script). The UI can send an "error" message back to your Python script. You can handle these using the `on_error` parameter in the component's constructor or by calling the `component.on_error(callback)` method.

The callback receives an `ErrorEvent` object, which has an `instance_id`, `type` (always "error"), and a `message` string describing the error encountered by the UI.

```python
import sidekick
from sidekick.events import ErrorEvent

def my_component_error_handler(event: ErrorEvent):
    print(f"ERROR from Sidekick UI for component '{event.instance_id}': {event.message}")

# Example: Registering error handler for a label
error_prone_label = sidekick.Label("Initial text", on_error=my_component_error_handler)

# This example primarily shows how to *register* the handler.
# Triggering a UI-side error from Python for demonstration is complex.
# Such errors usually stem from issues in the UI's processing of valid commands,
# or potentially from protocol violations if the library itself had a bug.

sidekick.run_forever()
```

---

## Chapter 4: Layout Management

Sidekick provides `Row` and `Column` container components to help you arrange other components in the UI panel.

### 4.1 Layout Containers: `Row` and `Column`

*   **`sidekick.Row()`:** Arranges its child components horizontally, from left to right.
*   **`sidekick.Column()`:** Arranges its child components vertically, from top to bottom.

The main Sidekick panel area (the root container) implicitly behaves like a `Column`.

### 4.2 Adding Components to Layouts

You can add components (children) to `Row` or `Column` containers in several ways:

1.  **Using the container's `add_child(component)` method:**
    Create the child component and the container separately, then add the child to the container.

    ```python
    import sidekick

    my_row = sidekick.Row(instance_id="button-bar")
    button1 = sidekick.Button("Button 1")
    button2 = sidekick.Button("Button 2")

    my_row.add_child(button1)
    my_row.add_child(button2)
    sidekick.run_forever()
    ```

2.  **Specifying `parent=container_instance` in the child's constructor:**
    When creating a child component, you can tell it which container it belongs to.

    ```python
    import sidekick

    my_column = sidekick.Column(instance_id="main-content")
    title_label = sidekick.Label("My App", parent=my_column)
    data_grid = sidekick.Grid(5, 5, parent=my_column)
    sidekick.run_forever()
    ```

3.  **Passing child components directly to the container's constructor:**
    This is often the most concise and "declarative" way.

    ```python
    import sidekick

    # Method 3a: Pass existing component instances
    btn_ok = sidekick.Button("OK")
    btn_cancel = sidekick.Button("Cancel")
    action_row = sidekick.Row(btn_ok, btn_cancel, instance_id="actions")

    # Method 3b: Create and pass components inline (very common)
    info_column = sidekick.Column(
        sidekick.Label("Information Section"),
        sidekick.Markdown("Some *details* here..."),
        instance_id="info-area"
    )
    sidekick.run_forever()
    ```

### 4.3 Nested Layouts

You can nest layout containers within each other to create more complex UI structures.

```python
import sidekick

app_layout = sidekick.Column(
    sidekick.Label("Application Dashboard", instance_id="title"),
    sidekick.Row( # First row for controls
        sidekick.Button("Load Data", instance_id="load-btn"),
        sidekick.Button("Save Data", instance_id="save-btn"),
        instance_id="control-row"
    ),
    sidekick.Grid(10, 10, instance_id="main-display-grid"), # Main display area
    sidekick.Row( # Bottom status row
        sidekick.Label("Status:", instance_id="status-prefix"),
        sidekick.Label("Ready", instance_id="status-text"),
        instance_id="status-bar"
    ),
    instance_id="app-root-column"
)

sidekick.run_forever() # Essential for running Sidekick applications
```

### 4.4 Declarative Layout Style Examples

The ability to pass child components directly to container constructors allows for a very readable, declarative style of UI definition, similar to how UI might be defined in some frontend frameworks.

**Example 1: Simple Form**

```python
import sidekick
from sidekick.events import TextboxSubmitEvent, ButtonClickEvent

name_field = sidekick.Textbox(placeholder="Your Name")
email_field = sidekick.Textbox(placeholder="Your Email")
submit_button = sidekick.Button("Submit")

@submit_button.click
def handle_submit(event: ButtonClickEvent):
    print(f"Name: {name_field.value}, Email: {email_field.value}")
    name_field.value = ""
    email_field.value = ""

form_layout = sidekick.Column(
    sidekick.Label("Contact Form"),
    sidekick.Row(
        sidekick.Label("Name:"),
        name_field  # Use the reference
    ),
    sidekick.Row(
        sidekick.Label("Email:"),
        email_field  # Use the reference
    ),
    submit_button  # Use the reference
)

sidekick.run_forever()
```

**Example 2: Combining multiple event handling styles**
```python
import sidekick
from sidekick.events import ButtonClickEvent

def callback_for_b(event: ButtonClickEvent):
    print(f"Button B ({event.instance_id}) clicked!")

app_ui = sidekick.Row(
    sidekick.Button("Button A", on_click=lambda e: print(f"Button A ({e.instance_id}) clicked!")),
    sidekick.Button("Button B", on_click=callback_for_b)
)

button_c = sidekick.Button("Button C")
@button_c.click
def button_c_action(event: ButtonClickEvent):
    print(f"Button C ({event.instance_id}) clicked via decorator!")

# Add button_c to the existing row or a new one
app_ui.add_child(button_c) # Assuming Row is the main container here.

sidekick.run_forever()
```

This "declarative" style, especially when constructing the UI tree in one go, can make the overall structure very clear.

---

## Chapter 5: Advanced Features

### 5.1 Reactive `Viz` with `ObservableValue`

The `sidekick.Viz` component is powerful for inspecting data, but it becomes truly dynamic when used with `sidekick.ObservableValue`.

`ObservableValue` is a wrapper around Python lists, dictionaries, or sets. When you modify the data *through* the `ObservableValue` wrapper, it automatically notifies any subscribed `Viz` component, causing the `Viz` panel to update its display in real-time, often highlighting the changes.

1.  **Wrap your data:**
    ```python
    my_list = [10, 20]
    observable_list = sidekick.ObservableValue(my_list)

    my_dict = {"a": 1}
    observable_dict = sidekick.ObservableValue(my_dict)
    ```

2.  **Show it in Viz:**
    ```python
    import sidekick
    viz_panel = sidekick.Viz()
    viz_panel.show("My Reactive List", observable_list)
    viz_panel.show("My Reactive Dict", observable_dict)
    ```

3.  **Modify through the wrapper:**
    ```python
    # For lists
    observable_list.append(30)       # Viz updates
    observable_list[0] = 99          # Viz updates
    del observable_list[1]         # Viz updates (using __delitem__)
    observable_list.insert(0, 5)   # Viz updates
    observable_list.pop()            # Viz updates
    observable_list.remove(99)       # Viz updates

    # For dictionaries
    observable_dict["b"] = 2         # Viz updates
    observable_dict.update({"c": 3, "a": 100}) # Viz updates for each change
    del observable_dict["a"]       # Viz updates

    # For sets (similar methods like .add(), .discard())
    my_set_data = {1, 2}
    observable_set = sidekick.ObservableValue(my_set_data)
    viz_panel.show("My Reactive Set", observable_set)
    observable_set.add(3)            # Viz updates
    observable_set.discard(1)        # Viz updates
    ```

**Important:**
*   Modifications must be made using the `ObservableValue` wrapper's methods (e.g., `observable_list.append()`, not `my_list.append()`).
*   If `ObservableValue` contains nested mutable structures (e.g., a list inside an observed dictionary), those nested structures also need to be wrapped in `ObservableValue` if you want their internal changes to be automatically reflected. For example:
    ```python
    nested_data = sidekick.ObservableValue({
        "config": sidekick.ObservableValue({"options": sidekick.ObservableValue([1, 2])})
    })
    viz_panel.show("Nested Reactive", nested_data)
    nested_data["config"]["options"].append(3) # This will trigger UI updates
    ```

    Call `sidekick.run_forever()` if your script needs to stay alive for these updates to be processed and shown after the main logic.

### 5.2 `Canvas` Double Buffering for Smooth Animations

When creating animations or drawing multiple shapes rapidly on a `Canvas`, drawing each element directly to the screen can cause flickering. Double buffering solves this.

Sidekick's `Canvas` provides a `buffer()` context manager:
1.  All drawing commands within the `with canvas.buffer() as buf:` block are performed on a hidden, off-screen buffer.
2.  When the `with` block exits, the entire content of this hidden buffer is drawn to the visible canvas at once.

This results in smoother, flicker-free graphics. For animations, the recommended approach is to use `sidekick.submit_interval()` to repeatedly call a function that draws a single frame.

```python
import sidekick
import math

canvas = sidekick.Canvas(200, 200)
radius = 20
angle = 0

# This function will be called repeatedly to draw each animation frame.
def render_frame():
    global angle
    # Use the buffer context manager for smooth, flicker-free drawing.
    with canvas.buffer() as frame:
        frame.draw_rect(0, 0, 200, 200, fill_color="white")

        # Calculate new ball position for a simple circular motion
        ball_x = 100 + 50 * math.cos(angle)
        ball_y = 100 + 50 * math.sin(angle)
        frame.draw_circle(int(ball_x), int(ball_y), radius, fill_color="blue")

        angle += 0.1  # Increment angle for next frame

# Schedule render_frame to be called approximately 20 times per second.
sidekick.submit_interval(render_frame, 1/20)

# Keep the script running so the interval task can execute.
sidekick.run_forever()
```

### 5.3 `sidekick.submit_task()` for Background Coroutines

If you need to run a background asynchronous task (a coroutine) that runs concurrently with Sidekick's operations and your main script logic, you can use `sidekick.submit_task()`. This is useful for tasks that involve `await asyncio.sleep()` or other asynchronous I/O operations without blocking the entire Sidekick service.

```python
import sidekick
import asyncio

console = sidekick.Console()

async def my_background_task():
    console.print("Background task started.")
    for i in range(3):
        await asyncio.sleep(2) # Non-blocking sleep
        console.print(f"Background task reporting: Tick {i+1}")
    console.print("Background task finished.")

# Submit the coroutine to Sidekick's managed event loop.
sidekick.submit_task(my_background_task())

console.print("Main script continues to run while background task executes.")
sidekick.run_forever()
```

### 5.4 `sidekick.submit_interval()` for Periodic Tasks & Animations

For tasks that need to run repeatedly at a regular interval, such as animations or periodic status checks, `sidekick.submit_interval(callback, interval)` is the perfect tool. It's a convenient wrapper around `submit_task` that handles the timing loop for you.

*   `callback`: The function (or coroutine) to call at each interval.
*   `interval`: The time in seconds between calls. For 60 FPS animation, use `1/60`.

This is the recommended way to create animations, as shown in the updated Canvas double buffering example.

```python
import sidekick
import datetime

clock_label = sidekick.Label("Waiting for time...")

def update_time():
    # This is a regular (synchronous) function
    now = datetime.datetime.now()
    clock_label.text = now.strftime("%H:%M:%S")

# Schedule update_time to be called every 1 second.
sidekick.submit_interval(update_time, 1.0)

sidekick.run_forever()
```

### 5.5 `await sidekick.run_forever_async()` for Pyodide

If you are running your code in Pyodide (which operates on a browser's event loop), you must use the asynchronous version of `run_forever`.

Instead of `sidekick.run_forever()`, you `await sidekick.run_forever_async()`. This correctly integrates with the existing event loop, ensuring the connection is active and then waiting for a shutdown signal without blocking.

```python
import sidekick
import asyncio

async def main():
    # This is an async main function
    console = sidekick.Console()
    console.print("Async script started.")

    # You can use async features like asyncio.sleep
    await asyncio.sleep(1)
    console.print("Async script continues after sleep.")

sidekick.submit_task(main())
await sidekick.run_forever_async()
```

### 5.6 Custom Connection (`sidekick.set_url`)

By default, `sidekick-py` tries to connect to a local Sidekick server (usually the VS Code extension on `ws://localhost:5163`) and then falls back to a cloud relay if configured.
If you need to connect to a specific Sidekick server (e.g., a custom deployment or a different cloud instance), you can use `sidekick.set_url("your_websocket_url")`.

**Important:** This must be called *before* any Sidekick component is created, as component creation implicitly triggers the connection activation.

```python
import sidekick

# Set this BEFORE creating any components
sidekick.set_url("ws://my-custom-sidekick-server.example.com:1234")

# Now create your components
my_label = sidekick.Label("Connecting to custom server...")
# ... rest of your script ...
sidekick.run_forever()
```

### 5.7 Clearing the UI

*   **`component.remove()`:** Removes a specific component instance from the Sidekick UI and cleans up its resources on the Python side.
    ```python
    import sidekick
    my_button = sidekick.Button("Temporary Button")
    # ... use the button ...
    sidekick.run_forever() # Assume it's interactive
    # Sometime later, perhaps in a callback:
    # my_button.remove() # Button disappears from the UI
    ```

*   **`sidekick.clear_all()`:** Sends a command to remove *all* currently displayed component instances from the Sidekick UI, effectively resetting the panel to an empty state (except for the root container).
    ```python
    import sidekick
    import time

    sidekick.Label("This will disappear.")
    sidekick.Button("So will this.")
    time.sleep(2) # Show them for a moment
    sidekick.clear_all() # Clears everything shown so far
    sidekick.Label("Panel is now clear, new content starts here.")
    sidekick.run_forever()
    ```

---

## Chapter 6: Sidekick Python API Reference

This chapter provides a more detailed (but not exhaustive) reference for the public API of the Sidekick Python library.

### 6.1 Global Functions

These functions are available directly under the `sidekick` module (e.g., `sidekick.run_forever()`).

*   `set_url(url: Optional[str])`: Sets a custom WebSocket URL for the Sidekick server, overriding defaults. Call before any component creation. Pass `None` to revert to default server list.
*   `activate_connection()`: **Non-blocking.** Ensures the Sidekick connection activation process is initiated if not already started or active. Usually called implicitly on first component creation.
*   `wait_for_connection(timeout: Optional[float] = None)`: **(CPython specific)** Blocks the calling thread until the Sidekick connection is fully active and ready, or until timeout/failure. Call this if you need to ensure connection before proceeding with UI interactions, and are not immediately calling `run_forever()`.
*   `clear_all()`: Removes all components from the Sidekick UI.
*   `register_global_message_handler(handler: Optional[Callable[[Dict], None]])`: Advanced. Registers a handler to receive *all* raw JSON messages coming from the Sidekick UI. Useful for debugging or custom protocol extensions.
*   `run_forever()`: (CPython) Internally ensures connection is active, then blocks the main script thread, keeping the Sidekick connection alive to process UI events. Exits on `Ctrl+C` or `sidekick.shutdown()`.
*   `run_forever_async()`: (Pyodide/async) Asynchronously ensures connection is active, then keeps the Sidekick connection alive. `await` this function.
*   `shutdown()`: Gracefully closes the connection to Sidekick and signals `run_forever` or `run_forever_async` to terminate.
*   `submit_task(coro: Coroutine)`: Submits a user-defined coroutine to Sidekick's managed asyncio event loop. Returns an `asyncio.Task`.
*   `submit_interval(callback: Callable, interval: float)`: Submits a function or coroutine to be called repeatedly at a specified interval. Returns an `asyncio.Task` representing the interval runner.

### 6.2 Component Base Class (`sidekick.Component`)

All visual components inherit from `Component`.

*   **Constructor `Component(component_type, payload, instance_id, parent, on_error)`:**
    *   `instance_id: Optional[str]`: User-defined unique ID. Auto-generated if `None`.
    *   `parent: Optional[Union[Component, str]]`: Parent container component or its `instance_id`.
    *   `on_error: Optional[Callable[[ErrorEvent], None]]`: Callback for UI-reported errors related to this component.
*   **Methods:**
    *   `remove()`: Removes the component from the UI and cleans up local resources.
    *   `on_error(callback: Optional[Callable[[ErrorEvent], None]])`: Sets or clears the error handler for this component.
*   **Properties (common to all components):**
    *   `.instance_id: str` (read-only after creation): The unique ID.
    *   `.component_type: str` (read-only): The type string (e.g., "grid", "button").

### 6.3 Core Visualization Components API

*   **`sidekick.Canvas(width, height, **kwargs)`**
    *   Properties: `.width`, `.height` (read-only).
    *   Methods: `clear(buffer_id=None)`, `draw_line(...)`, `draw_rect(...)`, `draw_circle(...)`, `draw_polyline(...)`, `draw_polygon(...)`, `draw_ellipse(...)`, `draw_text(...)`, `buffer()`, `on_click(callback)`, `@click` decorator.
    *   `buffer_id` in drawing methods defaults to `Canvas.ONSCREEN_BUFFER_ID` (0). Inside `with canvas.buffer() as buf:`, `buf.draw_line(...)` automatically targets an offscreen buffer.

*   **`sidekick.Console(text="", show_input=False, **kwargs)`**
    *   Methods: `print(*args, sep=' ', end='\n')`, `clear()`, `on_submit(callback)`, `@submit` decorator.

*   **`sidekick.Grid(num_columns, num_rows, **kwargs)`**
    *   Properties: `.num_columns`, `.num_rows` (read-only).
    *   Methods: `set_color(x, y, color)`, `set_text(x, y, text)`, `clear_cell(x, y)`, `clear()`, `on_click(callback)`, `@click` decorator.

*   **`sidekick.Viz(**kwargs)`**
    *   Methods: `show(name, value)`, `remove_variable(name)`.

### 6.4 UI Input/Display Components API

*   **`sidekick.Label(text="", **kwargs)`**
    *   Property: `.text: str` (get/set).

*   **`sidekick.Button(text="", **kwargs)`**
    *   Property: `.text: str` (get/set).
    *   Methods: `on_click(callback)`, `@click` decorator.

*   **`sidekick.Textbox(value="", placeholder="", **kwargs)`**
    *   Properties: `.value: str` (get/set), `.placeholder: str` (get/set).
    *   Methods: `on_submit(callback)`, `@submit` decorator.

*   **`sidekick.Markdown(text="", **kwargs)`**
    *   Property: `.text: str` (get/set).

### 6.5 Layout Components API

*   **`sidekick.Row(*children, **kwargs)`**
    *   Can accept child `Component` instances directly in the constructor.
    *   Method: `add_child(child_component: Component)`.

*   **`sidekick.Column(*children, **kwargs)`**
    *   Can accept child `Component` instances directly in the constructor.
    *   Method: `add_child(child_component: Component)`.

### 6.6 Event Objects

Located in `sidekick.events`. All inherit from `BaseSidekickEvent`.

*   `BaseSidekickEvent(instance_id: str, type: str)`
*   `ButtonClickEvent(instance_id: str, type: str)`
*   `GridClickEvent(instance_id: str, type: str, x: int, y: int)`
*   `CanvasClickEvent(instance_id: str, type: str, x: int, y: int)`
*   `TextboxSubmitEvent(instance_id: str, type: str, value: str)`
*   `ConsoleSubmitEvent(instance_id: str, type: str, value: str)`
*   `ErrorEvent(instance_id: str, type: str, message: str)`

### 6.7 `sidekick.ObservableValue` API

*   **Constructor:** `ObservableValue(value: Any)`
*   **Methods:**
    *   `get() -> Any`: Returns the wrapped Python value.
    *   `set(new_value: Any)`: Replaces the wrapped value entirely.
    *   Intercepted list methods: `append(item)`, `insert(index, item)`, `pop(index=-1)`, `remove(value)`, `clear()`.
    *   Intercepted dict methods: `__setitem__(key, value)` (for `obs[key]=val`), `__delitem__(key)` (for `del obs[key]`), `update(other, **kwargs)`, `clear()`.
    *   Intercepted set methods: `add(element)`, `discard(element)`, `clear()`.
    *   Standard dunder methods for iteration, length, containment, etc., are delegated to the wrapped value (`__iter__`, `__len__`, `__getitem__`, `__contains__`, etc.).

### 6.8 Exception Classes

Located in `sidekick.exceptions`.

*   `SidekickError(Exception)`: Base for all Sidekick library errors.
*   `SidekickConnectionError(SidekickError)`: Base for connection issues.
    *   `SidekickConnectionRefusedError(SidekickConnectionError)`: Connection refused by server.
    *   `SidekickTimeoutError(SidekickConnectionError)`: Operation timed out (e.g., waiting for UI).
    *   `SidekickDisconnectedError(SidekickConnectionError)`: Connection lost after being established.

---

## Chapter 7: Troubleshooting and Help

### 7.1 Frequently Asked Questions (FAQ) & Troubleshooting

*   **Q: My Sidekick panel is blank / nothing is showing up.**
    *   **A1:** Ensure you have installed both `sidekick-py` and the "Sidekick - Your Visual Coding Buddy" VS Code extension.
    *   **A2:** Make sure the Sidekick panel is open in VS Code (`Ctrl+Shift+P` > `Sidekick: Show Panel`).
    *   **A3:** Check your Python script for errors. Any error before Sidekick components are created or connection is established might prevent UI from appearing.
    *   **A4:** Look at the VS Code "Output" panel, and select "Sidekick Server" from the dropdown. This channel logs messages from the WebSocket server within the extension and can indicate connection problems (e.g., port already in use for `ws://localhost:5163`).
    *   **A5:** Open VS Code Developer Tools (Help > Toggle Developer Tools) and check the Console tab for errors related to the extension or the Webview.
    *   **A6:** If you're using `sidekick.set_url()`, ensure the URL is correct and the server is reachable.

*   **Q: I clicked a button, but my Python callback function didn't run.**
    *   **A:** Did you include `sidekick.run_forever()` (or `await sidekick.run_forever_async()`) at the end of your script? This is necessary to keep the script alive and listening for UI events.
    *   **A:** Double-check that you correctly registered the event handler using `on_click=...`, `button.on_click(...)`, or the `@button.click` decorator.

*   **Q: My `ObservableValue` isn't updating the `Viz` panel.**
    *   **A:** Ensure you are modifying the data *through the `ObservableValue` wrapper's methods* (e.g., `my_observable_list.append(item)`), not by modifying the original unwrapped data directly.
    *   **A:** For nested structures, the inner mutable parts also need to be `ObservableValue` instances if you want their internal changes to be reactive.

*   **Q: I see "Connection refused" or "Timeout" errors in my Python console.**
    *   **A:** This usually means `sidekick-py` couldn't connect to the Sidekick WebSocket server.
        *   If using VS Code, ensure the extension is enabled and the "Sidekick: Show Panel" command has successfully opened the panel. Check the "Sidekick Server" output channel in VS Code for server startup errors.
        *   If trying to connect to a remote/cloud server, check the URL and network connectivity.

*   **Q: My animation on the `Canvas` is flickering.**
    *   **A:** Use the `canvas.buffer()` context manager for double buffering. Draw all elements of a single animation frame within the `with canvas.buffer() as frame_buffer:` block. Also, prefer using `sidekick.submit_interval()` to drive your animation loop instead of a manual `while/sleep` loop.

### 7.2 Getting More Help

*   **GitHub Repository:** [https://github.com/zhouer/Sidekick](https://github.com/zhouer/Sidekick)
    *   Check the **Issues** tab for existing bug reports or feature requests.
    *   Feel free to open a new issue if you encounter a bug or have a question.
*   **Documentation:** Refer to the `docs/` directory in the repository for more detailed architectural and protocol information.

Happy visual coding with Sidekick!