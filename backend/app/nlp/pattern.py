"""A small declarative DSL for matching grammar points against token sequences.

A grammar point owns one or more alternative *patterns*. A pattern is an
ordered list of *elements*, and every element constrains exactly one token.
All keys of an element are optional and combined with logical AND:

=========  ===============================  =========================================
Key        Type                             Meaning
=========  ===============================  =========================================
surface    str | list[str]                  exact surface form
lemma      str | list[str]                  dictionary form OR normalized form
pos        list[str] | list[list[str]]      part-of-speech prefix(es)
conj       str | list[str]                  prefix of the conjugation form (活用形)
optional   bool                             the element may be skipped
context    bool                             must match, but is not highlighted
=========  ===============================  =========================================

Example — 〜ている (the verb is matched as context, only ている is highlighted)::

    [
        {"pos": ["動詞"], "context": true},
        {"surface": ["て", "で"], "pos": ["助詞", "接続助詞"]},
        {"lemma": ["居る", "いる"], "pos": ["動詞"]}
    ]
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.nlp.types import Token

_ALLOWED_KEYS = frozenset({"surface", "lemma", "pos", "conj", "optional", "context"})


class PatternError(ValueError):
    """Raised when a pattern specification is malformed."""


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v for v in value)


def _to_str_set(value: Any, key: str) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str) and value:
        return frozenset({value})
    if _is_str_list(value):
        return frozenset(value)
    raise PatternError(f"'{key}' must be a non-empty string or list of strings, got {value!r}")


def _to_str_tuple(value: Any, key: str) -> tuple[str, ...]:
    return tuple(sorted(_to_str_set(value, key)))


def _to_pos_prefixes(value: Any) -> tuple[tuple[str, ...], ...]:
    if value is None:
        return ()
    if _is_str_list(value):
        return (tuple(value),)
    if isinstance(value, list) and value and all(_is_str_list(v) for v in value):
        return tuple(tuple(v) for v in value)
    raise PatternError(f"'pos' must be a list of strings or a list of such lists, got {value!r}")


@dataclass(frozen=True, slots=True)
class PatternElement:
    """Constraint on a single token."""

    surfaces: frozenset[str] = frozenset()
    lemmas: frozenset[str] = frozenset()
    pos_prefixes: tuple[tuple[str, ...], ...] = ()
    conj_prefixes: tuple[str, ...] = ()
    optional: bool = False
    context: bool = False

    @classmethod
    def from_dict(cls, spec: Mapping[str, Any]) -> PatternElement:
        if not isinstance(spec, Mapping):
            raise PatternError(f"pattern element must be an object, got {spec!r}")
        unknown = set(spec) - _ALLOWED_KEYS
        if unknown:
            raise PatternError(f"unknown pattern keys: {sorted(unknown)}")

        element = cls(
            surfaces=_to_str_set(spec.get("surface"), "surface"),
            lemmas=_to_str_set(spec.get("lemma"), "lemma"),
            pos_prefixes=_to_pos_prefixes(spec.get("pos")),
            conj_prefixes=_to_str_tuple(spec.get("conj"), "conj"),
            optional=bool(spec.get("optional", False)),
            context=bool(spec.get("context", False)),
        )
        if not (element.surfaces or element.lemmas or element.pos_prefixes or element.conj_prefixes):
            raise PatternError("pattern element must declare at least one constraint")
        return element

    def matches(self, token: Token) -> bool:
        if self.surfaces and token.surface not in self.surfaces:
            return False
        if self.lemmas and not token.has_lemma(self.lemmas):
            return False
        if self.pos_prefixes and not any(token.pos[: len(p)] == p for p in self.pos_prefixes):
            return False
        if self.conj_prefixes and not token.conjugation_form.startswith(self.conj_prefixes):
            return False
        return True


@dataclass(frozen=True, slots=True)
class PatternMatch:
    """Token indices consumed by a successful match."""

    highlight_indices: tuple[int, ...]
    context_indices: tuple[int, ...]

    @property
    def token_start(self) -> int:
        return self.highlight_indices[0]

    @property
    def token_end(self) -> int:
        """Exclusive end index of the highlighted tokens."""
        return self.highlight_indices[-1] + 1

    @property
    def last_index(self) -> int:
        """Last token consumed (highlighted or context)."""
        return max((*self.highlight_indices, *self.context_indices))

    @property
    def length(self) -> int:
        return len(self.highlight_indices) + len(self.context_indices)


@dataclass(frozen=True, slots=True)
class TokenPattern:
    """An ordered sequence of :class:`PatternElement` matched against consecutive tokens."""

    elements: tuple[PatternElement, ...]

    @classmethod
    def from_list(cls, spec: Sequence[Mapping[str, Any]]) -> TokenPattern:
        if not isinstance(spec, list) or not spec:
            raise PatternError("a pattern must be a non-empty list of elements")
        elements = tuple(PatternElement.from_dict(item) for item in spec)
        if not any(not e.context and not e.optional for e in elements):
            raise PatternError("a pattern needs at least one required, non-context element")
        return cls(elements)

    def match_at(self, tokens: Sequence[Token], start: int) -> PatternMatch | None:
        """Return the longest match beginning at ``tokens[start]``, or ``None``.

        Uses depth-first backtracking; the search space only branches on
        ``optional`` elements, so it stays tiny for realistic patterns.
        """
        best: list[tuple[PatternElement, int]] = []
        path: list[tuple[PatternElement, int]] = []
        n_elements, n_tokens = len(self.elements), len(tokens)

        def walk(ei: int, ti: int) -> None:
            nonlocal best
            if ei == n_elements:
                if len(path) > len(best):
                    best = list(path)
                return
            element = self.elements[ei]
            if ti < n_tokens and element.matches(tokens[ti]):
                path.append((element, ti))
                walk(ei + 1, ti + 1)
                path.pop()
            if element.optional:
                walk(ei + 1, ti)

        walk(0, start)

        highlight = tuple(ti for el, ti in best if not el.context)
        if not highlight:
            return None
        context = tuple(ti for el, ti in best if el.context)
        return PatternMatch(highlight_indices=highlight, context_indices=context)
