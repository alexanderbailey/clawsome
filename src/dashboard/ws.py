import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..browser.contexts import get_alive_context, take_screenshot

router = APIRouter()


@router.websocket("/ws/screenshots/{ctx_id}")
async def screenshot_ws(websocket: WebSocket, ctx_id: str):
    await websocket.accept()
    try:
        while True:
            if not get_alive_context(ctx_id):
                await websocket.close(code=1000, reason="Context gone")
                break
            try:
                png = await take_screenshot(ctx_id)
                await websocket.send_bytes(png)
            except ValueError:
                pass  # no screenshot yet (external context)
            await asyncio.sleep(1.5)
    except (WebSocketDisconnect, Exception):
        pass
