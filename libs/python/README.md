# Sidekick Python Library (`sidekick-py`)

[![PyPI version](https://badge.fury.io/py/sidekick-py.svg)](https://badge.fury.io/py/sidekick-py)

This library provides the Python interface for interacting with the [Sidekick Visual Coding Buddy](https://github.com/zhouer/Sidekick) frontend UI, typically running within VS Code. It allows your Python scripts to easily create, update, and interact with visual modules like grids, consoles, variable visualizers, drawing canvases, and UI controls.

## Installation

Install the library using pip:

```bash
pip install sidekick-py
```

You will also need the [Sidekick VS Code extension](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding) installed and running in VS Code.

## Minimal Usage Example

```python
import sidekick

# 1. Create a Grid module instance
grid = sidekick.Grid()

# 2. Define what happens when a cell is clicked
def handle_click(x, y):
    # Update the clicked cell in the Sidekick UI
    grid.set_color(x, y, 'red')

# 3. Register the click handler
grid.on_click(handle_click)

# 4. Keep the script running to listen for clicks!
#    Without this, the script would end, and clicks wouldn't be handled.
sidekick.run_forever()
```

## Learn More

*   **Quick Start & Overview:** See the main [**Project README on GitHub**](https://github.com/zhouer/Sidekick) for a comprehensive quick start guide and project overview.
*   **Full API Reference:** Explore detailed documentation for all modules (`Grid`, `Console`, `Viz`, `Canvas`, `Control`), classes (`ObservableValue`), and functions in the [**Python API Documentation**](../../docs/api/python/index.html).
*   **Examples:** Check the `examples/` directory in the [GitHub repository](https://github.com/zhouer/Sidekick/tree/main/examples) for more usage scenarios.

This library simplifies the process by handling WebSocket communication and message formatting, allowing you to focus on controlling the visual elements from your Python code.
