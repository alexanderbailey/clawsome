from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from .auth import require_token
from ..browser.contexts import (
    create_context,
    get_alive_context,
    list_alive_contexts,
    navigate_to,
    take_screenshot,
    upload_screenshot,
    list_screenshots,
    get_saved_screenshot,
    exec_action,
    get_snapshot,
    destroy_context,
)
from ..db import insert_log, get_logs_by_context
from ..dashboard.sse import broadcast

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class CreateContextBody(BaseModel):
    name: str
    profile: str | None = None
    external: bool = False


class GotoBody(BaseModel):
    url: str
    timeout: int | None = None
    waitUntil: str | None = None


class ExecBody(BaseModel):
    action: str
    selector: str | None = None
    value: str | None = None
    script: str | None = None
    timeout: int | None = None


class LogBody(BaseModel):
    level: str | None = None
    message: str


@router.get("/contexts")
async def list_contexts_route():
    return list_alive_contexts()


@router.post("/contexts", status_code=201)
async def create_context_route(body: CreateContextBody):
    meta = await create_context(name=body.name, profile=body.profile, external=body.external)
    insert_log(context_id=meta["id"], level="info", message=f"Context created: {body.name}")
    broadcast(event="context:created", data=meta)
    return meta


@router.get("/contexts/{ctx_id}")
async def get_context_route(ctx_id: str):
    entry = get_alive_context(ctx_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Context not found")
    return entry["meta"]


@router.delete("/contexts/{ctx_id}")
async def destroy_context_route(ctx_id: str):
    try:
        await destroy_context(ctx_id)
        insert_log(context_id=ctx_id, level="info", message="Context destroyed")
        broadcast(event="context:destroyed", data={"id": ctx_id})
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/contexts/{ctx_id}/goto")
async def goto_route(ctx_id: str, body: GotoBody):
    try:
        kwargs = {}
        if body.timeout is not None:
            kwargs["timeout"] = body.timeout
        if body.waitUntil is not None:
            kwargs["wait_until"] = body.waitUntil
        result = await navigate_to(ctx_id, body.url, **kwargs)
        insert_log(context_id=ctx_id, level="info", message=f"Navigated to {body.url}")
        broadcast(event="context:updated", data={"id": ctx_id, "url": body.url})
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/contexts/{ctx_id}/snapshot")
async def snapshot_route(ctx_id: str):
    try:
        return await get_snapshot(ctx_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/contexts/{ctx_id}/screenshot")
async def screenshot_route(ctx_id: str):
    try:
        buffer = await take_screenshot(ctx_id)
        return Response(content=buffer, media_type="image/png")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/contexts/{ctx_id}/screenshot", status_code=204)
async def upload_screenshot_route(ctx_id: str, request: Request):
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="PNG body required")
    try:
        upload_screenshot(ctx_id, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=204)


@router.get("/contexts/{ctx_id}/screenshots")
async def list_screenshots_route(ctx_id: str):
    return list_screenshots(ctx_id)


@router.get("/contexts/{ctx_id}/screenshots/{filename}")
async def get_screenshot_file_route(ctx_id: str, filename: str):
    try:
        png = get_saved_screenshot(ctx_id, filename)
        return Response(content=png, media_type="image/png")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/contexts/{ctx_id}/exec")
async def exec_route(ctx_id: str, body: ExecBody):
    try:
        result = await exec_action(
            ctx_id,
            action=body.action,
            selector=body.selector,
            value=body.value,
            script=body.script,
            timeout=body.timeout,
        )
        insert_log(
            context_id=ctx_id,
            level="info",
            message=f"Executed: {body.action} {body.selector or ''}".strip(),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/contexts/{ctx_id}/logs")
async def get_logs_route(ctx_id: str):
    return get_logs_by_context(ctx_id)


@router.post("/contexts/{ctx_id}/logs", status_code=201)
async def append_log_route(ctx_id: str, body: LogBody):
    insert_log(context_id=ctx_id, level=body.level or "info", message=body.message)
    broadcast(event="log:new", data={"contextId": ctx_id, "level": body.level, "message": body.message})
    return {"ok": True}
