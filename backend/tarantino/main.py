from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from tarantino import __version__
from tarantino.config import Settings, get_settings

PLACEHOLDER_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>tarantino</title></head>
<body style="font-family:sans-serif;background:#111;color:#eee;padding:2rem">
<h1>tarantino</h1><p>The backend is running, but the frontend has not been built yet.</p>
</body></html>"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="tarantino", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

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
