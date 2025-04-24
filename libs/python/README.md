# Sidekick Python Library (`sidekick-py`)

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue.svg)](https://github.com/zhouer/Sidekick)
[![PyPI version](https://badge.fury.io/py/sidekick-py.svg)](https://badge.fury.io/py/sidekick-py)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sidekick-coding.sidekick-coding?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This library provides the Python interface for interacting with the [Sidekick Visual Coding Buddy](https://github.com/zhouer/Sidekick) frontend UI, typically running within VS Code. It allows your Python scripts to easily create, update, and interact with visual modules like grids (`Grid`), consoles (`Console`), variable visualizers (`Viz`), drawing canvases (`Canvas`), and UI controls (`Control`).

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

## Learn More

*   **[Sidekick GitHub Repository](https://github.com/zhouer/Sidekick)**
*   Explore the [Examples Directory](https://github.com/zhouer/Sidekick/tree/main/examples).
*   Read the [Python API Reference](https://zhouer.github.io/sidekick-py-docs/).
