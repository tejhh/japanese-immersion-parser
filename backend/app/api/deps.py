"""FastAPI dependency providers. Long-lived objects live on ``app.state``."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from psycopg_pool import ConnectionPool

from app.core.config import Settings
from app.nlp import TextAnalyzer
from app.services.article_service import ArticleService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_pool(request: Request) -> ConnectionPool:
    return request.app.state.pool


def get_analyzer(request: Request) -> TextAnalyzer:
    return request.app.state.analyzer


SettingsDep = Annotated[Settings, Depends(get_settings)]
PoolDep = Annotated[ConnectionPool, Depends(get_pool)]
AnalyzerDep = Annotated[TextAnalyzer, Depends(get_analyzer)]


def get_article_service(
    pool: PoolDep, analyzer: AnalyzerDep, settings: SettingsDep
) -> ArticleService:
    return ArticleService(pool, analyzer, store_tokens=settings.store_tokens)


ArticleServiceDep = Annotated[ArticleService, Depends(get_article_service)]
