import datetime
import asyncio

import sidekick
from sidekick import Viz, ObservableValue

clock = "Clock"
current_time = ObservableValue("Initializing")

v = Viz()
v.show("Clock", clock)
v.show("Current time", current_time)

async def update_clock():
    while True:
        current_time.set(datetime.datetime.now().strftime("%H:%M:%S"))
        await asyncio.sleep(1)

sidekick.submit_task(update_clock())
sidekick.run_forever()
