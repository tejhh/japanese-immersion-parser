from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.api.deps import AnalyzerDep, PoolDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(pool: PoolDep, analyzer: AnalyzerDep) -> dict[str, object]:
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        database = "ok"
    except Exception:  # noqa: BLE001 - health must report, not raise
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": __version__,
        "database": database,
        "tokenizer": analyzer.tokenizer.describe(),
        "grammar_rules": analyzer.grammar_rule_count,
        "vocabulary_entries": analyzer.vocabulary_count,
    }
