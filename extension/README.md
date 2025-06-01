# Sidekick – Your Visual Coding Buddy

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue.svg)](https://github.com/zhouer/Sidekick)
[![PyPI version](https://badge.fury.io/py/sidekick-py.svg)](https://badge.fury.io/py/sidekick-py)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sidekick-coding.sidekick-coding?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Sidekick is your visual coding buddy! An intuitive Python library that brings your code to life through an interactive panel in VS Code or your browser.
Quickly understand code execution, explore it visually, and make abstract programming concepts tangible.
Perfect for anyone learning or teaching Python, from young students to experienced developers.

## Quick Start

1.  **Install the Python Library:**

    ```shell
    pip install sidekick-py
    ```

2.  **Install and Open in VS Code (Recommended for the best experience):**

    *   Install "Sidekick - Your Visual Coding Buddy" from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding).
    *   Once installed, open the Sidekick Panel: Use the command palette (`Ctrl+Shift+P` or `Cmd+Shift+P`) and run `Sidekick: Show Panel`.

3. **Run the sample code**:

    ```python
    import sidekick
    import random

    # Create a 5x5 Grid
    grid = sidekick.Grid(5, 5)
    colors = ["khaki", "lavender", "peachpuff", "pink", "plum", "powderblue"]
    
    @grid.click # Use decorator for click handler
    def handle_cell_click(event):
        random_color = random.choice(colors)
        grid.set_color(event.x, event.y, random_color)
        print(f"Cell ({event.x}, {event.y}) set to {random_color}")

    # Keep your script running to listen for clicks!
    sidekick.run_forever()
    ```

    Run your Python script (e.g., `python your_file.py`) from your terminal, or use the "Run" button in VS Code.
  
    *   **If you have the VS Code extension installed and the Sidekick Panel open,** you will see the 5x5 Grid appear directly in the panel.
    *   **If the VS Code extension is not active or not installed,** the Python script will attempt to connect to a cloud relay server. In this case, a UI URL will be printed in your terminal; open this URL in your web browser to see and interact with the Grid.

## Why Choose Sidekick?

*   **Real-time Visual Feedback:** See your code in action instantly with interactive visualizations. Watch data structures change, algorithms execute, and user interactions trigger responses in real-time. This makes abstract programming concepts more tangible and easier to understand.
*   **Intuitive, Pythonic Syntax:** Focus on learning programming concepts rather than complex UI programming. Sidekick's beginner-friendly API keeps your code clean and readable with minimal boilerplate.
*   **Integrated Development Experience:** Seamlessly embedded in VS Code, Sidekick lets you see results immediately without switching applications. This tight feedback loop is invaluable for learning and debugging.
*   **Building Blocks, Not Frameworks:** Sidekick provides essential visual and UI building blocks. It doesn't aim to be a complete UI framework like Qt or Tkinter, but rather empowers you to create unlimited possibilities with your imagination by combining these fundamental components.

## Features

### Visual Components

1.  **[`Canvas`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.canvas)** - 2D Graphics and Animation
    *   `Canvas(width, height)`: Create a drawing canvas.
    *   `draw_line()`, `draw_rect()`, `draw_circle()`, `draw_polygon()`, `draw_ellipse()`, `draw_text()`: Draw shapes and text.
    *   `buffer()`: Context manager for smooth, double-buffered animations.
    *   `on_click()`: Respond to clicks on the canvas.

2.  **[`Console`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.console)** - Text-Based Input and Output
    *   `Console(show_input=False)`: Create a console area.
    *   `print()`: Display output text.
    *   `on_submit()`: Handle user text submission (if `show_input=True`).

3.  **[`Grid`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.grid)** - Interactive Cell-Based Visualizations
    *   `Grid(num_columns, num_rows)`: Create a grid.
    *   `set_color()`, `set_text()`: Set cell colors and text.
    *   `on_click()`: Handle user clicks on cells.

4.  **[`Viz`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.viz)** - Data Structure Visualization
    *   `Viz()`: Create a panel for visualizing variables.
    *   `show()`: Display complex data (lists, dicts, sets, objects).
    *   `ObservableValue`: Wrap data for automatic visualization updates on change.

### UI Components

1.  **[`Label`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.label)** - Simple Text Display
    *   `Label(text)`: Display a line of text.
    *   `.text` property: Get or set the displayed text.

2.  **[`Button`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.button)** - Clickable Buttons
    *   `Button(text)`: Create a button.
    *   `.text` property: Get or set the button label.
    *   `on_click()`, `@button.click`: Handle button clicks.

3.  **[`Textbox`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.textbox)** - Single-Line Text Input
    *   `Textbox()`: Create a text input field.
    *   `.value` property: Get or set the text content.
    *   `on_submit()`, `@textbox.submit`: Handle text submission (on Enter/blur).

4.  **[`Markdown`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.markdown)** - Formatted Text Display
    *   `Markdown()`: Display text formatted with Markdown.
    *   `.source` property: Get or set the Markdown source string.

### Layout Components

1.  **[`Row()`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.row)** - Arranges child components horizontally
    *   Use `container.add_child(component)` or `Component(..., parent=container)` to structure layouts. 

2.  **[`Column()`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#module-sidekick.column)** - Arranges child components vertically
    *   Use `container.add_child(component)` or `Component(..., parent=container)` to structure layouts.

### Managing Script Lifecycle

1.  **[`sidekick.run_forever()`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#sidekick.run_forever)** - Keep your script running to handle interactions (clicks, input). Necessary for interactive components.

2.  **[`sidekick.shutdown()`](https://sidekick-py.readthedocs.io/en/latest/sidekick.html#sidekick.shutdown)** - Gracefully stop the script and disconnect (can be called from callbacks).

## Learn More

*   [GitHub Repository](https://github.com/zhouer/Sidekick)
*   [Examples](https://github.com/zhouer/Sidekick/tree/main/examples).
*   [User Guide](https://github.com/zhouer/Sidekick/blob/main/docs/user-guide.md)
*   [API Reference](https://sidekick-py.readthedocs.io/).
