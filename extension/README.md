# Sidekick – Your Visual Coding Buddy

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue.svg)](https://github.com/zhouer/Sidekick)
[![PyPI version](https://badge.fury.io/py/sidekick-py.svg)](https://badge.fury.io/py/sidekick-py)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sidekick-coding.sidekick-coding?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**See your Python code come alive, right inside VS Code!**

Sidekick is your friendly visual assistant for programming. It tackles the challenge of abstract code by providing an **interactive panel** directly within your VS Code editor. Watch loops draw patterns, data structures change in real-time, without leaving your development environment.

Perfect for **learners**, **educators**, **parents teaching coding**, and anyone who benefits from seeing code in action!

## Quick Start

Follow these steps to get Sidekick running:

1.  **Install Python Library:** Open your terminal and install the necessary `sidekick-py` library:
    ```bash
    pip install sidekick-py
    ```
    *(Requires Python 3)*

2.  **Install VS Code Extension:** Install this "Sidekick - Your Visual Coding Buddy" extension from the VS Code Marketplace.

3.  **Show Sidekick Panel:** In VS Code, open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`) and run the command: **`Sidekick: Show Panel`**. This will open the Sidekick panel, typically beside your editor.

4.  **Create a Python Script:** Save the following code as a Python file (e.g., `hello_sidekick.py`):

    ```python
    import sidekick
    import random

    # 1. Create a 5x5 Grid
    grid = sidekick.Grid(5, 5)
    grid.set_text(2, 2, "Click!")

    # 2. Define what happens on click
    def handle_click(x, y):
        colors = ["#FFADAD", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#9BF6FF", "#A0C4FF", "#BDB2FF", "#FFC6FF"]
        random_color = random.choice(colors)
        print(f"Cell ({x},{y}) clicked! Setting color to {random_color}")
        grid.set_color(x, y, random_color) # Update Sidekick UI
        grid.set_text(x, y, "") # Clear text on click

    # 3. Register the click handler
    grid.on_click(handle_click)

    # 4. Keep the script running to listen for clicks!
    #    Without this, the script would end, and clicks wouldn't be handled.
    sidekick.run_forever()
    ```

5.  **Run the Script:** Open a terminal within VS Code (`Ctrl+`\`), navigate to where you saved the file, and run:
    ```bash
    python hello_sidekick.py
    ```

6.  **Interact:** Click on the cells within the Sidekick panel in VS Code. Observe the terminal output and the visual changes in the grid! Press `Ctrl+C` in the terminal to stop the script.

## Why Sidekick?

*   **Instant Visualization:** Stop guessing, start seeing! Visualize algorithms on a `Grid`, track output in a `Console`, draw on a `Canvas`, or inspect data with `Viz`.
*   **Interactive Feedback:** Build programs that react! Create `Control` buttons that trigger Python functions, get user input from the `Console`, or respond to `Grid` clicks.
*   **Simple Python API:** Focus on your logic, not complex UI code. Sidekick provides an intuitive, beginner-friendly Python library (`sidekick-py`).
*   **Seamless VS Code Integration:** Works where you work. Sidekick lives in the VS Code side panel, keeping your code and its visual output together.
*   **Live Variable Explorer:** Use `Viz.show()` to inspect variables and data structures. Magically updates when you use `ObservableValue` – watch lists grow and dictionaries change automatically!
*   **Modular & Combinable:** Simple building blocks (`Grid`, `Console`, `Control`, `Canvas`, `Viz`) that you can combine creatively to suit your needs.

## Core Visualization Modules

Use these building blocks from the `sidekick-py` library to control the Sidekick panel:

*   **`sidekick.Grid(rows, cols)`**: Creates a grid. Use `.set_color(x, y, color)`, `.set_text(x, y, text)`, and `.on_click(callback)` to interact.
*   **`sidekick.Console(show_input=False)`**: A text output area. Use `.print(message)` or `.log(message)`. If `show_input=True`, use `.on_input_text(callback)` to get user input.
*   **`sidekick.Control()`**: Add UI controls. Use `.add_button(id, text)` or `.add_text_input(id, button_text, placeholder)`. Handle interactions with `.on_click(callback)` and `.on_input_text(callback)`.
*   **`sidekick.Canvas(width, height)`**: A drawing surface. Use methods like `.draw_line()`, `.draw_rect()`, `.draw_circle()`, `.clear()`, and `.config()`.
*   **`sidekick.Viz()`**: Visualize variables with `.show(name, value)`. Use `sidekick.ObservableValue(your_data)` for automatic UI updates when wrapped lists, dicts, or sets change.

## VS Code Integration Details

*   **Command:** Use `Sidekick: Show Panel` from the Command Palette (`Ctrl+Shift+P`) to open or focus the Sidekick view.
*   **Configuration:** You can adjust the WebSocket connection settings used internally if needed (e.g., if the default port `5163` conflicts):
    *   `sidekick.websocket.port` (default: `5163`)
    *   `sidekick.websocket.host` (default: `localhost`)
        These settings are accessible via VS Code's standard settings UI (File > Preferences > Settings, search for "Sidekick").

## Learn More

*   **[Sidekick GitHub Repository](https://github.com/zhouer/Sidekick)**
*   Explore the [Examples Directory](https://github.com/zhouer/Sidekick/tree/main/examples).
*   Read the [Python API Reference](https://zhouer.github.io/sidekick-py-docs/).