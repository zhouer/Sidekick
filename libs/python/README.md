# Sidekick Python Library (`sidekick-py`)

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue.svg)](https://github.com/zhouer/Sidekick)
[![PyPI version](https://badge.fury.io/py/sidekick-py.svg)](https://badge.fury.io/py/sidekick-py)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sidekick-coding.sidekick-coding?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This library provides the Python interface for interacting with the [Sidekick Visual Coding Buddy](https://github.com/zhouer/Sidekick) frontend UI, typically running within VS Code. It allows your Python scripts to easily create, update, and interact with visual modules like grids (`Grid`), consoles (`Console`), variable visualizers (`Viz`), drawing canvases (`Canvas`), and UI controls (`Control`).

## Installation

Install the library using pip:

```bash
pip install sidekick-py
```

You will also need the [Sidekick VS Code extension](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding) installed and running in VS Code.

## Minimal Usage Example

**First, open the Sidekick panel** in VS Code (Press `Ctrl+Shift+P`, search for and run `Sidekick: Show Panel`).

Then, save and run the following Python script:

```python
import sidekick

# 1. Create a 16x16 Grid
grid = sidekick.Grid(16, 16)

# 2. Define what happens when a cell is clicked
def handle_click(x, y):
    # Update the clicked cell in the Sidekick UI
    grid.set_color(x, y, 'red')
    print(f"Cell ({x}, {y}) clicked!") # Optional: Print to terminal

# 3. Register the click handler
grid.on_click(handle_click)

# 4. Keep the script running to listen for clicks!
#    Without this, the script would end, and clicks wouldn't be handled.
sidekick.run_forever()
```

After running the script, clicking the grid cells in the Sidekick panel will turn them red. Press `Ctrl+C` in the terminal to stop.

## Learn More

*   **[Sidekick GitHub Repository](https://github.com/zhouer/Sidekick)**
*   Explore the [Examples Directory](https://github.com/zhouer/Sidekick/tree/main/examples).
*   Read the [Python API Reference](https://zhouer.github.io/sidekick-py-docs/).