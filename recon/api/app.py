"""FastAPI application factory, UI asset routes and the JSON error shape."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from recon import __version__
from recon.api.routes import (
    STAGE_BY_ERROR,
    STATUS_BY_ERROR,
    ApiProblem,
    RunStore,
    build_llm_provider,
    build_router,
    error_code,
    lookup_by_class,
)
from recon.config import Settings, get_settings
from recon.errors import ReconError

LOGGER = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TOKENS_PATH = PACKAGE_DIR.parent / "assets" / "tokens.css"
UI_ASSETS = {"index.html": "text/html", "app.css": "text/css", "app.js": "text/javascript"}
DEFAULT_REPORTS_DIR = Path("reports")
INTERNAL_MESSAGE = "the reconciliation could not be completed"


def error_body(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    """Wrap one failure in the documented `{"error": {...}}` envelope."""
    return {"error": {"code": code, "message": message, "details": details}}


def _static_response(path: Path, media_type: str) -> Response:
    """Read one UI asset as UTF-8 text so the response stays byte-stable."""
    return Response(content=path.read_text(encoding="utf-8"), media_type=media_type)


def add_error_handlers(app: FastAPI) -> None:
    """Register the handlers that produce the single documented error shape."""

    async def problem_handler(request: Request, error: ApiProblem) -> JSONResponse:
        """Render an endpoint-level failure."""
        return JSONResponse(
            status_code=error.status,
            content=error_body(error.code, error.message, {"stage": error.stage, **error.details}),
        )

    async def recon_handler(request: Request, error: ReconError) -> JSONResponse:
        """Map a `ReconError` subclass to 400, 422 or 500 per Architecture section 14."""
        status = lookup_by_class(STATUS_BY_ERROR, error, 500)
        if status >= 500:
            LOGGER.error("api_failure code=%s status=%d", error_code(error), status, exc_info=error)
        return JSONResponse(
            status_code=status,
            content=error_body(
                error_code(error),
                str(error),
                {"stage": lookup_by_class(STAGE_BY_ERROR, error, "report")},
            ),
        )

    async def request_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        """Render a malformed request (missing part or bad form field) in the same shape."""
        problems = [
            {
                "field": ".".join(str(part) for part in item["loc"][1:]),
                "message": str(item["msg"]),
            }
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(
                "request_invalid",
                "the request is missing a required part",
                {"stage": "parse", "problems": problems},
            ),
        )

    async def unexpected_handler(request: Request, error: Exception) -> JSONResponse:
        """Log the traceback and return a generic 500 without leaking internals."""
        LOGGER.exception("api_unexpected_failure path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", INTERNAL_MESSAGE, {"stage": "report"}),
        )

    app.add_exception_handler(ApiProblem, problem_handler)
    app.add_exception_handler(RequestValidationError, request_handler)
    app.add_exception_handler(ReconError, recon_handler)
    app.add_exception_handler(Exception, unexpected_handler)


def create_app(settings: Settings | None = None, reports_dir: Path | None = None) -> FastAPI:
    """Build the API and single-page UI for one settings snapshot."""
    config = settings or get_settings()
    store = RunStore(Path(reports_dir) if reports_dir else DEFAULT_REPORTS_DIR)
    app = FastAPI(
        title="Recon Investigator",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = config
    app.state.store = store
    app.include_router(build_router(store, config))
    add_error_handlers(app)

    @app.get("/")
    def index() -> Response:
        """Serve the single-page reconciliation UI."""
        return _static_response(STATIC_DIR / "index.html", UI_ASSETS["index.html"])

    @app.get("/static/{name}")
    def static_asset(name: str) -> Response:
        """Serve a UI asset; the design tokens come from `recon/assets/tokens.css`."""
        if name == "tokens.css":
            return _static_response(TOKENS_PATH, "text/css")
        if name in UI_ASSETS:
            return _static_response(STATIC_DIR / name, UI_ASSETS[name])
        raise ApiProblem(404, "asset_not_found", f"unknown asset: {name}", "parse")

    return app


def run_server(settings: Settings | None = None, port: int = 8000) -> None:
    """Start the local web UI and API on the given port."""
    config = settings or get_settings()
    provider = build_llm_provider(config)
    provider_name = "none" if provider is None else provider.name
    print(f"Recon Investigator: http://127.0.0.1:{port} (llm={provider_name})")
    uvicorn.run(create_app(config), host="127.0.0.1", port=port)
