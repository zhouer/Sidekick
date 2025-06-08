import sidekick

width = 400
height = 300
c = sidekick.Canvas(width, height)

radius = 25
cx = radius
cy = radius
dx = 4
dy = 4
background_color = 'lightblue'
ball_color = 'white'

def animate():
    global cx, cy, dx, dy
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

sidekick.submit_interval(animate, 1/60)
sidekick.run_forever()
