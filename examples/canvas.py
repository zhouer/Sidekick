# stress_test_canvas.py
import time
import random
import math
import logging
from typing import List, Dict, Any

# Import Sidekick components
from sidekick import Canvas, connection

# --- Configuration ---
CANVAS_WIDTH = 800
CANVAS_HEIGHT = 600
NUM_BALLS = 10        # Increase this number to increase stress
TARGET_FPS = 30
TARGET_FRAME_TIME = 1.0 / TARGET_FPS
MIN_RADIUS = 5
MAX_RADIUS = 15
MAX_INITIAL_SPEED = 150 # Pixels per second
COLORS = [
    "#e63946", "#f1faee", "#a8dadc", "#457b9d", "#1d3557",
    "#ffbe0b", "#fb5607", "#ff006e", "#8338ec", "#3a86ff",
    "#e07a5f", "#3d405b", "#81b29a", "#f2cc8f", "#e76f51",
]

# --- Logging Setup ---
# Configure connection logger for more details if needed
# logging.getLogger("SidekickConn").setLevel(logging.DEBUG)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Ball Simulation ---

# Define the structure for a ball
Ball = Dict[str, Any]

def create_balls(n: int, width: int, height: int) -> List[Ball]:
    """Creates a list of balls with random properties."""
    balls = []
    for i in range(n):
        radius = random.uniform(MIN_RADIUS, MAX_RADIUS)
        balls.append({
            "id": i,
            "x": random.uniform(radius, width - radius),
            "y": random.uniform(radius, height - radius),
            "vx": random.uniform(-MAX_INITIAL_SPEED, MAX_INITIAL_SPEED),
            "vy": random.uniform(-MAX_INITIAL_SPEED, MAX_INITIAL_SPEED),
            "r": radius,
            "color": random.choice(COLORS),
        })
    return balls

def update_balls(balls: List[Ball], dt: float, width: int, height: int):
    """Updates ball positions and handles boundary collisions."""
    for ball in balls:
        # Update position based on velocity and delta time
        ball["x"] += ball["vx"] * dt
        ball["y"] += ball["vy"] * dt

        # Boundary collision checks
        # Left wall
        if ball["x"] - ball["r"] < 0:
            ball["x"] = ball["r"] # Place ball at boundary
            ball["vx"] *= -1      # Reverse horizontal velocity
        # Right wall
        elif ball["x"] + ball["r"] > width:
            ball["x"] = width - ball["r"]
            ball["vx"] *= -1
        # Top wall
        if ball["y"] - ball["r"] < 0:
            ball["y"] = ball["r"]
            ball["vy"] *= -1      # Reverse vertical velocity
        # Bottom wall
        elif ball["y"] + ball["r"] > height:
            ball["y"] = height - ball["r"]
            ball["vy"] *= -1

# --- Error Handler (Optional) ---
def handle_canvas_error(error_message: str):
    """Callback for handling errors from the canvas instance."""
    logging.error(f"Received error from Canvas: {error_message}")

# --- Main Test Function ---

def run_stress_test():
    """Runs the canvas stress test."""
    logging.info("Starting Sidekick Canvas Stress Test...")
    logging.info(f"Target FPS: {TARGET_FPS}, Number of Balls: {NUM_BALLS}")

    canvas: Canvas | None = None # Initialize canvas to None
    try:
        # Ensure connection is active (good practice)
        connection.activate_connection()

        # Create the canvas instance
        canvas = Canvas(width=CANVAS_WIDTH, height=CANVAS_HEIGHT, bg_color="#202020", instance_id="stress-test-canvas")
        logging.info(f"Canvas '{canvas.target_id}' created.")

        # Register error handler (optional)
        canvas.on_error(handle_canvas_error)

        # Allow time for spawn message to be processed
        time.sleep(0.5)

        # Create initial balls
        balls = create_balls(NUM_BALLS, CANVAS_WIDTH, CANVAS_HEIGHT)

        # Timing variables
        last_frame_time = time.monotonic()
        frame_count = 0
        start_time = time.monotonic()

        logging.info("Starting animation loop (Press Ctrl+C to stop)...")

        # Main animation loop
        while True:
            # --- Timing and Delta Time ---
            current_time = time.monotonic()
            delta_time = current_time - last_frame_time
            last_frame_time = current_time

            # --- Update Ball Physics ---
            update_balls(balls, delta_time, CANVAS_WIDTH, CANVAS_HEIGHT)

            # --- Drawing ---
            # 1. Clear the canvas (essential for animation)
            #    Sends a command with action: "clear" and a new commandId
            canvas.clear() # Uses the default background color set during init

            # 2. Draw each ball
            for ball in balls:
                # Configure fill style for this ball
                # Sends command: action: "config", options: { fillStyle: ... }, commandId: ...
                canvas.config(fill_style=ball["color"])
                # Draw the filled circle
                # Sends command: action: "circle", options: { cx, cy, radius, filled }, commandId: ...
                canvas.draw_circle(cx=int(ball["x"]), cy=int(ball["y"]), radius=int(ball["r"]), filled=True)

            # --- Frame Rate Control ---
            frame_count += 1
            processing_end_time = time.monotonic()
            processing_time = processing_end_time - current_time
            sleep_time = TARGET_FRAME_TIME - processing_time

            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # Frame took longer than target time - potential bottleneck
                logging.warning(f"Frame took too long: {processing_time*1000:.2f} ms (Target: {TARGET_FRAME_TIME*1000:.2f} ms)")

            # Optional: Print average FPS periodically
            if frame_count % (TARGET_FPS * 5) == 0: # Every 5 seconds
                 elapsed_time = time.monotonic() - start_time
                 avg_fps = frame_count / elapsed_time
                 logging.info(f"Average FPS after {elapsed_time:.1f}s: {avg_fps:.2f}")


    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, stopping stress test.")
    except Exception as e:
        logging.exception(f"An error occurred during the stress test: {e}") # Log full traceback
    finally:
        # Clean up resources
        if canvas:
            logging.info(f"Removing canvas '{canvas.target_id}'.")
            canvas.remove()
        # Connection is closed automatically by atexit, but manual close can be added if needed
        # connection.close_connection()
        logging.info("Stress test finished.")

# --- Run the Test ---
if __name__ == "__main__":
    run_stress_test()