import time
from sidekick import Canvas

width = 400
height = 300

radius = 25
cx = radius
cy = radius
dx = 4
dy = 4
background_color = 'lightblue'
ball_color = 'white'

c = Canvas(width, height)
c.on_click(print)
time.sleep(0.1)

try:
    while True:
        with c.buffer() as buf:
            buf.draw_rect(0, 0, width, height, fill_color=background_color)
            buf.draw_circle(cx, cy, radius, fill_color=ball_color)

        cx += dx
        cy += dy

        if cx + radius > width:
            dx = -dx
            cx = width - radius
        elif cx - radius < 0:
            dx = -dx
            cx = radius

        if cy + radius > height:
            dy = -dy
            cy = height - radius
        elif cy - radius < 0:
            dy = -dy
            cy = radius

        time.sleep(1/60)
except KeyboardInterrupt:
    pass