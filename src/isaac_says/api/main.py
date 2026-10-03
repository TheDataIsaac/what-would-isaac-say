"""The FastAPI app. Run it with `isaac-says serve`. Docs are at http://127.0.0.1:8000/docs"""

import logging
import uuid
from contextlib import asynccontextmanager

import openai
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import isaac_says
from isaac_says.api.resources import build_resources
from isaac_says.api.routes import admin, chat, meta
from isaac_says.config import get_settings
from isaac_says.logging_setup import configure_logging

log = logging.getLogger(__name__)

DESCRIPTION = """
A grounded assistant for the **Explain the Data** newsletter.

* It answers only from the newsletter, and every answer carries **verified quotes**.
* It reviews a reader's dashboard, chart or report against the newsletter's principles.
* When the newsletter does not cover a question, it says so and saves the question for Isaac.
"""


def create_app() -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Set up the database, search index and agent when the server starts.
        async with build_resources(get_settings()) as resources:
            app.state.resources = resources
            yield

    app = FastAPI(
        title="What Would Isaac Say?",
        description=DESCRIPTION,
        version=isaac_says.__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """Give each request an id, sent back in the X-Request-ID header and in error messages."""
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(openai.OpenAIError)
    async def openai_error_handler(request: Request, exc: openai.OpenAIError) -> JSONResponse:
        # 502 means this server is fine but OpenAI is not.
        log.error("OpenAI error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=502,
            content={
                "detail": "The language model is unavailable. Please try again.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # The full error goes to the log. The visitor sees no details.
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    app.include_router(meta.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app


# What uvicorn runs. The resources are created when it starts.
app = create_app()
