"""HTTP contract test for /api/v1/parse (no database, no SudachiPy).

The TestClient is used without a ``with`` block, so the lifespan (which
opens the DB pool and loads Sudachi) is skipped and a fake analyzer is
injected on ``app.state`` instead.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg_pool")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.nlp import GrammarMatcher, TextAnalyzer, VocabularyMatcher  # noqa: E402
from tests.conftest import FakeTokenizer, build_tokens  # noqa: E402


@pytest.fixture()
def client(grammar_rules, vocabulary_entries) -> TestClient:
    text, tokens = build_tokens([
        ("日本", "日本", "日本", "名詞", "固有名詞", "*"),
        ("へ", "へ", "へ", "助詞", "格助詞", "*"),
        ("行き", "行く", "行く", "動詞", "非自立可能", "連用形-一般"),
        ("たい", "たい", "たい", "助動詞", "*", "終止形-一般"),
    ])
    app = create_app(Settings(max_text_chars=50))
    app.state.analyzer = TextAnalyzer(
        FakeTokenizer({text: tokens}),
        GrammarMatcher(grammar_rules),
        VocabularyMatcher(vocabulary_entries),
    )
    return TestClient(app)


def test_parse_returns_positioned_highlights(client):
    response = client.post("/api/v1/parse", json={"text": "日本へ行きたい", "include_tokens": True})
    assert response.status_code == 200
    body = response.json()

    grammar = [h for h in body["highlights"] if h["kind"] == "grammar"]
    assert grammar[0]["grammar"]["slug"] == "tai"
    assert (grammar[0]["start"], grammar[0]["end"], grammar[0]["jlpt_level"]) == (5, 7, "N5")
    assert body["meta"]["offset_unit"] == "unicode_codepoint"
    assert len(body["tokens"]) == 4


def test_parse_rejects_oversized_text(client):
    response = client.post("/api/v1/parse", json={"text": "あ" * 51})
    assert response.status_code == 413
