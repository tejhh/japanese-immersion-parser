"""Wiring helpers that assemble the analyzer from database-backed master data."""

from __future__ import annotations

import logging

from psycopg_pool import ConnectionPool

from app.db.repositories import GrammarRepository, VocabularyRepository
from app.nlp import GrammarMatcher, TextAnalyzer, Tokenizer, VocabularyMatcher

logger = logging.getLogger(__name__)


def build_analyzer(pool: ConnectionPool, tokenizer: Tokenizer) -> TextAnalyzer:
    rules = GrammarRepository(pool).load_active_rules()
    vocabulary = VocabularyRepository(pool).load_all()
    if not rules:
        logger.warning("No active grammar points found — did you run scripts/seed_db.py?")
    logger.info("Loaded %d grammar rules and %d vocabulary entries", len(rules), len(vocabulary))
    return TextAnalyzer(tokenizer, GrammarMatcher(rules), VocabularyMatcher(vocabulary))
