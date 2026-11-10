"""JLPT grammar rules and the matcher that locates them in tokenized text."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.nlp.pattern import PatternError, PatternMatch, TokenPattern
from app.nlp.types import JLPTLevel, Token


@dataclass(frozen=True, slots=True)
class GrammarRule:
    """A JLPT grammar point plus the token patterns that detect it."""

    slug: str
    label: str
    level: JLPTLevel
    conjugation_formula: str
    meaning_en: str
    patterns: tuple[TokenPattern, ...]
    meaning_id: str | None = None
    priority: int = 0
    id: int | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GrammarRule:
        """Build a rule from a seed-file entry or a ``grammar_points`` row."""
        slug = data.get("slug", "<missing slug>")
        try:
            raw_patterns = data["token_patterns"]
            if isinstance(raw_patterns, str):  # JSONB fetched as text
                raw_patterns = json.loads(raw_patterns)
            if not isinstance(raw_patterns, list) or not raw_patterns:
                raise PatternError("'token_patterns' must be a non-empty list of patterns")
            return cls(
                slug=data["slug"],
                label=data["label"],
                level=JLPTLevel(data["jlpt_level"]),
                conjugation_formula=data["conjugation_formula"],
                meaning_en=data["meaning_en"],
                meaning_id=data.get("meaning_id"),
                priority=int(data.get("priority") or 0),
                id=data.get("id"),
                patterns=tuple(TokenPattern.from_list(p) for p in raw_patterns),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise PatternError(f"invalid grammar rule {slug!r}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class GrammarMatch:
    """One occurrence of a grammar point in a text."""

    rule: GrammarRule
    start: int
    end: int
    surface: str
    token_start: int
    token_end: int
    context_lemmas: tuple[str, ...] = ()

    @property
    def level(self) -> JLPTLevel:
        return self.rule.level

    @property
    def contextual_meaning(self) -> str:
        """Generic meaning bound to the concrete word it attaches to."""
        if not self.context_lemmas:
            return self.rule.meaning_en
        return f"{self.rule.meaning_en} — applied to「{'・'.join(self.context_lemmas)}」"


class GrammarMatcher:
    """Finds every grammar rule occurrence in a token sequence.

    Matches of the *same* rule never overlap (scanning resumes after a hit);
    matches of *different* rules may nest or overlap — e.g. 〜てしまう inside
    〜てしまっている — and are all returned so the UI can layer them.
    """

    def __init__(self, rules: Iterable[GrammarRule]) -> None:
        self._rules: tuple[GrammarRule, ...] = tuple(
            sorted(rules, key=lambda r: (-r.priority, r.slug))
        )

    @property
    def rules(self) -> tuple[GrammarRule, ...]:
        return self._rules

    def find(
        self,
        tokens: Sequence[Token],
        text: str,
        levels: Collection[JLPTLevel] | None = None,
    ) -> list[GrammarMatch]:
        matches = [
            match
            for rule in self._rules
            if not levels or rule.level in levels
            for match in self._find_rule(rule, tokens, text)
        ]
        matches.sort(key=lambda m: (m.start, -(m.end - m.start), -m.level.difficulty))
        return matches

    @staticmethod
    def _best_match(rule: GrammarRule, tokens: Sequence[Token], index: int) -> PatternMatch | None:
        candidates = (p.match_at(tokens, index) for p in rule.patterns)
        return max((c for c in candidates if c), key=lambda c: c.length, default=None)

    def _find_rule(
        self, rule: GrammarRule, tokens: Sequence[Token], text: str
    ) -> Iterator[GrammarMatch]:
        index = 0
        while index < len(tokens):
            found = self._best_match(rule, tokens, index)
            if found is None:
                index += 1
                continue
            start = tokens[found.token_start].start
            end = tokens[found.token_end - 1].end
            yield GrammarMatch(
                rule=rule,
                start=start,
                end=end,
                surface=text[start:end],
                token_start=found.token_start,
                token_end=found.token_end,
                context_lemmas=tuple(tokens[i].dictionary_form for i in found.context_indices),
            )
            index = found.last_index + 1
