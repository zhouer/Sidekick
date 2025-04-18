import time
import math
import logging
from typing import Optional, Dict, Any, List, Tuple

import sidekick
from sidekick import Console, Canvas

# Import asteval for safe expression evaluation
try:
    from asteval import Interpreter
except ImportError:
    print("ERROR: Please install the 'asteval' library: pip install asteval")
    exit(1)

# --- Configuration ---
CANVAS_WIDTH = 600
CANVAS_HEIGHT = 400
PLOT_POINTS = 400  # Number of points to calculate along the x-axis
DEFAULT_X_MIN = -10.0
DEFAULT_X_MAX = 10.0
DEFAULT_Y_MIN = -10.0
DEFAULT_Y_MAX = 10.0

# Colors
BG_COLOR = "#111827"      # Very Dark Blue/Gray background
AXIS_COLOR = "#9CA3AF"     # Gray axes
GRID_LINE_COLOR = "#374151" # Darker gray for grid lines
TEXT_COLOR = "#E5E7EB"     # Light gray for text
DEFAULT_PLOT_COLOR = "#34D399" # Teal function plot
PLOT_COLORS = [            # Colors for overlaid plots
    "#34D399", # Teal
    "#F87171", # Red
    "#60A5FA", # Blue
    "#FBBF24", # Amber
    "#A78BFA", # Violet
    "#EC4899", # Pink
    "#F1FAEE", # Off-white (for dark bg)
]

# --- Global State ---
console: Optional[Console] = None
canvas: Optional[Canvas] = None

# Plotting parameters - use globals for simplicity in this example
x_min, x_max = DEFAULT_X_MIN, DEFAULT_X_MAX
y_min, y_max = DEFAULT_Y_MIN, DEFAULT_Y_MAX

# Safe expression evaluator and symbol table
aeval = Interpreter()
# Add common math functions and constants
aeval.symtable['sin'] = math.sin
aeval.symtable['cos'] = math.cos
aeval.symtable['tan'] = math.tan
aeval.symtable['asin'] = math.asin
aeval.symtable['acos'] = math.acos
aeval.symtable['atan'] = math.atan
aeval.symtable['sqrt'] = math.sqrt
aeval.symtable['log'] = math.log # Natural log
aeval.symtable['log10'] = math.log10
aeval.symtable['exp'] = math.exp
aeval.symtable['pi'] = math.pi
aeval.symtable['e'] = math.e
aeval.symtable['abs'] = abs
# 'x' will be added temporarily during plotting

# Store plotted functions: List of (expression_string, color_string)
plotted_expressions: List[Tuple[str, str]] = []
plot_color_index = 0 # Index for cycling through PLOT_COLORS

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logging.getLogger("sidekick").setLevel(logging.DEBUG)

# --- Helper Functions ---

def map_coords(x: float, y: float) -> Optional[Tuple[int, int]]:
    """Maps mathematical coordinates to canvas pixel coordinates."""
    # Check for zero range *before* division
    if x_max == x_min or y_max == y_min:
        logging.warning(f"Plot range has zero width or height ({x_min=}, {x_max=}, {y_min=}, {y_max=}). Cannot map coords.")
        return None

    # Check if y is within plot range (with tolerance)
    y_epsilon = abs(y_max - y_min) * 0.001 if y_max != y_min else 0.01
    if y < y_min - y_epsilon or y > y_max + y_epsilon: return None

    px = int(((x - x_min) / (x_max - x_min)) * CANVAS_WIDTH)
    py = int(((y_max - y) / (y_max - y_min)) * CANVAS_HEIGHT) # Inverted y-axis

    # Clamp to canvas edges
    px = max(0, min(CANVAS_WIDTH - 1, px))
    py = max(0, min(CANVAS_HEIGHT - 1, py))

    return px, py

def draw_axes_and_grid():
    """Draws the X/Y axes and background grid lines."""
    if not canvas: return
    logging.debug("Drawing axes and grid...")
    canvas.clear(BG_COLOR) # Clear with background color

    # Prevent drawing if range is invalid
    if x_max <= x_min or y_max <= y_min:
        logging.warning("Cannot draw axes/grid due to invalid range.")
        # Optionally draw an error message on canvas if supported
        return

    # --- Draw Grid Lines ---
    canvas.config(stroke_style=GRID_LINE_COLOR, line_width=1)
    # Adjust grid density based on range, aiming for ~10 lines
    x_range = x_max - x_min
    y_range = y_max - y_min
    x_step = max(x_range / 10.0, 1e-6) # Avoid zero step
    y_step = max(y_range / 10.0, 1e-6)

    # Find a "nice" step value (e.g., 1, 2, 5, 10, etc.) - basic version
    x_magnitude = 10**math.floor(math.log10(x_step)) if x_step > 0 else 1
    y_magnitude = 10**math.floor(math.log10(y_step)) if y_step > 0 else 1
    x_nice_step = x_magnitude * (1 if x_step/x_magnitude < 1.5 else 2 if x_step/x_magnitude < 3.5 else 5 if x_step/x_magnitude < 7.5 else 10)
    y_nice_step = y_magnitude * (1 if y_step/y_magnitude < 1.5 else 2 if y_step/y_magnitude < 3.5 else 5 if y_step/y_magnitude < 7.5 else 10)

    # Vertical lines
    start_vx = math.ceil(x_min / x_nice_step) * x_nice_step
    vx = start_vx
    while vx <= x_max:
        if abs(vx) > 1e-9: # Avoid drawing over thicker Y axis
             coords = map_coords(vx, y_min)
             if coords: canvas.draw_line(coords[0], 0, coords[0], CANVAS_HEIGHT)
        vx += x_nice_step

    # Horizontal lines
    start_hy = math.ceil(y_min / y_nice_step) * y_nice_step
    hy = start_hy
    while hy <= y_max:
        if abs(hy) > 1e-9: # Avoid drawing over thicker X axis
             coords = map_coords(x_min, hy)
             if coords: canvas.draw_line(0, coords[1], CANVAS_WIDTH, coords[1])
        hy += y_nice_step

    # --- Draw Axes ---
    canvas.config(stroke_style=AXIS_COLOR, line_width=1)
    # X-Axis (line at y=0)
    x_axis_coords = map_coords(x_min, 0)
    if x_axis_coords and 0 <= x_axis_coords[1] < CANVAS_HEIGHT:
        canvas.draw_line(0, x_axis_coords[1], CANVAS_WIDTH, x_axis_coords[1])
    # Y-Axis (line at x=0)
    y_axis_coords = map_coords(0, y_min)
    if y_axis_coords and 0 <= y_axis_coords[0] < CANVAS_WIDTH:
        canvas.draw_line(y_axis_coords[0], 0, y_axis_coords[0], CANVAS_HEIGHT)

    # TODO: Add axis labels/ticks if Canvas supports text drawing later
    logging.debug("Axes and grid drawn.")

def plot_single_function(expression: str, color: str):
    """Evaluates and plots a single function expression with a specific color."""
    if not canvas or not console: return
    logging.info(f"Plotting expression '{expression}' with color {color}")

    # Check for invalid range before plotting
    if x_max <= x_min or y_max <= y_min:
        console.print(f"WARN: Invalid plot range. Cannot plot '{expression}'.")
        return

    canvas.config(stroke_style=color, line_width=2)
    points: List[Optional[Tuple[int, int]]] = []
    dx = (x_max - x_min) / PLOT_POINTS
    errors_encountered = 0
    last_valid_y = None

    for i in range(PLOT_POINTS + 1):
        x = x_min + i * dx
        aeval.symtable['x'] = x # Temporarily add x

        y = None
        try:
            y = aeval(expression)
            if not isinstance(y, (int, float)):
                raise TypeError(f"Result not a number ({type(y).__name__})")
            if not math.isfinite(y):
                 raise ValueError("Result is not finite (infinity or NaN)")
            last_valid_y = y

        except Exception as e:
            # Log only the first error after a valid point or the very first point's error
            if errors_encountered == 0:
                context = f"(last y={last_valid_y:.2f})" if last_valid_y is not None else ""
                msg = f"WARN: Eval Error for '{expression}' near x={x:.2f} {context}: {e}"
                console.print(msg)
                logging.warning(msg)
            errors_encountered += 1
            y = None # Mark as invalid
        finally:
             if 'x' in aeval.symtable: del aeval.symtable['x'] # Clean up x

        # Map coordinates and handle discontinuities
        if y is not None:
            coords = map_coords(x, y)
            points.append(coords) # Append coords or None if outside Y range
        else:
            points.append(None) # Error or outside Y range

    # Remove consecutive None values
    cleaned_points: List[Optional[Tuple[int, int]]] = []
    for i, p in enumerate(points):
        if p is not None or (i > 0 and points[i-1] is not None):
            cleaned_points.append(p)

    # Draw lines connecting the valid points
    if not cleaned_points:
        console.print(f"INFO: No valid points calculated in range for '{expression}'.")
        return

    logging.debug(f"Drawing {len([p for p in cleaned_points if p is not None])} points for '{expression}'")
    for i in range(len(cleaned_points) - 1):
        p1 = cleaned_points[i]
        p2 = cleaned_points[i+1]
        if p1 is not None and p2 is not None:
            canvas.draw_line(p1[0], p1[1], p2[0], p2[1])

    if errors_encountered > 0:
        console.print(f"WARN: Encountered {errors_encountered} evaluation error(s) for '{expression}'.")
    else:
         console.print(f"INFO: Finished plotting '{expression}'.")

def redraw_canvas_and_plots():
    """Clears canvas, draws axes/grid, and replots all stored expressions."""
    if not canvas: return
    logging.info("Redrawing canvas and all plotted functions.")
    draw_axes_and_grid()
    if not plotted_expressions:
        logging.info("No functions previously plotted.")
        return

    logging.info(f"Replotting {len(plotted_expressions)} function(s).")
    # Replot existing functions with their stored colors
    # Use enumerate to potentially re-apply colors consistently if needed,
    # but here we just use the stored color.
    for expression, color in plotted_expressions:
        plot_single_function(expression, color)
    if console:
        console.print(f"Canvas redrawn with {len(plotted_expressions)} function(s).")


def clear_plots():
    """Clears only the plotted functions list and redraws the base canvas."""
    global plotted_expressions, plot_color_index
    if not canvas or not console: return
    console.print("Clearing function plots...")
    plotted_expressions = []
    plot_color_index = 0
    # Redraw the base elements (axes and grid)
    draw_axes_and_grid()
    console.print("Plot area cleared.")

def display_help():
    """Prints help information to the console."""
    if not console: return
    console.print("\n--- Graphing Calculator Help ---")
    console.print("Commands:")
    console.print("  <expression>          Calculate (e.g., 5 * sqrt(pi))")
    console.print("  <var> = <expr>        Assign variable (e.g., r = 5)")
    console.print("  plot <expr_with_x>    Plot function of 'x' (e.g., plot sin(x)/x)")
    console.print("  set <range> = <val>   Set plot range (e.g., set x_max = 20)")
    console.print("                        <range> is x_min, x_max, y_min, or y_max")
    console.print("  clear                 Clear all function plots.")
    console.print("  help                  Show this help message.")
    console.print("  quit / exit           Exit the calculator.")
    console.print("Supported in expressions:")
    console.print("  Operators: +, -, *, /, **")
    console.print("  Functions: sin, cos, tan, asin, acos, atan, sqrt, log, log10, exp, abs")
    console.print("  Constants: pi, e")
    console.print("  Variables: 'x' (in plot), user-defined variables.")
    console.print("---------------------------------\n")


# --- Input Handling Logic ---

def handle_console_input(input_str: str):
    """Handles input from the Console, routing to appropriate actions."""
    global plot_color_index
    global x_min, x_max, y_min, y_max # Allow modification of range globals
    if not console: return

    input_str = input_str.strip()
    if not input_str: return

    cmd_lower = input_str.lower()

    try:
        if cmd_lower == "clear":
            clear_plots()

        elif cmd_lower == "help":
            display_help()

        elif cmd_lower == "quit" or cmd_lower == "exit":
            console.print("Exiting...")
            sidekick.shutdown()

        elif cmd_lower.startswith("plot "):
            expression = input_str[5:].strip()
            if not expression:
                console.print("ERROR: 'plot' command requires an expression.")
                return
            # Assign a color and add to list *before* plotting
            color = PLOT_COLORS[plot_color_index % len(PLOT_COLORS)]
            plotted_expressions.append((expression, color))
            plot_color_index += 1
            # Plot this new function (it will be drawn on top)
            plot_single_function(expression, color)

        elif cmd_lower.startswith("set "):
            # Format: set <var> = <value_expression>
            parts = input_str[4:].strip().split('=', 1)
            if len(parts) != 2:
                console.print("ERROR: Invalid 'set' syntax. Use 'set <range_var> = <value>'")
                return

            range_var = parts[0].strip().lower()
            value_expr = parts[1].strip()

            if range_var not in ['x_min', 'x_max', 'y_min', 'y_max']:
                console.print(f"ERROR: Unknown range variable '{range_var}'. Use x_min, x_max, y_min, or y_max.")
                return
            if not value_expr:
                console.print(f"ERROR: No value provided for 'set {range_var}'.")
                return

            # Evaluate the value expression
            new_value = aeval(value_expr)
            if not isinstance(new_value, (int, float)):
                console.print(f"ERROR: Value for '{range_var}' must evaluate to a number.")
                return

            # --- Update the global variable and validate range ---
            needs_redraw = False
            temp_x_min, temp_x_max, temp_y_min, temp_y_max = x_min, x_max, y_min, y_max

            if range_var == 'x_min':
                if new_value >= x_max: console.print(f"ERROR: x_min ({new_value}) cannot be >= x_max ({x_max})."); return
                x_min = float(new_value)
                needs_redraw = True
            elif range_var == 'x_max':
                if new_value <= x_min: console.print(f"ERROR: x_max ({new_value}) cannot be <= x_min ({x_min})."); return
                x_max = float(new_value)
                needs_redraw = True
            elif range_var == 'y_min':
                if new_value >= y_max: console.print(f"ERROR: y_min ({new_value}) cannot be >= y_max ({y_max})."); return
                y_min = float(new_value)
                needs_redraw = True
            elif range_var == 'y_max':
                if new_value <= y_min: console.print(f"ERROR: y_max ({new_value}) cannot be <= y_min ({y_min})."); return
                y_max = float(new_value)
                needs_redraw = True

            if needs_redraw:
                console.print(f"Set {range_var} = {new_value}. Redrawing canvas...")
                redraw_canvas_and_plots() # Redraw everything with new range
            else: # Should not happen with current checks, but defensively:
                 console.print(f"Set {range_var} = {new_value}. (No change detected?)")


        elif '=' in input_str and not input_str.strip().startswith('=='):
            # Variable assignment
            parts = input_str.split('=', 1)
            var_name = parts[0].strip()
            expr_to_eval = parts[1].strip()

            if not var_name.isidentifier():
                 console.print(f"ERROR: Invalid variable name: '{var_name}'")
                 return
            if not expr_to_eval:
                 console.print(f"ERROR: No expression provided for assignment to '{var_name}'")
                 return
            if var_name == 'x':
                 console.print(f"ERROR: Cannot assign to reserved variable 'x'")
                 return

            value = aeval(expr_to_eval)
            aeval.symtable[var_name] = value
            console.print(f"{var_name} = {value}")

        else:
            # Default: Simple calculation
            result = aeval(input_str)
            console.print(f"= {result}")

    except Exception as e:
        # Catch errors from asteval or other issues
        error_msg = f"ERROR: {e}"
        console.print(error_msg)
        logging.error(f"Error processing input '{input_str}': {e}")


def handle_module_error(module_name: str, error_message: str):
    """Generic error handler for Sidekick modules."""
    log_message = f"ERROR from {module_name}: {error_message}"
    logging.error(log_message)
    if console:
        try:
            console.print(f"[{module_name.upper()}_ERROR] {error_message}")
        except Exception as e:
            logging.error(f"Failed to print error to main console: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    try:
        # Create Sidekick modules (Canvas first for visual order)
        canvas = Canvas(
            instance_id="graph_canvas",
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT,
            bg_color=BG_COLOR
        )
        console = Console(
            instance_id="graph_console",
            show_input=True,
            initial_text="Graphing Calculator. Type 'help' for commands.",
        )
        # No Controls module needed now

        # Register callbacks
        console.on_input_text(handle_console_input)
        console.on_error(lambda err: handle_module_error("Console", err))
        canvas.on_error(lambda err: handle_module_error("Canvas", err))

        logging.info("Sidekick modules created and handlers registered.")

        # Initial drawing
        draw_axes_and_grid()
        console.print(f"Plot range: X=[{x_min:.1f}, {x_max:.1f}], Y=[{y_min:.1f}, {y_max:.1f}]")

        logging.info("Setup complete. Waiting for user input or Ctrl+C...")
        # Keep main thread alive - execution driven by callbacks
        sidekick.run_forever()
    except ConnectionRefusedError:
        logging.error("Connection refused. Is the Sidekick server running?")
        print("[ERROR] Connection refused. Is the Sidekick server (e.g., Vite dev server or VS Code extension) running?")
    except Exception as e:
        logging.exception("An unexpected error occurred in the main thread:")
        if console:
             try: console.print(f"FATAL ERROR: {e}")
             except: pass
    finally:
        logging.info("Cleanup complete.")