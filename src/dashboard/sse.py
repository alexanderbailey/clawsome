import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

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
    yield {"event": "ping", "data": "{}"}
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield msg
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "{}"}
    finally:
        _queues.discard(queue)


@router.get("/sse/updates")
async def sse_updates(request: Request):
    queue = asyncio.Queue(maxsize=100)
    _queues.add(queue)
    return EventSourceResponse(_event_generator(request, queue))
