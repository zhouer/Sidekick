# Sidekick – Your Visual Coding Buddy

**Turn your code's logic into interactive visualizations directly within VS Code!**

Sidekick is a modular visual programming assistant designed to bridge the gap between abstract code and tangible output. It provides an interactive panel right next to your code where your Python scripts can draw grids, display text, visualize data structures, create simple drawings, and even add UI controls like buttons.

Perfect for:

*   **Beginners:** See your code's effects instantly, making learning Python more engaging and intuitive.
*   **Educators & Students:** Create interactive examples and visually explain algorithms or programming concepts.
*   **Algorithm Visualization:** Watch data structures change or simulations unfold in real-time.
*   **Debugging:** Get a clearer picture of your program's state beyond simple print statements.

Sidekick uses a simple Python library (`sidekick-py`) to control the visual elements, communicating seamlessly with the VS Code panel via WebSockets.

---

## Features

*   **Real-time Visualization:** See updates in the Sidekick panel as your Python code runs.
*   **Interactive Elements:** Respond to clicks on grids, button presses, or text input from the panel within your Python script.
*   **Multiple Modules:** Includes built-in modules for different visualization needs:
    *   **Grid:** An interactive grid of cells.
    *   **Console:** A text output area, optionally with user input.
    *   **Viz:** An inspector for Python variables and data structures (lists, dicts, sets, objects) with reactive updates.
    *   **Canvas:** A basic 2D drawing surface for lines, rectangles, and circles.
    *   **Control:** Dynamically add buttons and text input fields.
*   **Simple Python API:** Easy-to-use object-oriented library (`sidekick-py`) hides communication complexities.
*   **VS Code Integration:** Runs smoothly within a dedicated panel in your familiar IDE environment.

---

## Quick Start

1.  **Prerequisites:** Make sure you have Python 3 installed.
2.  **Install Python Library:** Open your terminal or command prompt and install the `sidekick-py` library:
    ```bash
    pip install sidekick-py
    ```
3.  **Install Extension:** Install this "Sidekick - Your Visual Coding Buddy" extension from the VS Code Marketplace.
4.  **Show Sidekick Panel:** Open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`) and type/select **"Show Sidekick Panel"**. This will open the Sidekick panel in a separate view column.
5.  **Create & Run Python Script:** Create a new Python file (e.g., `hello_sidekick.py`) with the following code:

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

6.  **Run the Script:** Open a terminal within VS Code (or use your system terminal) and run the script:
    ```bash
    python hello_sidekick.py
    ```

7.  **Interact:** You should see "Sidekick Grid initialized..." printed in your terminal. Look at the Sidekick panel in VS Code. Click on any cell in the 5x5 grid. You'll see the cell update in the panel and a message printed in your terminal! Press `Ctrl+C` in the terminal to stop the script.

---

## Modules Overview

Sidekick comes with several built-in visual modules you can control from Python:

*   **`sidekick.Grid`**: Creates an M x N grid of cells. You can set the `color` and `text` of each cell individually. Supports `on_click` event handling to react when a user clicks a cell.
*   **`sidekick.Console`**: Provides a scrolling text output area, similar to a standard console. Use `.print()` or `.log()` to append messages. Can optionally include a text input field and supports `on_input_text` for handling user submissions.
*   **`sidekick.Viz`**: Visualizes Python variables and data structures (like lists, dictionaries, sets, and basic objects) in an expandable tree view. When used with `sidekick.ObservableValue`, it automatically updates the UI to reflect changes in your data with minimal code.
*   **`sidekick.Canvas`**: A simple 2D drawing surface. Provides methods like `.draw_line()`, `.draw_rect()`, `.draw_circle()`, `.clear()`, and `.config()` to control drawing styles.
*   **`sidekick.Control`**: Allows you to dynamically add UI controls like buttons (`.add_button()`) and text input fields with submit buttons (`.add_text_input()`) to the Sidekick panel. Supports `on_click` (for buttons) and `on_input_text` (for text submissions) events.
