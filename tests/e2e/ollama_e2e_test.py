import asyncio
import json
import time

import httpx
import websockets


async def run_end_to_end():
    base = "http://localhost:7000/api"
    # 1) Create session via REST API
    async with httpx.AsyncClient(base_url=base) as client:
        resp = await client.post("/sessions", json={"model": "llama3.1:8b", "working_directory": "."})
        if resp.status_code != 201:
            print("[E2E] Failed to create session:", resp.text)
            return
        data = resp.json()
        session_id = data.get("session_id")
        print(f"[E2E] Created session: {session_id}")

    # 2) Open WebSocket and send a message
    ws_uri = f"ws://localhost:7000/api/ws/{session_id}"
    try:
        async with websockets.connect(ws_uri, timeout=20) as ws:
            # Send a simple user message
            await ws.send(json.dumps({"type": "user_message", "content": "ciao", "message_id": "m1"}))
            # Collect events for a short period
            end_time = time.time() + 40
            while time.time() < end_time:
                msg = await ws.recv()
                evt = json.loads(msg)
                print("[E2E] event:", evt.get("type"), "payload:", evt)
                if evt.get("type") == "turn_end":
                    break
    except Exception as e:
        print("[E2E] WebSocket error:", e)

if __name__ == "__main__":
    asyncio.run(run_end_to_end())
