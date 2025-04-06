# hero.py
import sidekick
import time
import random
import math
import threading # For delayed actions demonstration

# --- Configuration (Optional, but good for testing) ---
# Ensure a clean slate in Sidekick UI when the script connects
# Set connection URL if not using the default localhost:5163
# sidekick.set_url("ws://...")
sidekick.set_config(clear_on_connect=True, clear_on_disconnect=False)

# --- Global Flags/Data (Optional) ---
script_running = True

# --- Callback Handlers ---
# Define handlers *before* creating modules that use them

def handle_grid_click(message):
    """Callback for Grid module events."""
    payload = message.get('payload', {})
    event_type = payload.get('event')
    if event_type == 'click':
        x, y = payload.get('x'), payload.get('y')
        # Provide feedback using the main console
        if main_console:
            main_console.print(f"Grid Clicked: ({x}, {y})")
        # Optionally, change the clicked cell
        if test_grid and 0 <= x < test_grid.num_columns and 0 <= y < test_grid.num_rows:
             test_grid.set_cell(x, y, color="#FFA500", text="Clicked") # Orange

def handle_console_input(message):
    """Callback for the interactive Console module events."""
    global script_running
    payload = message.get('payload', {})
    event_type = payload.get('event')
    if event_type == 'inputText':
        value = payload.get('value', '')
        main_console.print(f"Hero Received Input: '{value}'")
        if value.lower() == 'quit':
            main_console.print("Quit signal received. Shutting down.")
            script_running = False
        elif value.lower() == 'clear grid':
             if test_grid: test_grid.clear()
        elif value.lower() == 'clear canvas':
             if test_canvas: test_canvas.clear()
        elif value.lower().startswith('viz remove '):
            var_name = value.split(' ', 2)[-1]
            if test_viz and var_name:
                 test_viz.remove_variable(var_name)


def handle_control_interaction(message):
    """Callback for Control module events."""
    payload = message.get('payload', {})
    event_type = payload.get('event')
    control_id = payload.get('controlId')

    if event_type == 'click':
        main_console.print(f"Control Click: Button '{control_id}'")
        if control_id == 'remove_me_button':
             main_console.print(f"Removing button '{control_id}'...")
             if test_controls:
                 test_controls.remove_control(control_id)

    elif event_type == 'inputText':
        value = payload.get('value', '')
        main_console.print(f"Control Input: Text field '{control_id}' submitted value: '{value}'")

# --- Module Instances (Initialize to None) ---
main_console: sidekick.Console | None = None
test_grid: sidekick.Grid | None = None
test_canvas: sidekick.Canvas | None = None
test_viz: sidekick.Viz | None = None
test_controls: sidekick.Control | None = None

# --- Main Application Logic ---
try:
    # 1. --- Console ---
    # Create the main console first for logging script progress
    # Keep the instance_id predictable for potential re-attachment
    console_id = "main-test-console"
    main_console = sidekick.Console(
        instance_id=console_id,
        spawn=True, # Create it initially
        show_input=True, # Enable the input field
        initial_text="--- Sidekick Test App Initialized ---"
    )
    # Re-attach to register the handler (demonstrates spawn=False)
    # Note: This only works reliably if Sidekick preserves state across Hero restarts
    # For this script, it mainly tests the mechanism.
    console_handler_attacher = sidekick.Console(
        instance_id=console_id,
        spawn=False, # Don't re-create, just attach
        on_message=handle_console_input # Register handler
    )
    main_console.print("Console Ready. Type 'quit' to exit.")
    time.sleep(0.5)

    # 2. --- Grid ---
    main_console.print("Creating Grid (10x8)...")
    test_grid = sidekick.Grid(
        num_columns=10,
        num_rows=8,
        instance_id="test-grid-1",
        on_message=handle_grid_click # Register click handler
    )
    time.sleep(0.5)

    main_console.print("Populating Grid...")
    for y in range(test_grid.num_rows):
        for x in range(test_grid.num_columns):
            color = f"hsl({(x + y * 2) * 20 % 360}, 70%, 50%)"
            text = f"{x},{y}"
            test_grid.set_cell(x, y, color=color, text=text)
            # time.sleep(0.01) # Very fast, maybe too fast
    time.sleep(1)
    main_console.print("Grid populated. Click on cells!")
    main_console.print("Type 'clear grid' in console input to clear.")
    time.sleep(1)

    # 3. --- Canvas ---
    main_console.print("Creating Canvas (400x300)...")
    test_canvas = sidekick.Canvas(width=400, height=300, instance_id="test-canvas-1", bg_color="#f0f0f0")
    time.sleep(0.5)

    main_console.print("Drawing on Canvas...")
    # Configure styles
    test_canvas.config(stroke_style="blue", line_width=2)
    # Draw lines
    test_canvas.draw_line(10, 10, 390, 290)
    test_canvas.config(stroke_style="red", line_width=1)
    test_canvas.draw_line(10, 290, 390, 10)
    time.sleep(0.5)
    # Draw rectangles
    test_canvas.config(stroke_style="green", fill_style="rgba(0, 255, 0, 0.3)", line_width=3)
    test_canvas.draw_rect(50, 50, 100, 80, filled=False) # Outline
    test_canvas.draw_rect(200, 150, 120, 100, filled=True) # Filled
    time.sleep(0.5)
    # Draw circles
    test_canvas.config(stroke_style="#8A2BE2", fill_style="yellow", line_width=4) # BlueViolet outline
    test_canvas.draw_circle(100, 200, 40, filled=False) # Outline
    test_canvas.draw_circle(300, 80, 50, filled=True)   # Filled
    time.sleep(1)
    main_console.print("Canvas drawing complete.")
    main_console.print("Type 'clear canvas' in console input to clear.")
    time.sleep(1)

    # 4. --- Control ---
    main_console.print("Creating Control Panel...")
    test_controls = sidekick.Control(instance_id="test-controls-1", on_message=handle_control_interaction)
    time.sleep(0.5)

    main_console.print("Adding controls...")
    test_controls.add_button(control_id="hello_button", text="Say Hello")
    time.sleep(0.2)
    test_controls.add_text_input(
        control_id="name_input",
        placeholder="Enter your name",
        initial_value="Sidekick User",
        button_text="Submit Name"
    )
    time.sleep(0.2)
    test_controls.add_button(control_id="remove_me_button", text="Remove Me")
    time.sleep(1)
    main_console.print("Controls added. Interact with them!")
    time.sleep(1)

    # 5. --- Viz ---
    main_console.print("Creating Variable Visualizer (Viz)...")
    test_viz = sidekick.Viz(instance_id="test-viz-1")
    time.sleep(0.5)

    main_console.print("Showing variables in Viz...")
    # Basic types
    test_viz.show("my_string", "Hello Viz!")
    test_viz.show("my_integer", 12345)
    test_viz.show("my_float", 3.14159)
    test_viz.show("my_boolean", True)
    test_viz.show("my_none", None)
    time.sleep(0.5)

    # Containers (non-observable first)
    simple_list = [1, "two", False, None, 3.0]
    simple_dict = {"a": 10, "b": "bee", "c": [1,2], True: "Yes"}
    simple_set = {1, 1, 2, 3, "apple", "banana"}
    test_viz.show("simple_list", simple_list)
    test_viz.show("simple_dict", simple_dict)
    test_viz.show("simple_set", simple_set)
    time.sleep(0.5)

    # Observable Containers
    obs_list = sidekick.ObservableValue([10, 20, 30])
    obs_dict = sidekick.ObservableValue({"x": 100, "y": 200})
    obs_nested = sidekick.ObservableValue({
        "name": "Nested Observable",
        "data": sidekick.ObservableValue([
            {"id": 1, "value": sidekick.ObservableValue("A")},
            {"id": 2, "value": sidekick.ObservableValue("B")}
        ]),
        "settings": {"enabled": True}
    })
    test_viz.show("observable_list", obs_list)
    test_viz.show("observable_dict", obs_dict)
    test_viz.show("observable_nested", obs_nested)
    time.sleep(1)

    # --- Demonstrate Reactivity ---
    main_console.print("Modifying observable variables...")
    time.sleep(1)

    main_console.print(" -> Appending to observable_list")
    obs_list.append(40)
    time.sleep(1)

    main_console.print(" -> Changing item in observable_list")
    obs_list[1] = 25 # Update value at index 1
    time.sleep(1)

    main_console.print(" -> Adding item to observable_dict")
    obs_dict["z"] = 300 # Add new key
    time.sleep(1)

    main_console.print(" -> Updating item in observable_dict")
    obs_dict["x"] = 150 # Update existing key
    time.sleep(1)

    main_console.print(" -> Modifying nested observable value")
    # Access nested observable value and set it
    obs_nested.get()["data"].get()[0]["value"].set("Alpha")
    time.sleep(1)

    main_console.print(" -> Appending to nested observable list")
    # Access nested observable list and append
    obs_nested.get()["data"].append({"id": 3, "value": sidekick.ObservableValue("C")})
    time.sleep(1)

    main_console.print(" -> Removing variable 'simple_set'")
    test_viz.remove_variable("simple_set")
    time.sleep(0.5)
    main_console.print("Type 'viz remove <var_name>' to remove others.")

    # --- Keep Script Running ---
    main_console.print("--- Test Setup Complete ---")
    main_console.print("Interact with UI elements. Type 'quit' in Console input to exit.")
    while script_running:
        # Keep alive, maybe add periodic actions if needed
        time.sleep(0.5)

except ConnectionRefusedError:
    print("[ERROR] Connection refused. Is the Sidekick server (e.g., Vite dev server or VS Code extension) running?")
except Exception as e:
    print(f"[ERROR] An unexpected error occurred: {e}")
    import traceback
    traceback.print_exc()
finally:
    print("Hero script finishing. Closing connection...")
    # --- Cleanup ---
    # remove() sends the remove command and unregisters handlers
    if test_grid: test_grid.remove()
    if test_canvas: test_canvas.remove()
    if test_viz: test_viz.remove()
    if test_controls: test_controls.remove()
    # Removing the console last might prevent seeing final messages if it closes too quickly
    if main_console: main_console.remove()
    # Explicitly close the WebSocket connection
    sidekick.close_connection()
    print("Connection closed.")