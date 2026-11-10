from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import AnalyzerDep, PoolDep
from app.db.repositories import GrammarRepository
from app.nlp import JLPTLevel
from app.schemas import GrammarPointOut, ReloadResult
from app.services.bootstrap import build_analyzer

router = APIRouter(prefix="/grammar", tags=["grammar"])


@router.get("", response_model=list[GrammarPointOut])
def list_grammar(pool: PoolDep, level: JLPTLevel | None = None) -> list[GrammarPointOut]:
    return [GrammarPointOut(**row) for row in GrammarRepository(pool).list_points(level)]


@router.post("/reload", response_model=ReloadResult)
def reload_rules(request: Request, pool: PoolDep, analyzer: AnalyzerDep) -> ReloadResult:
    """Hot-reload grammar and vocabulary master data without restarting the server.

    Protect this endpoint (auth / internal network) before exposing it publicly.
    """
    fresh = build_analyzer(pool, analyzer.tokenizer)
    request.app.state.analyzer = fresh  # atomic reference swap
    return ReloadResult(
        grammar_rules=fresh.grammar_rule_count, vocabulary_entries=fresh.vocabulary_count
    )
