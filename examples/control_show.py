import sidekick
from sidekick import Control, Console

console = Console()

def input_text_handler(control_id, text):
    console.print("You said:", text)

def click_handler(control_id):
    if control_id == "button_a":
        console.print("Button A clicked!")
    elif control_id == "button_b":
        console.print("Button B clicked!")

control = Control()
control.on_input_text(input_text_handler)
control.on_click(click_handler)
control.add_text_input("text_input", "Type something...", "", "Send")
control.add_button("button_a", "A")
control.add_button("button_b", "B")

sidekick.run_forever()
