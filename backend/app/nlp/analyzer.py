"""High-level façade: text in, positioned JLPT highlights out."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.nlp.grammar import GrammarMatch, GrammarMatcher
from app.nlp.types import JLPTLevel, Token
from app.nlp.vocabulary import VocabularyMatch, VocabularyMatcher


class Tokenizer(Protocol):
    """Anything that can split Japanese text into positioned tokens."""

    def tokenize(self, text: str) -> list[Token]: ...

    def describe(self) -> dict[str, str]: ...


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    text: str
    tokens: tuple[Token, ...]
    grammar: tuple[GrammarMatch, ...]
    vocabulary: tuple[VocabularyMatch, ...]
    estimated_level: JLPTLevel | None
    elapsed_ms: float
    tokenizer_info: dict[str, str] = field(default_factory=dict)

    @property
    def level_counts(self) -> dict[JLPTLevel, int]:
        counts = Counter(m.level for m in (*self.grammar, *self.vocabulary))
        return {level: counts.get(level, 0) for level in JLPTLevel}


def estimate_level(levels: Sequence[JLPTLevel], min_share: float = 0.1) -> JLPTLevel | None:
    """Return the hardest level that accounts for at least ``min_share`` of hits.

    A single stray N1 word in an otherwise N5 text should not label the text
    N1, so rare levels are ignored below the ``min_share`` threshold.
    """
    if not levels:
        return None
    counts = Counter(levels)
    total = len(levels)
    for level in sorted(counts, key=lambda lv: lv.difficulty, reverse=True):
        if counts[level] / total >= min_share:
            return level
    return min(counts, key=lambda lv: lv.difficulty)


class TextAnalyzer:
    """Combines a tokenizer with grammar and vocabulary matchers."""

    def __init__(
        self,
        tokenizer: Tokenizer,
        grammar_matcher: GrammarMatcher,
        vocabulary_matcher: VocabularyMatcher,
    ) -> None:
        self._tokenizer = tokenizer
        self._grammar = grammar_matcher
        self._vocabulary = vocabulary_matcher

    @property
    def tokenizer(self) -> Tokenizer:
        return self._tokenizer

    @property
    def grammar_rule_count(self) -> int:
        return len(self._grammar.rules)

    @property
    def vocabulary_count(self) -> int:
        return len(self._vocabulary)

    def analyze(
        self,
        text: str,
        *,
        levels: Collection[JLPTLevel] | None = None,
        include_vocabulary: bool = True,
    ) -> AnalysisResult:
        started = time.perf_counter()
        tokens = self._tokenizer.tokenize(text)
        grammar = self._grammar.find(tokens, text, levels)
        vocabulary = self._vocabulary.find(tokens, levels) if include_vocabulary else []
        estimated = estimate_level([m.level for m in grammar] + [m.level for m in vocabulary])
        return AnalysisResult(
            text=text,
            tokens=tuple(tokens),
            grammar=tuple(grammar),
            vocabulary=tuple(vocabulary),
            estimated_level=estimated,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            tokenizer_info=self._tokenizer.describe(),
        )
