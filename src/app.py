import asyncio
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .browser.manager import launch_browser, close_browser
from .browser.contexts import destroy_all_contexts, run_reaper
from .dashboard.sse import broadcast
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
    reaper = asyncio.create_task(
        run_reaper(lambda ctx_id: broadcast(event="context:destroyed", data={"id": ctx_id}))
    )
    yield
    reaper.cancel()
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
