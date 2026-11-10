"""Data-access layer. Raw, parameterised SQL that mirrors ``database/schema.sql``.

Write methods accept an open connection so the service layer can compose
several of them inside a single transaction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.nlp import AnalysisResult, GrammarRule, JLPTLevel, VocabularyEntry

Row = dict[str, Any]


class GrammarRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def load_active_rules(self) -> list[GrammarRule]:
        sql = """
            SELECT id, slug, label, jlpt_level, conjugation_formula,
                   meaning_en, meaning_id, token_patterns, priority
            FROM grammar_points
            WHERE is_active
            ORDER BY priority DESC, id
        """
        with self._pool.connection() as conn:
            return [GrammarRule.from_dict(row) for row in conn.execute(sql).fetchall()]

    def list_points(self, level: JLPTLevel | None = None) -> list[Row]:
        sql = """
            SELECT id, slug, label, jlpt_level, conjugation_formula, meaning_en,
                   meaning_id, example_ja, example_en
            FROM grammar_points
            WHERE is_active AND (%(level)s::jlpt_level IS NULL OR jlpt_level = %(level)s::jlpt_level)
            ORDER BY jlpt_level DESC, slug
        """
        with self._pool.connection() as conn:
            return conn.execute(sql, {"level": level.value if level else None}).fetchall()


class VocabularyRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def load_all(self) -> list[VocabularyEntry]:
        sql = "SELECT id, lemma, reading, part_of_speech, jlpt_level, meaning_en FROM vocabulary"
        with self._pool.connection() as conn:
            return [VocabularyEntry.from_dict(row) for row in conn.execute(sql).fetchall()]


class ArticleRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    # ---- writes (caller owns the transaction) -------------------------------

    @staticmethod
    def insert_article(conn: Connection, *, title: str, body: str, source_url: str | None) -> int:
        row = conn.execute(
            """
            INSERT INTO articles (title, body, source_url, body_sha256, parse_status)
            VALUES (%s, %s, %s, %s, 'processing')
            RETURNING id
            """,
            (title, body, source_url, hashlib.sha256(body.encode("utf-8")).hexdigest()),
        ).fetchone()
        return row["id"]

    @staticmethod
    def insert_parse_run(
        conn: Connection,
        *,
        article_id: int,
        result: AnalysisResult,
        analyzer_version: str,
        store_tokens: bool,
    ) -> int:
        """Insert a completed parse run and make it the article's current one."""
        conn.execute(
            "UPDATE parse_runs SET is_current = FALSE WHERE article_id = %s AND is_current",
            (article_id,),
        )
        tokens = (
            Jsonb([[t.start, t.end, t.dictionary_form, t.reading, t.pos_major] for t in result.tokens])
            if store_tokens
            else None
        )
        info = result.tokenizer_info
        row = conn.execute(
            """
            INSERT INTO parse_runs (article_id, analyzer_version, sudachi_dict, split_mode,
                                    token_count, tokens, status, is_current, elapsed_ms)
            VALUES (%s, %s, %s, %s, %s, %s, 'completed', TRUE, %s)
            RETURNING id
            """,
            (
                article_id,
                analyzer_version,
                info.get("dictionary", "core"),
                info.get("split_mode", "C"),
                len(result.tokens),
                tokens,
                result.elapsed_ms,
            ),
        ).fetchone()
        return row["id"]

    @staticmethod
    def insert_highlights(
        conn: Connection, *, article_id: int, parse_run_id: int, result: AnalysisResult
    ) -> int:
        rows: list[tuple[Any, ...]] = []
        for g in result.grammar:
            if g.rule.id is None:
                raise ValueError(f"grammar rule {g.rule.slug!r} has no database id")
            rows.append((
                parse_run_id, article_id, "grammar", g.rule.id, None, g.level.value,
                g.start, g.end, g.token_start, g.token_end, g.surface, g.contextual_meaning,
            ))
        for v in result.vocabulary:
            if v.entry.id is None:
                raise ValueError(f"vocabulary entry {v.entry.lemma!r} has no database id")
            rows.append((
                parse_run_id, article_id, "vocabulary", None, v.entry.id, v.level.value,
                v.start, v.end, v.token_index, v.token_index + 1, v.surface, v.entry.meaning_en,
            ))
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO article_highlights (
                        parse_run_id, article_id, kind, grammar_point_id, vocabulary_id,
                        jlpt_level, start_index, end_index, token_start, token_end,
                        surface, contextual_meaning)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
        return len(rows)

    @staticmethod
    def mark_completed(
        conn: Connection, *, article_id: int, estimated_level: JLPTLevel | None
    ) -> None:
        conn.execute(
            "UPDATE articles SET parse_status = 'completed', estimated_level = %s WHERE id = %s",
            (estimated_level.value if estimated_level else None, article_id),
        )

    # ---- reads --------------------------------------------------------------

    def get(self, article_id: int, *, include_body: bool = True) -> Row | None:
        columns = "id, title, source_url, char_length, estimated_level, parse_status, created_at"
        if include_body:
            columns += ", body"
        with self._pool.connection() as conn:
            return conn.execute(
                f"SELECT {columns} FROM articles WHERE id = %s", (article_id,)
            ).fetchone()

    def list(self, *, limit: int, offset: int) -> list[Row]:
        with self._pool.connection() as conn:
            return conn.execute(
                """
                SELECT id, title, source_url, char_length, estimated_level, parse_status, created_at
                FROM articles ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
                """,
                (limit, offset),
            ).fetchall()

    def current_highlights(
        self,
        article_id: int,
        *,
        levels: Sequence[JLPTLevel] | None = None,
        kind: str | None = None,
    ) -> list[Row]:
        sql = """
            SELECT * FROM v_current_highlights
            WHERE article_id = %(article_id)s
              AND (%(levels)s::text[] IS NULL OR jlpt_level::text = ANY(%(levels)s::text[]))
              AND (%(kind)s::highlight_kind IS NULL OR kind = %(kind)s::highlight_kind)
            ORDER BY start_index, end_index DESC, id
        """
        params = {
            "article_id": article_id,
            "levels": [lv.value for lv in levels] if levels else None,
            "kind": kind,
        }
        with self._pool.connection() as conn:
            return conn.execute(sql, params).fetchall()
