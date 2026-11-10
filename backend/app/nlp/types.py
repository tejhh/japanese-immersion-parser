"""Core value objects shared across the NLP pipeline."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum

UNSET = "*"
"""Sudachi's placeholder for an empty part-of-speech field."""


class JLPTLevel(str, Enum):
    """JLPT proficiency levels, from N5 (beginner) to N1 (advanced)."""

    N5 = "N5"
    N4 = "N4"
    N3 = "N3"
    N2 = "N2"
    N1 = "N1"

    @property
    def difficulty(self) -> int:
        """Return 1 for N5 (easiest) up to 5 for N1 (hardest)."""
        return 6 - int(self.value[1])


@dataclass(frozen=True, slots=True)
class Token:
    """A single morpheme, independent of the tokenizer that produced it.

    ``start``/``end`` are code-point offsets into the *original* text, so
    ``text[token.start:token.end] == token.surface`` always holds.
    """

    index: int
    surface: str
    dictionary_form: str
    normalized_form: str
    reading: str
    pos: tuple[str, ...]
    start: int
    end: int

    @property
    def pos_major(self) -> str:
        """Top-level part of speech, e.g. ``動詞`` or ``助詞``."""
        return self.pos[0] if self.pos else UNSET

    @property
    def conjugation_form(self) -> str:
        """Conjugation form (活用形), e.g. ``連用形-一般``; ``*`` if not inflected."""
        return self.pos[5] if len(self.pos) > 5 else UNSET

    def has_lemma(self, candidates: Collection[str]) -> bool:
        """True if either the dictionary or normalized form is in ``candidates``."""
        return self.dictionary_form in candidates or self.normalized_form in candidates
