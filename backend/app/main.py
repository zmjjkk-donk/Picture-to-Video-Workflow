from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .services.frontend import FrontendStaticFiles

from .config import Settings, get_settings
from .db import init_database
from .api.routes import router


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or get_settings()
    runtime.ensure_directories()
    engine, session_factory = init_database(runtime)
    app = FastAPI(title=runtime.app_name, version=runtime.app_version)
    app.state.settings = runtime
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    frontend_dist = runtime.project_root / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", FrontendStaticFiles(directory=frontend_dist, html=True), name="frontend")

    @app.exception_handler(Exception)
    async def unhandled_exception(_request: Request, exc: Exception):
        if isinstance(exc, JSONResponse):
            return exc
        return JSONResponse(status_code=500, content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}})

    return app


app = create_app()

