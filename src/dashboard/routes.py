from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..browser.contexts import list_alive_contexts, get_alive_context, list_screenshots
from ..db import get_logs_by_context, get_context

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

router = APIRouter()


@router.get("/", response_class=RedirectResponse)
async def index():
    return RedirectResponse(url="/summary")


@router.get("/summary", response_class=HTMLResponse)
async def summary(request: Request):
    contexts = list_alive_contexts()
    return templates.TemplateResponse(
        "summary.html", {"request": request, "title": "Summary", "contexts": contexts}
    )


@router.get("/context/{ctx_id}", response_class=HTMLResponse)
async def context_view(request: Request, ctx_id: str):
    screenshots = list_screenshots(ctx_id)
    entry = get_alive_context(ctx_id)
    if not entry:
        db_ctx = get_context(ctx_id)
        if db_ctx:
            context = dict(db_ctx)
            context["alive"] = False
            return templates.TemplateResponse(
                "context.html",
                {"request": request, "title": db_ctx["name"], "context": context, "screenshots": screenshots},
            )
        return HTMLResponse("Context not found", status_code=404)
    context = {**entry["meta"], "alive": True}
    return templates.TemplateResponse(
        "context.html",
        {"request": request, "title": entry["meta"]["name"], "context": context, "screenshots": screenshots},
    )


@router.get("/logs/{ctx_id}", response_class=HTMLResponse)
async def logs_view(request: Request, ctx_id: str):
    entry = get_alive_context(ctx_id)
    db_ctx = get_context(ctx_id)
    name = (entry["meta"]["name"] if entry else None) or (db_ctx["name"] if db_ctx else ctx_id)
    logs = get_logs_by_context(ctx_id)
    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "title": f"Logs — {name}",
            "context_id": ctx_id,
            "context_name": name,
            "logs": list(reversed(logs)),
        },
    )


@router.get("/partials/context-list", response_class=HTMLResponse)
async def partial_context_list(request: Request):
    contexts = list_alive_contexts()
    if not contexts:
        return HTMLResponse(
            '<div class="empty-state">'
            "<p>No active browser contexts.</p>"
            '<p style="margin-top: 0.5rem; font-size: 0.85rem;">'
            "Create one via the API: <code>POST /api/contexts</code>"
            "</p></div>"
        )
    tpl = templates.env.get_template("partials/context_card.html")
    cards = [tpl.render(ctx=ctx) for ctx in contexts]
    return HTMLResponse('<div class="grid">' + "".join(cards) + "</div>")
