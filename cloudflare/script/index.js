export default {
    async fetch(request, env, ctx) {
        const testPyContent = `import asyncio
import json
import random
import time
from js import sendHeroMessage, registerSidekickMessageHandler
from pyodide.ffi import create_proxy


def on_message(message):
    msg = json.loads(message)
    print("on_message:", msg)

# Create a persistent proxy for the function
on_message_proxy = create_proxy(on_message)

# Register the proxied message handler
registerSidekickMessageHandler(on_message_proxy)
print('python handler registered')

announce = {'id': 0, 'component': 'system', 'type': 'announce', 'payload': {'peerId': 'hero-1', 'role': 'hero', 'status': 'online', 'version': '0.0.6', 'timestamp': int(time.time() * 1000)}}
sendHeroMessage(json.dumps(announce))
print('python send announce')

clear_all = {'id': 0, 'component': 'global', 'type': 'clearAll'}
sendHeroMessage(json.dumps(clear_all))

spawn_grid = {'id': 0, 'component': 'grid', 'type': 'spawn', 'target': 'sidekick-grid-1', 'payload': {'numColumns': 5, 'numRows': 5}}
sendHeroMessage(json.dumps(spawn_grid))
print('python send spawn')

try:
    while True:
        colors = ["khaki", "lavender", "peachpuff", "pink", "plum", "powderblue", "", ""]
        random_color = random.choice(colors)
        update_grid = {'id': 0, 'component': 'grid', 'type': 'update', 'target': 'sidekick-grid-1', 'payload': {'action': 'setColor', 'options': {'color': random_color, 'x': random.randint(0, 4), 'y': random.randint(0, 4)}}}
        sendHeroMessage(json.dumps(update_grid))
        print('python send update')
        await asyncio.sleep(0.5)
except KeyboardInterrupt:
    print('python KeyboardInterrupt')

announce = {'id': 0, 'component': 'system', 'type': 'announce', 'payload': {'peerId': 'hero-1', 'role': 'hero', 'status': 'offline', 'version': '0.0.6', 'timestamp': int(time.time() * 1000)}}
sendHeroMessage(json.dumps(announce))`;

        return new Response(testPyContent, {
            headers: {
                'Content-Type': 'text/plain',
            },
        });
    },
};
