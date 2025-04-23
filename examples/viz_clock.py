import datetime
import time
from sidekick import Viz, ObservableValue

clock = "Clock"
current_time = ObservableValue("Initializing")

v = Viz()
v.show("Clock", clock)
v.show("Current time", current_time)

while True:
    current_time.set(datetime.datetime.now().strftime("%H:%M:%S"))
    time.sleep(1)
