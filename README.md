# Sidekick – Your Visual Coding Buddy

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue.svg)](https://github.com/zhouer/Sidekick)
[![PyPI version](https://badge.fury.io/py/sidekick-py.svg)](https://badge.fury.io/py/sidekick-py)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sidekick-coding.sidekick-coding?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**See your Python code come alive, right inside VS Code!**

Sidekick is your friendly visual assistant for programming. It tackles the challenge of abstract code by providing an **interactive panel** directly within your VS Code editor. Watch loops draw patterns, data structures change in real-time, without leaving your development environment.

Perfect for **learners**, **educators**, **parents teaching coding**, and anyone who benefits from seeing code in action!

## Installation

Sidekick requires two components:

1.  **The Python Library [`sidekick-py`](https://pypi.org/project/sidekick-py/):**
    ```bash
    pip install sidekick-py
    ```
2.  **The VS Code Extension:**
    *   Open VS Code.
    *   Go to the Extensions view (`Ctrl+Shift+X`).
    *   Search for "**Sidekick - Your Visual Coding Buddy**" or use the [link](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding).
    *   Click **Install**.

## Quick Start

Let's make a simple interactive grid!

1.  **Open Sidekick:** In VS Code, press `Ctrl+Shift+P` and search for/run the command `Sidekick: Show Panel`.
2.  **Save the Code:** Save the following Python code as a file (e.g., `hello_sidekick.py`):

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

3.  **Run the Code:** Open a terminal in VS Code (`Ctrl+`\`) and run:
    ```bash
    python hello_sidekick.py
    ```
4.  **Interact:** Click on the cells in the Sidekick panel within VS Code. You should see the terminal print messages and the cell colors change! Press `Ctrl+C` in the terminal to stop.

## Why Sidekick?

*   **Instant Visualization:** Stop guessing, start seeing! Visualize algorithms on a `Grid`, track output in a `Console`, draw on a `Canvas`, or inspect data with `Viz`.
*   **Interactive Feedback:** Build programs that react! Create `Control` buttons that trigger Python functions, get user input from the `Console`, or respond to `Canvas` and `Grid` clicks.
*   **Simple Python API:** Focus on your logic, not complex UI code. Sidekick provides an intuitive, beginner-friendly Python library (`sidekick-py`).
*   **Seamless VS Code Integration:** Works where you work. Sidekick lives in the VS Code side panel, keeping your code and its visual output together.
*   **Live Variable Explorer:** Use `Viz.show()` to inspect variables and data structures. Magically updates when you use `ObservableValue` – watch lists grow and dictionaries change automatically!
*   **Modular & Combinable:** Simple building blocks (`Grid`, `Console`, `Control`, `Canvas`, `Viz`) that you can combine creatively to suit your needs.

## The Sidekick Philosophy: Focused & Fun

**Important Note:** Sidekick is **not** designed to be a full-featured UI framework like Qt or Tkinter.

Instead, Sidekick provides the **essential building blocks** for visual interaction, keeping the focus squarely on **understanding your code's logic and flow**. Its strength lies in its **simplicity** and **low learning curve**.

Think of Sidekick modules as powerful, easy-to-use visual tools. Combine them in imaginative ways: build a game board on the `Grid`, show game state in the `Console`, visualize complex data with `Viz`, draw graphics with `Canvas`, and add controls with `Control`. **The possibilities are vast, limited only by your creativity!**

## Core Concepts & Features

Sidekick helps bring your Python code to life visually. Here are the essential features:

### 1. Core Visualization Modules

These are the building blocks you create and control from Python:

*   **`sidekick.Grid`:** A 2D grid of cells. Perfect for maps, boards, or pixel art. Control cell color (`set_color`), text (`set_text`), and react to clicks (`on_click`).
*   **`sidekick.Console`:** A text output area, like Python's `print`, but inside Sidekick. Optionally includes a text input field. Use `print()`/`log()` for output and `on_input_text()` for user input.
*   **`sidekick.Control`:** Add UI controls like buttons (`add_button`) and text inputs (`add_text_input`). React to interactions using `on_click()` and `on_input_text()` callbacks.
*   **`sidekick.Canvas`:** A 2D drawing surface. Draw lines (`draw_line`), rectangles (`draw_rect`), circles (`draw_circle`), `draw_text()` etc., to create graphics programmatically. Includes a `buffer()` context manager for smooth, flicker-free animations (double buffering). React to clicks with `on_click()`.
*   **`sidekick.Viz`:** An interactive tree view for inspecting variables (lists, dicts, objects). Use `show()` to display. **Crucially, use `sidekick.ObservableValue` to make the display automatically update when your data changes!**

### 2. Interaction via Callbacks

Make your visualizations responsive! Sidekick lets your Python code react to UI events using callback functions:

*   `grid.on_click(callback)`: Run code when a grid cell is clicked.
*   `console.on_input_text(callback)`: Process text submitted from the console.
*   `control.on_click(callback)`: Trigger functions when buttons are pressed.
*   `control.on_input_text(callback)`: Handle text submitted from control inputs.
*   `canvas.on_click(callback)`: Run code when the canvas is clicked.
*   **Remember:** Your Python script must be running for callbacks to work (see Lifecycle Management).

### 3. Reactive Visualization with `ObservableValue`

Tired of manually updating variable displays? `Viz` works seamlessly with `ObservableValue`:

*   Wrap your lists, dicts, or sets: `obs_list = sidekick.ObservableValue([...])`
*   Show it: `viz.show("My List", obs_list)`
*   Modify it *through the wrapper* (`obs_list.append(item)`, `obs_list[0] = new_val`): The `Viz` panel updates automatically! No extra `viz.show()` needed.

### 4. Managing Script Lifecycle

Sidekick needs to talk to a *running* Python script. You need to manage how long your script runs:

*   **`sidekick.run_forever()`:** The most common method. **Keeps your script running indefinitely** to display visuals and handle interactions (callbacks). Place it at the end of your script. Stop with `Ctrl+C` or by calling `sidekick.shutdown()` from a callback.
*   **`sidekick.shutdown()`:** Call this (usually from a callback) to stop `run_forever()` gracefully and close the connection.

## Learn More

*   **See More Examples:** [**Examples Directory**](./examples/)
*   **Explore the API:** [**Full Python API Reference**](https://zhouer.github.io/sidekick-py-docs/)
*   **For Developers:**
    *   [System Architecture](./docs/architecture.md)
    *   [Communication Protocol](./docs/protocol.md)
    *   [Python Library Development Guide](./docs/python-development.md)
    *   [WebApp Development Guide](./docs/webapp-development.md)
    *   [Extension Development Guide](./docs/extension-development.md)

## Inspiration & Origins

This project started as a personal tool designed to help teach my own children the fundamentals of coding in a more visual and engaging way. I wanted to bridge the gap between abstract code and tangible results. The core ideas were inspired by the great work and philosophy behind [PyKidos](https://pykidos.github.io/).

## License

This project is licensed under the MIT License - see the [LICENSE.md](./LICENSE.md) file for details.
