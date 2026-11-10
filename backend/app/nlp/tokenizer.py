"""SudachiPy adapter producing :class:`~app.nlp.types.Token` objects.

Two practical concerns are handled here:

* **Input size** — Sudachi rejects inputs larger than ~49 KB (UTF-8), so long
  articles are split at sentence boundaries and token offsets are shifted
  back into the coordinate space of the original text.
* **Thread safety** — Sudachi tokenizer objects must not be shared across
  threads. FastAPI runs sync endpoints in a thread pool, so each worker
  thread lazily builds its own tokenizer (the dictionary file is memory-mapped,
  so the per-thread cost is small).
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from typing import Any

from app.nlp.types import Token

SUDACHI_MAX_INPUT_BYTES = 49_149
DEFAULT_CHUNK_BYTES = 32_768
VALID_DICTIONARIES = frozenset({"small", "core", "full"})
VALID_SPLIT_MODES = frozenset({"A", "B", "C"})

# A "sentence" is a run of non-terminators followed by its terminators, or a
# run of terminators on its own. Together the two alternatives cover every
# character, so concatenating all matches reproduces the input exactly.
_SENTENCE_RE = re.compile(r"[^。！？!?\n]+[。！？!?\n]*|[。！？!?\n]+")


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _hard_split(text: str, start: int, end: int, max_bytes: int) -> Iterator[tuple[int, str]]:
    """Split ``text[start:end]`` into pieces of at most ``max_bytes`` bytes."""
    piece_start, piece_bytes = start, 0
    for i in range(start, end):
        char_bytes = _utf8_len(text[i])
        if piece_bytes + char_bytes > max_bytes:
            yield piece_start, text[piece_start:i]
            piece_start, piece_bytes = i, 0
        piece_bytes += char_bytes
    if piece_start < end:
        yield piece_start, text[piece_start:end]


def iter_chunks(text: str, max_bytes: int = DEFAULT_CHUNK_BYTES) -> Iterator[tuple[int, str]]:
    """Yield ``(offset, chunk)`` pairs that partition ``text`` without gaps.

    Chunks break at sentence boundaries and never exceed ``max_bytes``
    (UTF-8); a single over-long sentence is hard-split as a last resort.
    """
    if max_bytes <= 4:
        raise ValueError("max_bytes must be larger than one UTF-8 character")

    chunk_start, chunk_bytes = 0, 0
    for sentence in _SENTENCE_RE.finditer(text):
        seg_start, seg_end = sentence.span()
        seg_bytes = _utf8_len(sentence.group())

        if chunk_bytes + seg_bytes > max_bytes and seg_start > chunk_start:
            yield chunk_start, text[chunk_start:seg_start]
            chunk_start, chunk_bytes = seg_start, 0

        if seg_bytes > max_bytes:
            yield from _hard_split(text, seg_start, seg_end, max_bytes)
            chunk_start, chunk_bytes = seg_end, 0
            continue

        chunk_bytes += seg_bytes

    if chunk_start < len(text):
        yield chunk_start, text[chunk_start:]


class SudachiTokenizer:
    """Thread-safe SudachiPy wrapper."""

    def __init__(
        self,
        dictionary: str = "core",
        split_mode: str = "C",
        max_chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    ) -> None:
        if dictionary not in VALID_DICTIONARIES:
            raise ValueError(f"dictionary must be one of {sorted(VALID_DICTIONARIES)}")
        split_mode = split_mode.upper()
        if split_mode not in VALID_SPLIT_MODES:
            raise ValueError(f"split_mode must be one of {sorted(VALID_SPLIT_MODES)}")
        if not 4 < max_chunk_bytes <= SUDACHI_MAX_INPUT_BYTES:
            raise ValueError(f"max_chunk_bytes must be in (4, {SUDACHI_MAX_INPUT_BYTES}]")

        try:
            import sudachipy  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "SudachiPy is not installed. Run: pip install sudachipy sudachidict_core"
            ) from exc

        self.dictionary = dictionary
        self.split_mode = split_mode
        self.max_chunk_bytes = max_chunk_bytes
        self._local = threading.local()
        self._thread_tokenizer()  # fail fast at startup if the dictionary is missing

    def describe(self) -> dict[str, str]:
        return {"engine": "sudachipy", "dictionary": self.dictionary, "split_mode": self.split_mode}

    def _thread_tokenizer(self) -> Any:
        tokenizer = getattr(self._local, "tokenizer", None)
        if tokenizer is None:
            from sudachipy import Dictionary, SplitMode

            mode = getattr(SplitMode, self.split_mode)
            tokenizer = Dictionary(dict=self.dictionary).create(mode=mode)
            self._local.tokenizer = tokenizer
        return tokenizer

    def tokenize(self, text: str) -> list[Token]:
        tokenizer = self._thread_tokenizer()
        tokens: list[Token] = []
        for offset, chunk in iter_chunks(text, self.max_chunk_bytes):
            for morpheme in tokenizer.tokenize(chunk):
                tokens.append(
                    Token(
                        index=len(tokens),
                        surface=morpheme.surface(),
                        dictionary_form=morpheme.dictionary_form(),
                        normalized_form=morpheme.normalized_form(),
                        reading=morpheme.reading_form(),
                        pos=tuple(morpheme.part_of_speech()),
                        start=offset + morpheme.begin(),
                        end=offset + morpheme.end(),
                    )
                )
        return tokens
