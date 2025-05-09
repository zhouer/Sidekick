import sidekick
from sidekick import Console

def echo(event):
    c.print(event.value)

c = Console(show_input=True, on_submit=echo)
sidekick.run_forever()
