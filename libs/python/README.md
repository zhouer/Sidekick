# Sidekick Python Library (`sidekick-py`)

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue.svg)](https://github.com/zhouer/Sidekick)
[![PyPI version](https://badge.fury.io/py/sidekick-py.svg)](https://badge.fury.io/py/sidekick-py)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/sidekick-coding.sidekick-coding?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=sidekick-coding.sidekick-coding)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This library provides a Pythonic API to interact with the [Sidekick](https://github.com/zhouer/Sidekick) environment,
enabling you to bring your code to life through interactive visualizations and user interfaces directly from Python scripts.

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

## Learn More

*   [GitHub Repository](https://github.com/zhouer/Sidekick)
*   [Examples](https://github.com/zhouer/Sidekick/tree/main/examples).
*   [User Guide](https://github.com/zhouer/Sidekick/blob/main/docs/user-guide.md)
*   [API Reference](https://sidekick-py.readthedocs.io/).