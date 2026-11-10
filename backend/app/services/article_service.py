"""Use-cases for articles: ingest + pre-compute, re-parse, read highlights."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from app import __version__
from app.db.repositories import ArticleRepository, Row
from app.nlp import AnalysisResult, JLPTLevel, TextAnalyzer


class ArticleNotFoundError(LookupError):
    def __init__(self, article_id: int) -> None:
        super().__init__(f"article {article_id} not found")
        self.article_id = article_id


@dataclass(frozen=True, slots=True)
class ParseOutcome:
    article: Row
    highlight_count: int
    result: AnalysisResult


class ArticleService:
    def __init__(self, pool: ConnectionPool, analyzer: TextAnalyzer, *, store_tokens: bool) -> None:
        self._pool = pool
        self._analyzer = analyzer
        self._repo = ArticleRepository(pool)
        self._store_tokens = store_tokens

    def create_and_parse(self, *, title: str, body: str, source_url: str | None) -> ParseOutcome:
        # NLP runs *before* opening a transaction so no connection is held during CPU work.
        result = self._analyzer.analyze(body)
        with self._pool.connection() as conn, conn.transaction():
            article_id = self._repo.insert_article(conn, title=title, body=body, source_url=source_url)
            count = self._persist(conn, article_id, result)
        return ParseOutcome(self._require(article_id, include_body=False), count, result)

    def reparse(self, article_id: int) -> ParseOutcome:
        article = self._require(article_id, include_body=True)
        result = self._analyzer.analyze(article["body"])
        with self._pool.connection() as conn, conn.transaction():
            count = self._persist(conn, article_id, result)
        return ParseOutcome(self._require(article_id, include_body=False), count, result)

    def get(self, article_id: int) -> Row:
        return self._require(article_id, include_body=True)

    def list(self, *, limit: int, offset: int) -> list[Row]:
        return self._repo.list(limit=limit, offset=offset)

    def highlights(
        self, article_id: int, *, levels: Sequence[JLPTLevel] | None, kind: str | None
    ) -> list[Row]:
        self._require(article_id, include_body=False)
        return self._repo.current_highlights(article_id, levels=levels, kind=kind)

    # ---- internals ------------------------------------------------------------

    def _persist(self, conn, article_id: int, result: AnalysisResult) -> int:
        run_id = self._repo.insert_parse_run(
            conn,
            article_id=article_id,
            result=result,
            analyzer_version=__version__,
            store_tokens=self._store_tokens,
        )
        count = self._repo.insert_highlights(
            conn, article_id=article_id, parse_run_id=run_id, result=result
        )
        self._repo.mark_completed(conn, article_id=article_id, estimated_level=result.estimated_level)
        return count

    def _require(self, article_id: int, *, include_body: bool) -> Row:
        article = self._repo.get(article_id, include_body=include_body)
        if article is None:
            raise ArticleNotFoundError(article_id)
        return article
