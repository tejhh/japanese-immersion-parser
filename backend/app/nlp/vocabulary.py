"""JLPT vocabulary lookup keyed by Sudachi lemmas."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.nlp.types import JLPTLevel, Token

# Function words and punctuation are never vocabulary highlights.
_SKIPPED_POS = frozenset({"補助記号", "空白", "記号", "助詞", "助動詞"})


@dataclass(frozen=True, slots=True)
class VocabularyEntry:
    lemma: str
    reading: str
    level: JLPTLevel
    meaning_en: str
    part_of_speech: str | None = None
    id: int | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VocabularyEntry:
        return cls(
            lemma=data["lemma"],
            reading=data["reading"],
            level=JLPTLevel(data["jlpt_level"]),
            meaning_en=data["meaning_en"],
            part_of_speech=data.get("part_of_speech"),
            id=data.get("id"),
        )


@dataclass(frozen=True, slots=True)
class VocabularyMatch:
    entry: VocabularyEntry
    start: int
    end: int
    surface: str
    token_index: int

    @property
    def level(self) -> JLPTLevel:
        return self.entry.level


class VocabularyMatcher:
    """Maps tokens to JLPT vocabulary entries via their lemma."""

    def __init__(self, entries: Iterable[VocabularyEntry]) -> None:
        index: dict[str, list[VocabularyEntry]] = defaultdict(list)
        for entry in entries:
            index[entry.lemma].append(entry)
        # When a lemma is listed at several levels, prefer the easiest one.
        self._index = {
            lemma: sorted(group, key=lambda e: e.level.difficulty) for lemma, group in index.items()
        }

    def __len__(self) -> int:
        return sum(len(group) for group in self._index.values())

    def lookup(self, token: Token) -> VocabularyEntry | None:
        if token.pos_major in _SKIPPED_POS:
            return None
        for key in (token.normalized_form, token.dictionary_form):
            candidates = self._index.get(key)
            if candidates:
                same_pos = (e for e in candidates if e.part_of_speech == token.pos_major)
                return next(same_pos, candidates[0])
        return None

    def find(
        self, tokens: Sequence[Token], levels: Collection[JLPTLevel] | None = None
    ) -> list[VocabularyMatch]:
        matches: list[VocabularyMatch] = []
        for token in tokens:
            entry = self.lookup(token)
            if entry is None or (levels and entry.level not in levels):
                continue
            matches.append(
                VocabularyMatch(
                    entry=entry,
                    start=token.start,
                    end=token.end,
                    surface=token.surface,
                    token_index=token.index,
                )
            )
        return matches
