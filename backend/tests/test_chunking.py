from __future__ import annotations

import pytest

from app.nlp.tokenizer import iter_chunks


def _assert_partition(text: str, chunks: list[tuple[int, str]], max_bytes: int) -> None:
    assert "".join(c for _, c in chunks) == text
    for offset, chunk in chunks:
        assert text[offset:offset + len(chunk)] == chunk
        assert len(chunk.encode("utf-8")) <= max_bytes


def test_short_text_is_single_chunk():
    text = "今日は晴れ。明日は雨だろう。"
    assert list(iter_chunks(text, 1024)) == [(0, text)]


def test_breaks_on_sentence_boundaries():
    sentence = "日本語を勉強しています。"  # 12 chars = 36 bytes
    text = sentence * 10
    chunks = list(iter_chunks(text, 100))
    _assert_partition(text, chunks, 100)
    assert all(chunk.endswith("。") for _, chunk in chunks)
    assert len(chunks) == 5  # 2 sentences (72 B) fit per chunk → 10 sentences = 5 chunks


def test_overlong_sentence_is_hard_split():
    text = "あ" * 50 + "。" + "短い。"
    chunks = list(iter_chunks(text, 30))
    _assert_partition(text, chunks, 30)


def test_handles_newlines_and_leading_terminators():
    text = "\n\n「こんにちは！」\n元気？はい。\n"
    chunks = list(iter_chunks(text, 16))
    _assert_partition(text, chunks, 16)


def test_empty_text_yields_nothing():
    assert list(iter_chunks("", 100)) == []


def test_rejects_tiny_limit():
    with pytest.raises(ValueError):
        list(iter_chunks("テスト", 3))
