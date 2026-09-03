import sys
import asyncio
import json

sys.path.insert(0, "/home/smeer/Downloads/Spooder/web_dashboard")
from server import SpooderServer, LEG_COXA_CHANNELS, LEG_FEMUR_CHANNELS

class MockWebSocket:
    def __init__(self, messages):
        self.messages = messages
        self.sent = []

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return json.dumps(self.messages.pop(0))

    async def send(self, msg):
        self.sent.append(json.loads(msg))

async def test_websocket_crouch_flow():
    server = SpooderServer()
    
    # Send set_crouch active=True
    ws1 = MockWebSocket([{"type": "set_crouch", "active": True}])
    await server.handler(ws1)
    assert server.crouch_active is True
    assert server.crouch_offset == -45
    print("[PASS] WS set_crouch active=True persisted state correctly")
    
    # Send set_gait active=False while crouch_active=True
    ws2 = MockWebSocket([{"type": "set_gait", "active": False}])
    await server.handler(ws2)
    assert server.crouch_active is True
    print("[PASS] WS set_gait active=False preserved crouch_active state")

    # Send set_crouch active=False
    ws3 = MockWebSocket([{"type": "set_crouch", "active": False}])
    await server.handler(ws3)
    assert server.crouch_active is False
    assert server.crouch_offset == 0
    print("[PASS] WS set_crouch active=False cleared crouch state")

if __name__ == "__main__":
    asyncio.run(test_websocket_crouch_flow())
