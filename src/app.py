import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .browser.manager import launch_browser, close_browser
from .browser.contexts import destroy_all_contexts
from .api.contexts import router as api_router
from .dashboard.routes import router as dashboard_router
from .dashboard.sse import router as sse_router
from .dashboard.ws import router as ws_router

ROOT = Path(__file__).parent.parent
SRC = Path(__file__).parent

PORT = int(os.environ.get("PORT", "3000"))
HOST = os.environ.get("HOST", "0.0.0.0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    (ROOT / "data").mkdir(exist_ok=True)
    init_db(str(ROOT / "data" / "clawsome.db"))
    await launch_browser()
    yield
    await destroy_all_contexts()
    await close_browser()


app = FastAPI(lifespan=lifespan)

app.mount("/public", StaticFiles(directory=str(SRC / "public")), name="public")

app.include_router(api_router)
app.include_router(dashboard_router)
app.include_router(sse_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
