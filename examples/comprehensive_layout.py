import sidekick
from sidekick import Row, Column, Button, Console, Markdown, Label, Textbox, Grid, Canvas

# Create a console for output
console = Console()

# Create a canvas for drawing
canvas = Canvas(300, 200)

# Function to handle textbox submission
def on_textbox_submit(event):
    console.print(f"Submitted text: {event.value}")

# Function to handle button clicks
def on_button_click(button_name):
    console.print(f"Button {button_name} clicked!")

# Function to handle grid clicks
def on_grid_click(event):
    console.print(f"Grid clicked at ({event.x}, {event.y})")
    grid.set_color(event.x, event.y, "blue")

# Function to handle canvas clicks
def on_canvas_click(event):
    console.print(f"Canvas clicked at ({event.x}, {event.y})")
    canvas.clear()
    canvas.draw_circle(event.x, event.y, 20, fill_color="red")

# Create a grid
grid = Grid(5, 5, on_click=on_grid_click)
for x in range(5):
    for y in range(5):
        grid.set_text(x, y, f"{x},{y}")

# Set up canvas with initial drawing
canvas.draw_rect(50, 50, 200, 100, fill_color="lightblue", line_color="blue")
canvas.draw_text(100, 100, "Click me!", text_color="black")
canvas.on_click(on_canvas_click)

# Create a textbox
textbox = Textbox(placeholder="Enter text here...", on_submit=on_textbox_submit)

# Main layout structure
Column(
    # Header section
    Markdown("# Sidekick Layout Example"),
    Label("This example demonstrates various layout capabilities and components."),

    # First row with console and interactive components
    Row(
        # Left column with console
        Column(
            Label("Console Output:"),
            console,
            instance_id="left-column"
        ),

        # Right column with interactive components
        Column(
            Label("Interactive Components:"),

            # Buttons in a row
            Row(
                Button("Button 1", on_click=lambda _: on_button_click("1")),
                Button("Button 2", on_click=lambda _: on_button_click("2")),
                Button("Button 3", on_click=lambda _: on_button_click("3")),
                instance_id="button-row"
            ),

            # Textbox
            Label("Enter text and press Enter:"),
            textbox,

            instance_id="right-column"
        ),

        instance_id="main-row"
    ),

    # Second row with grid and canvas
    Row(
        # Grid section
        Column(
            Label("Interactive Grid (Click on cells):"),
            grid,
            instance_id="grid-column"
        ),

        # Canvas section
        Column(
            Label("Interactive Canvas (Click to draw):"),
            canvas,
            instance_id="canvas-column"
        ),

        instance_id="second-row"
    ),

    # Footer
    Label("© Sidekick Layout Example"),

    instance_id="main-layout"
)

# Run the application
sidekick.run_forever()
