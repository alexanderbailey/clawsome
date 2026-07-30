import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..browser.contexts import get_alive_context, take_screenshot

router = APIRouter()

# How long the loop sleeps between captures.
FRAME_INTERVAL_S = 1.5

# Sent on connect, and in place of any frame we cannot produce. Without it a
# socket that has stopped delivering is indistinguishable from one that simply
# has nothing to send: an external context that has not pushed a screenshot yet
# yields no frames at all, so frame silence on its own is not evidence of a
# dead connection. Carries the cadence so the client can size its own staleness
# threshold rather than hard-coding a copy of the number above.
_PING = json.dumps({"type": "ping", "intervalMs": int(FRAME_INTERVAL_S * 1000)})


@router.websocket("/ws/screenshots/{ctx_id}")
async def screenshot_ws(websocket: WebSocket, ctx_id: str):
    await websocket.accept()
    await websocket.send_text(_PING)
    try:
        while True:
            if not get_alive_context(ctx_id):
                await websocket.close(code=1000, reason="Context gone")
                break
            try:
                png = await take_screenshot(ctx_id)
                await websocket.send_bytes(png)
            except ValueError:
                # No screenshot yet (external context). Keep the socket audibly
                # alive so silence stays a reliable signal that it is dead.
                await websocket.send_text(_PING)
            await asyncio.sleep(FRAME_INTERVAL_S)
    except (WebSocketDisconnect, Exception):
        pass
