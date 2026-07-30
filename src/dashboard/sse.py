import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

# How long the stream waits for an event before emitting a keepalive. The
# client sizes its own staleness threshold from this, so the cadence is
# decided in one place instead of being copied into live.js by hand.
PING_INTERVAL_S = 15.0

_PING = {"event": "ping", "data": json.dumps({"intervalMs": int(PING_INTERVAL_S * 1000)})}

_queues: set[asyncio.Queue] = set()


def broadcast(*, event: str, data: dict):
    message = {"event": event, "data": json.dumps(data)}
    dead = []
    for q in _queues:
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _queues.discard(q)


async def _event_generator(request: Request, queue: asyncio.Queue):
    yield _PING
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL_S)
                yield msg
            except asyncio.TimeoutError:
                yield _PING
    finally:
        _queues.discard(queue)


@router.get("/sse/updates")
async def sse_updates(request: Request):
    queue = asyncio.Queue(maxsize=100)
    _queues.add(queue)
    return EventSourceResponse(_event_generator(request, queue))
