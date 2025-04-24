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

    Use the command palette (`Ctrl+Shift+P`) and run `Sidekick: Show Panel`.

4.  **Run the sample code**:

    ```python
    import sidekick
    import random

    # Create a 5x5 Grid
    grid = sidekick.Grid(5, 5)

    # Define what happens on click
    def handle_click(x, y):
        colors = ["khaki", "lavender", "peachpuff", "pink", "plum", "powderblue"]
        random_color = random.choice(colors)
        grid.set_color(x, y, random_color)

    # Register the click handler
    grid.on_click(handle_click)

    # Keep your script running to listen for clicks!
    sidekick.run_forever()
    ```

    Run your script using `python your_file.py` in the terminal, or click the `Run` button in VS Code.

5.  **Interact:** 

    Click cells in the Sidekick panel to see colors change (press `Ctrl+C` to stop)

## Why Choose Sidekick?

*   **Real-time Visual Feedback:** See your code in action instantly with interactive visualizations. Watch data structures change, algorithms execute, and user interactions trigger responses in real-time.
*   **Intuitive, Pythonic Syntax:** Focus on learning concepts rather than UI programming. Sidekick's intuitive, beginner-friendly API keeps your code clean and readable with minimal boilerplate.
*   **Integrated Development Experience:** Seamlessly embedded in VS Code, Sidekick lets you see results immediately without switching applications, all within your complete development environment.
*   **Building Blocks, Not Frameworks:** Sidekick doesn't aim to be a complete UI framework like Qt or Tkinter. Instead, it provides essential building blocks that let you create unlimited possibilities with your imagination.

## Features

### 1. [`Grid`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.grid) - Interactive Cell-Based Visualizations

*   `Grid(num_columns, num_rows)`: Create a grid with specified dimensions
*   `set_color()`, `set_text()`: Set colors and text
*   `on_click()`: Handle user interaction

### 2. [`Console`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.console) - Text-Based Input and Output

*   `Console(show_input=False)`: Create a console that optionally includes input field
*   `print()`: Display output
*   `on_input_text()`: Collect user input

### 3. [`Control`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.control) - Interactive UI Components

*   `Control()`: Create a control panel for UI components
*   `add_button()`: Create buttons
*   `add_text_input()`: Add text inputs
*   `on_click()`: Handle button clicks
*   `on_input_text()`: Process text input

### 4. [`Canvas`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.canvas) - 2D Graphics and Animation

*   `Canvas(width, height)`: Create a drawing canvas with specified dimensions
*   `draw_line()`, `draw_polyline()`: Draw lines
*   `draw_rect()`, `draw_circle()`, `draw_polygon()`, `draw_ellipse()`: Draw shapes
*   `draw_text()`: Add text
*   `buffer()`: Create smooth animations with this context manager
*   `on_click()`: Respond to clicks

### 5. [`Viz`](https://zhouer.github.io/sidekick-py-docs/sidekick.html#module-sidekick.viz) - Data Structure Visualization

*   `Viz()`: Create a visualization panel for data structures
*   `show()`: Display complex data
*   `ObservableValue`: Wrap data structures to update visualizations automatically

### 6. Managing Script Lifecycle

*   `sidekick.run_forever()`: Keep your script running to handle interactions
*   `sidekick.shutdown()`: Gracefully stop the script when needed

## Learn More

*   **[Sidekick GitHub Repository](https://github.com/zhouer/Sidekick)**
*   Explore the [Examples Directory](https://github.com/zhouer/Sidekick/tree/main/examples).
*   Read the [Python API Reference](https://zhouer.github.io/sidekick-py-docs/).
