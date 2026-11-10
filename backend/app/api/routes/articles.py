from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import ArticleServiceDep, SettingsDep
from app.nlp import JLPTLevel
from app.schemas import (
    AnalysisMeta,
    ArticleCreate,
    ArticleDetail,
    ArticleHighlights,
    ArticleParsed,
    ArticleSummary,
    Highlight,
)
from app.services.article_service import ArticleNotFoundError, ParseOutcome

router = APIRouter(prefix="/articles", tags=["articles"])


def _parsed(outcome: ParseOutcome) -> ArticleParsed:
    return ArticleParsed(
        article=ArticleSummary(**outcome.article),
        highlight_count=outcome.highlight_count,
        meta=AnalysisMeta(
            tokenizer=outcome.result.tokenizer_info, elapsed_ms=outcome.result.elapsed_ms
        ),
    )


def _not_found(exc: ArticleNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("", response_model=ArticleParsed, status_code=status.HTTP_201_CREATED)
def create_article(
    payload: ArticleCreate, service: ArticleServiceDep, settings: SettingsDep
) -> ArticleParsed:
    """Store an article and pre-compute its JLPT highlights."""
    if len(payload.body) > settings.max_text_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"body exceeds {settings.max_text_chars} characters",
        )
    outcome = service.create_and_parse(
        title=payload.title.strip(),
        body=payload.body,
        source_url=str(payload.source_url) if payload.source_url else None,
    )
    return _parsed(outcome)


@router.get("", response_model=list[ArticleSummary])
def list_articles(
    service: ArticleServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ArticleSummary]:
    return [ArticleSummary(**row) for row in service.list(limit=limit, offset=offset)]


@router.get("/{article_id}", response_model=ArticleDetail)
def get_article(article_id: int, service: ArticleServiceDep) -> ArticleDetail:
    try:
        return ArticleDetail(**service.get(article_id))
    except ArticleNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/{article_id}/highlights",
    response_model=ArticleHighlights,
    response_model_exclude_none=True,
)
def get_highlights(
    article_id: int,
    service: ArticleServiceDep,
    level: Annotated[list[JLPTLevel] | None, Query(description="Repeatable: ?level=N3&level=N2")] = None,
    kind: Literal["grammar", "vocabulary"] | None = None,
) -> ArticleHighlights:
    """Return pre-computed highlights from the article's current parse run."""
    try:
        rows = service.highlights(article_id, levels=level, kind=kind)
    except ArticleNotFoundError as exc:
        raise _not_found(exc) from exc
    return ArticleHighlights(article_id=article_id, highlights=[Highlight.from_row(r) for r in rows])


@router.post("/{article_id}/reparse", response_model=ArticleParsed)
def reparse_article(article_id: int, service: ArticleServiceDep) -> ArticleParsed:
    """Re-run the analyzer (e.g. after grammar rules changed); keeps old runs for audit."""
    try:
        return _parsed(service.reparse(article_id))
    except ArticleNotFoundError as exc:
        raise _not_found(exc) from exc
