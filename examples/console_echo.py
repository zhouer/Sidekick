import sidekick
from sidekick import Console

c = Console(show_input=True)

def echo(text):
    c.print(text)

c.on_input_text(echo)
sidekick.run_forever()
