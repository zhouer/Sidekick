# Sidekick – Your Visual Coding Buddy

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue.svg)](https://github.com/zhouer/Sidekick)
[![PyPI version](https://badge.fury.io/py/sidekick-py.svg)](https://badge.fury.io/py/sidekick-py)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sidekick-coding.sidekick-coding?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**See your code come to life, right inside VS Code!**

Sidekick is your friendly visual assistant for programming. It tackles the challenge of abstract code by providing an **interactive panel** directly within your VS Code editor. Watch loops draw patterns, data structures change in real-time, without leaving your development environment.

Perfect for **learners**, **educators**, **parents teaching coding**, and anyone who benefits from seeing code in action!

## Quick Start

1.  **Install the Python Library:**

    ```shell
    pip install sidekick-py
    ```

2.  **Install the VS Code Extension:**

    Get "Sidekick - Your Visual Coding Buddy" from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding)

3.  **Open Sidekick Panel:**

    Use the command palette (`Ctrl+Shift+P` or `Cmd+Shift+P`) and run `Sidekick: Show Panel`.

4.  **Run the sample code**:

    ```python
    import sidekick
    import random

    # Create a 5x5 Grid
    grid = sidekick.Grid(5, 5)

    # Define what happens on click
    def handle_click(event):
        colors = ["khaki", "lavender", "peachpuff", "pink", "plum", "powderblue"]
        random_color = random.choice(colors)
        grid.set_color(event.x, event.y, random_color)
        print(f"Grid '{event.instance_id}' cell ({event.x}, {event.y}) clicked, set to {random_color}")

    # Register the click handler
    grid.on_click(handle_click)

    # Keep your script running to listen for clicks!
    sidekick.run_forever()
    ```

    Run your script using `python your_file.py` in the terminal, or click the `Run` button in VS Code.

5.  **Interact:**

    Click cells in the Sidekick panel to see colors change.

## Why Choose Sidekick?

*   **Real-time Visual Feedback:** See your code in action instantly with interactive visualizations. Watch data structures change, algorithms execute, and user interactions trigger responses in real-time.
*   **Intuitive, Pythonic Syntax:** Focus on learning concepts rather than UI programming. Sidekick's intuitive, beginner-friendly API keeps your code clean and readable with minimal boilerplate.
*   **Integrated Development Experience:** Seamlessly embedded in VS Code, Sidekick lets you see results immediately without switching applications, all within your complete development environment.
*   **Building Blocks, Not Frameworks:** Sidekick doesn't aim to be a complete UI framework like Qt or Tkinter. Instead, it provides essential building blocks that let you create unlimited possibilities with your imagination.

## Features

### Core Visual Components

1.  **[`Grid`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.grid)** - Interactive Cell-Based Visualizations
    *   `Grid(num_columns, num_rows)`: Create a grid.
    *   `set_color()`, `set_text()`: Set cell colors and text.
    *   `on_click()`: Handle user clicks on cells.

2.  **[`Console`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.console)** - Text-Based Input and Output
    *   `Console(show_input=False)`: Create a console area.
    *   `print()`: Display output text.
    *   `on_submit()`: Handle user text submission (if `show_input=True`).

3.  **[`Canvas`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.canvas)** - 2D Graphics and Animation
    *   `Canvas(width, height)`: Create a drawing canvas.
    *   `draw_line()`, `draw_rect()`, `draw_circle()`, `draw_polygon()`, `draw_ellipse()`, `draw_text()`: Draw shapes and text.
    *   `buffer()`: Context manager for smooth, double-buffered animations.
    *   `on_click()`: Respond to clicks on the canvas.

4.  **[`Viz`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.viz)** - Data Structure Visualization
    *   `Viz()`: Create a panel for visualizing variables.
    *   `show()`: Display complex data (lists, dicts, sets, objects).
    *   `ObservableValue`: Wrap data for automatic visualization updates on change.

### UI & Layout Components

5.  **[`Label`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.label)** - Simple Text Display
    *   `Label(text)`: Display a line of text.
    *   `.text` property: Get or set the displayed text.

6.  **[`Button`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.button)** - Clickable Buttons
    *   `Button(text)`: Create a button.
    *   `.text` property: Get or set the button label.
    *   `on_click()`, `@button.click`: Handle button clicks.

7.  **[`Textbox`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.textbox)** - Single-Line Text Input
    *   `Textbox()`: Create a text input field.
    *   `.value` property: Get or set the text content.
    *   `on_submit()`, `@textbox.submit`: Handle text submission (on Enter/blur).

8.  **[`Markdown`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.markdown)** - Formatted Text Display
    *   `Markdown()`: Display text formatted with Markdown.
    *   `.source` property: Get or set the Markdown source string.

9.  **Layout Containers (`Row`, `Column`)**
    *   [`Row()`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.row): Arranges child components horizontally.
    *   [`Column()`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.column): Arranges child components vertically.
    *   Use `container.add_child(component)` or `Component(..., parent=container)` to structure layouts.

### Managing Script Lifecycle

*   `sidekick.run_forever()`: Keep your script running to handle interactions (clicks, input). Necessary for interactive components.
*   `sidekick.shutdown()`: Gracefully stop the script and disconnect (can be called from callbacks).

## Learn More

*   [Examples](https://github.com/zhouer/Sidekick/tree/main/examples/)
*   [API Reference](https://zhouer.github.io/sidekick-py-docs/)
*   **Developer Docs:** [Architecture](https://github.com/zhouer/Sidekick/blob/main/docs/architecture.md) | [Protocol](https://github.com/zhouer/Sidekick/blob/main/docs/protocol.md) | [Python](https://github.com/zhouer/Sidekick/blob/main/docs/python-development.md) | [WebApp](https://github.com/zhouer/Sidekick/blob/main/docs/webapp-development.md) | [Extension](https://github.com/zhouer/Sidekick/blob/main/docs/extension-development.md)

## Origins

This project started as a personal tool designed to help teach my own children the fundamentals of coding in a more visual and engaging way. I wanted to bridge the gap between abstract code and tangible results. The core ideas were inspired by the great work and philosophy behind [PyKidos](https://pykidos.github.io/).

## License

MIT License - see [LICENSE.md](https://github.com/zhouer/Sidekick/blob/main/LICENSE.md)