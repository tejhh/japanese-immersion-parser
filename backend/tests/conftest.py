"""Shared fixtures.

``build_tokens`` lets tests describe Sudachi-like output by hand, so the
matching logic is exercised without SudachiPy installed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.nlp import GrammarMatcher, GrammarRule, Token, VocabularyEntry

SEED_DIR = Path(__file__).resolve().parents[2] / "database" / "seeds"

# (surface, dictionary_form, normalized_form, pos[0], pos[1], conjugation_form)
TokenSpec = tuple[str, str, str, str, str, str]


def build_tokens(specs: list[TokenSpec], text: str | None = None) -> tuple[str, list[Token]]:
    """Create contiguous tokens; returns ``(text, tokens)``."""
    tokens: list[Token] = []
    offset = 0
    for i, (surface, dic, norm, pos0, pos1, conj) in enumerate(specs):
        tokens.append(
            Token(
                index=i,
                surface=surface,
                dictionary_form=dic,
                normalized_form=norm,
                reading="",
                pos=(pos0, pos1, "*", "*", "*", conj),
                start=offset,
                end=offset + len(surface),
            )
        )
        offset += len(surface)
    joined = "".join(s[0] for s in specs)
    assert text is None or text == joined, "token surfaces must concatenate to text"
    return joined, tokens


class FakeTokenizer:
    """Returns pre-built tokens for known sentences."""

    def __init__(self, fixtures: dict[str, list[Token]]) -> None:
        self._fixtures = fixtures

    def tokenize(self, text: str) -> list[Token]:
        return self._fixtures[text]

    def describe(self) -> dict[str, str]:
        return {"engine": "fake", "dictionary": "core", "split_mode": "C"}


@pytest.fixture(scope="session")
def grammar_seed() -> list[dict]:
    return json.loads((SEED_DIR / "grammar_points.json").read_text(encoding="utf-8"))["grammar_points"]


@pytest.fixture(scope="session")
def vocabulary_seed() -> list[dict]:
    return json.loads((SEED_DIR / "vocabulary.json").read_text(encoding="utf-8"))["vocabulary"]


@pytest.fixture(scope="session")
def grammar_rules(grammar_seed) -> list[GrammarRule]:
    return [GrammarRule.from_dict({**g, "id": i}) for i, g in enumerate(grammar_seed, start=1)]


@pytest.fixture(scope="session")
def grammar_matcher(grammar_rules) -> GrammarMatcher:
    return GrammarMatcher(grammar_rules)


@pytest.fixture(scope="session")
def vocabulary_entries(vocabulary_seed) -> list[VocabularyEntry]:
    return [VocabularyEntry.from_dict({**v, "id": i}) for i, v in enumerate(vocabulary_seed, start=1)]
