"""FastAPI application entry point.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import articles, grammar, health, parse
from app.core.config import Settings, get_settings
from app.db.pool import create_pool
from app.nlp.tokenizer import SudachiTokenizer
from app.services.bootstrap import build_analyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _lifespan(settings: Settings) -> Callable[[FastAPI], AsyncIterator[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = create_pool(settings)
        try:
            tokenizer = SudachiTokenizer(settings.sudachi_dict, settings.sudachi_split_mode)
            app.state.pool = pool
            app.state.analyzer = build_analyzer(pool, tokenizer)
            yield
        finally:
            pool.close()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Morphological analysis of Japanese text with JLPT (N5–N1) grammar detection.",
        lifespan=_lifespan(settings),
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    for module in (parse, articles, grammar):
        app.include_router(module.router, prefix="/api/v1")
    return app


app = create_app()
