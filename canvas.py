# hero_canvas_stress_test.py
import time
import math
import random
from sidekick import Canvas, set_url, close_connection
from sidekick import connection as sidekick_connection # Import connection module
import logging

# --- Configuration ---
CANVAS_WIDTH = 800
CANVAS_HEIGHT = 600
BACKGROUND_COLOR = "#1a1a1a" # Dark background for better contrast
SIDEKICK_URL = "ws://localhost:5163"
LOG_LEVEL = logging.INFO # Set to DEBUG for SidekickConn logs

# --- Stress Test Parameters ---
NUM_BATCHES = 10         # How many major drawing phases
COMMANDS_PER_BATCH = 200 # How many draw commands per phase (approx)
DELAY_BETWEEN_BATCHES = 0.5 # Seconds to pause between phases
DELAY_BETWEEN_COMMANDS = 0.001 # Tiny delay between individual commands (can be 0)

# --- Setup Logging ---
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger("SidekickConn").setLevel(LOG_LEVEL)
logging.getLogger("CanvasStressTest").setLevel(LOG_LEVEL)
logger = logging.getLogger("CanvasStressTest")

# --- Helper Functions ---
def random_color(hue_start=0, hue_end=360, saturation=80, lightness=60):
    """Generates a random HSL color string."""
    hue = random.randint(hue_start, hue_end)
    return f"hsl({hue}, {saturation}%, {lightness}%)"

def draw_expanding_circles(canvas: Canvas, cx, cy, max_radius, steps, color):
    """Draws concentric circles."""
    if not canvas: return
    canvas.config(stroke_style=color, line_width=1, fill_style=None) # No fill
    for i in range(1, steps + 1):
        radius = (max_radius / steps) * i
        canvas.draw_circle(cx, cy, radius, filled=False)
        if DELAY_BETWEEN_COMMANDS > 0: time.sleep(DELAY_BETWEEN_COMMANDS)

def draw_radiating_lines(canvas: Canvas, cx, cy, length, num_lines, color_func):
    """Draws lines radiating from a center point."""
    if not canvas: return
    canvas.config(line_width=1, fill_style=None)
    angle_step = 360 / num_lines
    for i in range(num_lines):
        angle = math.radians(i * angle_step)
        end_x = cx + length * math.cos(angle)
        end_y = cy + length * math.sin(angle)
        canvas.config(stroke_style=color_func(i, num_lines))
        canvas.draw_line(cx, cy, end_x, end_y)
        if DELAY_BETWEEN_COMMANDS > 0: time.sleep(DELAY_BETWEEN_COMMANDS)

def draw_random_rects(canvas: Canvas, count, max_size, color_func):
    """Draws randomly placed and sized rectangles (filled)."""
    if not canvas: return
    canvas.config(stroke_style=None, line_width=1) # No stroke for filled rects
    for i in range(count):
        w = random.randint(5, max_size)
        h = random.randint(5, max_size)
        x = random.randint(0, canvas.width - w)
        y = random.randint(0, canvas.height - h)
        canvas.config(fill_style=color_func(i, count))
        canvas.draw_rect(x, y, w, h, filled=True)
        if DELAY_BETWEEN_COMMANDS > 0: time.sleep(DELAY_BETWEEN_COMMANDS)

def draw_grid(canvas: Canvas, step, color):
    """Draws a grid."""
    if not canvas: return
    canvas.config(stroke_style=color, line_width=0.5, fill_style=None)
    # Vertical lines
    for x in range(step, canvas.width, step):
        canvas.draw_line(x, 0, x, canvas.height)
        if DELAY_BETWEEN_COMMANDS > 0: time.sleep(DELAY_BETWEEN_COMMANDS)
    # Horizontal lines
    for y in range(step, canvas.height, step):
        canvas.draw_line(0, y, canvas.width, y)
        if DELAY_BETWEEN_COMMANDS > 0: time.sleep(DELAY_BETWEEN_COMMANDS)

# --- Main Test Execution ---
if __name__ == "__main__":
    logger.info("Starting Canvas Stress Test...")
    canvas: Canvas | None = None # Initialize canvas variable

    try:
        logger.info("Connection activated.")
        logger.info(f"Creating Canvas ({CANVAS_WIDTH}x{CANVAS_HEIGHT}, BG: {BACKGROUND_COLOR})...")
        canvas = Canvas(width=CANVAS_WIDTH, height=CANVAS_HEIGHT, bg_color=BACKGROUND_COLOR, instance_id="stress-test-canvas")
        # Wait briefly to ensure spawn message is likely processed
        time.sleep(0.5)
        logger.info("Canvas created.")

        # --- Start Drawing Batches ---
        total_commands = 0
        start_test_time = time.time()

        for batch_num in range(1, NUM_BATCHES + 1):
            logger.info(f"--- Starting Batch {batch_num}/{NUM_BATCHES} ---")
            batch_start_time = time.time()
            commands_in_batch = 0

            # Clear canvas at the start of some batches for visual clarity
            if batch_num % 3 == 1: # Clear every 3 batches (1, 4, 7...)
                 logger.info("Clearing canvas...")
                 canvas.clear() # Clears to background color
                 commands_in_batch += 1
                 time.sleep(0.1) # Small delay after clear

            # Determine drawing pattern for this batch
            pattern_type = batch_num % 4

            if pattern_type == 1: # Expanding Circles
                logger.info("Drawing expanding circles...")
                num_circles = COMMANDS_PER_BATCH // 2 # Roughly half the commands
                max_r = min(canvas.width, canvas.height) // 2 - 10
                cx = canvas.width / 2
                cy = canvas.height / 2
                draw_expanding_circles(canvas, cx, cy, max_r, num_circles, random_color(0, 120)) # Reds/Yellows/Greens
                commands_in_batch += num_circles
            elif pattern_type == 2: # Radiating Lines
                logger.info("Drawing radiating lines...")
                num_lines = COMMANDS_PER_BATCH
                length = min(canvas.width, canvas.height) * 0.45
                cx = random.randint(int(length), int(canvas.width - length))
                cy = random.randint(int(length), int(canvas.height - length))
                draw_radiating_lines(canvas, cx, cy, length, num_lines,
                                     lambda i, total: f"hsl({120 + (i/total)*120}, 70%, 60%)") # Greens/Cyans/Blues
                commands_in_batch += num_lines
            elif pattern_type == 3: # Random Rectangles
                logger.info("Drawing random rectangles...")
                num_rects = COMMANDS_PER_BATCH
                max_rect_size = 50
                draw_random_rects(canvas, num_rects, max_rect_size,
                                  lambda i, total: f"hsl({240 + (i/total)*120}, 60%, 70%)") # Blues/Magentas/Reds
                commands_in_batch += num_rects
            else: # Grid
                logger.info("Drawing grid...")
                grid_step = 40
                num_lines_approx = (canvas.width // grid_step) + (canvas.height // grid_step)
                draw_grid(canvas, grid_step, "rgba(200, 200, 200, 0.3)") # Light grey grid
                commands_in_batch += num_lines_approx # Approximate count

            total_commands += commands_in_batch
            batch_duration = time.time() - batch_start_time
            logger.info(f"--- Finished Batch {batch_num} ({commands_in_batch} commands) in {batch_duration:.3f}s ---")

            # Pause between batches
            if batch_num < NUM_BATCHES:
                logger.info(f"Pausing for {DELAY_BETWEEN_BATCHES}s...")
                time.sleep(DELAY_BETWEEN_BATCHES)

        # --- Test Finished ---
        end_test_time = time.time()
        total_duration = end_test_time - start_test_time
        logger.info("="*40)
        logger.info("Canvas Stress Test Finished!")
        logger.info(f"Total Commands Sent (approx): {total_commands}")
        logger.info(f"Total Duration: {total_duration:.3f}s")
        logger.info("Check the Sidekick Canvas visually for correctness and smoothness.")
        logger.info("="*40)

        # Keep alive for a bit longer to observe final state
        logger.info("Keeping connection alive for 10 more seconds...")
        time.sleep(10)

    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user.")
    except Exception as e:
        logger.exception("An unhandled exception occurred during the test!")
    finally:
        # Clean up
        if canvas:
            logger.info("Removing canvas...")
            canvas.remove()
            time.sleep(0.1) # Give remove message time to send
        logger.info("Closing connection...")
        close_connection()
        logger.info("Script finished.")