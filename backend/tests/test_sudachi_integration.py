"""End-to-end checks against the real SudachiPy dictionary.

Skipped automatically when SudachiPy is not installed. These tests guard the
seed patterns against tokenization differences between dictionary releases.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sudachipy")

from app.nlp.tokenizer import SudachiTokenizer  # noqa: E402


@pytest.fixture(scope="module")
def tokenizer() -> SudachiTokenizer:
    return SudachiTokenizer("core", "C")


def test_offsets_index_into_original_text(tokenizer):
    text = "東京で日本語を勉強している。\n明日も行きたい！"
    tokens = tokenizer.tokenize(text)
    assert tokens, "expected tokens"
    for token in tokens:
        assert text[token.start:token.end] == token.surface
    assert "".join(t.surface for t in tokens) == text.replace(" ", "")


def test_long_text_is_chunked_transparently(tokenizer):
    text = "日本語を勉強しています。" * 5000  # ~180 KB, beyond Sudachi's input limit
    tokens = tokenizer.tokenize(text)
    assert tokens[-1].end == len(text)


@pytest.mark.parametrize(
    ("sentence", "expected_slug"),
    [
        ("今、本を読んでいる。", "te-iru"),
        ("日本へ行きたい。", "tai"),
        ("ここで写真を撮らないでください。", "naide-kudasai"),
        ("宿題を出さなければならない。", "nakereba-naranai"),
        ("富士山に登ったことがある。", "ta-koto-ga-aru"),
        ("財布を忘れてしまった。", "te-shimau"),
        ("毎日運動することにした。", "koto-ni-suru"),
        ("中止せざるを得ない。", "zaru-wo-enai"),
    ],
)
def test_seed_grammar_detected(tokenizer, grammar_matcher, sentence, expected_slug):
    tokens = tokenizer.tokenize(sentence)
    found = {m.rule.slug for m in grammar_matcher.find(tokens, sentence)}
    debug = [(t.surface, t.dictionary_form, t.pos) for t in tokens]
    assert expected_slug in found, f"tokens: {debug}"
