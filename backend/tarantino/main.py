import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from tarantino import __version__
from tarantino import auth
from tarantino.api import admin, cassettes, cinema, config, events, images, programme, rooms, vhs
from tarantino.config import Settings, get_settings
from tarantino.projector.adb import Adb
from tarantino.projector.cast import cast_wake
from tarantino.projector.remote import RemoteLink
from tarantino.services import Services
from tarantino.shows.orchestrator import Timing

PLACEHOLDER_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>tarantino</title></head>
<body style="font-family:sans-serif;background:#111;color:#eee;padding:2rem">
<h1>tarantino</h1><p>The backend is running, but the frontend has not been built yet.</p>
</body></html>"""

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per Jellyfin request is too noisy


def create_app(
    settings: Settings | None = None,
    *,
    jellyfin_transport: httpx.AsyncBaseTransport | None = None,
    adb_factory: Callable[[str], Adb] = Adb,
    timing: Timing | None = None,
    remote: RemoteLink | None = None,
    waker: Callable[[str], Awaitable[bool]] = cast_wake,
    run_jobs: bool = True,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services = Services.create(settings, jellyfin_transport, adb_factory, timing, remote, waker)
        app.state.services = services
        services.start(run_jobs=run_jobs)
        try:
            yield
        finally:
            await services.close()

    app = FastAPI(
        title="tarantino", version=__version__, lifespan=lifespan,
        docs_url="/api/docs", openapi_url="/api/openapi.json",
    )  # fmt: skip

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    admin_only = [Depends(auth.require_admin)]
    app.include_router(auth.router)
    app.include_router(admin.router, dependencies=admin_only)
    app.include_router(programme.router, dependencies=admin_only)
    app.include_router(rooms.router, dependencies=admin_only)
    app.include_router(config.router, dependencies=admin_only)
    app.include_router(cassettes.router, dependencies=admin_only)
    app.include_router(cinema.router)
    app.include_router(images.router)
    app.include_router(events.router)
    app.include_router(vhs.router)

    frontend_dir = settings.frontend_dir.resolve()

    # SvelteKit SPA: serve built files, fall back to index.html for client-side routes.
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = frontend_dir / "index.html"
        if not index.is_file():
            return HTMLResponse(PLACEHOLDER_HTML)
        candidate = (frontend_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(frontend_dir):
            return FileResponse(candidate)
        return FileResponse(index)

    return app


app = create_app()
