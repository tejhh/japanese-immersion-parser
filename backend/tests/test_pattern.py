from __future__ import annotations

import pytest

from app.nlp import PatternError, TokenPattern
from tests.conftest import build_tokens


def test_context_element_is_excluded_from_highlight():
    _, tokens = build_tokens([
        ("食べ", "食べる", "食べる", "動詞", "一般", "連用形-一般"),
        ("て", "て", "て", "助詞", "接続助詞", "*"),
        ("いる", "いる", "居る", "動詞", "非自立可能", "終止形-一般"),
    ])
    pattern = TokenPattern.from_list([
        {"pos": ["動詞"], "context": True},
        {"surface": ["て", "で"], "pos": ["助詞", "接続助詞"]},
        {"lemma": "居る"},
    ])
    match = pattern.match_at(tokens, 0)
    assert match is not None
    assert match.context_indices == (0,)
    assert match.highlight_indices == (1, 2)
    assert (match.token_start, match.token_end, match.last_index) == (1, 3, 2)


def test_lemma_matches_dictionary_or_normalized_form():
    _, tokens = build_tokens([("いる", "いる", "居る", "動詞", "非自立可能", "終止形-一般")])
    assert TokenPattern.from_list([{"lemma": "いる"}]).match_at(tokens, 0)
    assert TokenPattern.from_list([{"lemma": "居る"}]).match_at(tokens, 0)
    assert TokenPattern.from_list([{"lemma": "要る"}]).match_at(tokens, 0) is None


def test_conjugation_prefix_and_pos_alternatives():
    _, tokens = build_tokens([("読ん", "読む", "読む", "動詞", "一般", "連用形-撥音便")])
    assert TokenPattern.from_list([{"conj": "連用形"}]).match_at(tokens, 0)
    assert TokenPattern.from_list([{"conj": "未然形"}]).match_at(tokens, 0) is None
    assert TokenPattern.from_list([{"pos": [["名詞"], ["動詞", "一般"]]}]).match_at(tokens, 0)


def test_optional_element_prefers_longest_match():
    _, tokens = build_tokens([
        ("わけ", "訳", "訳", "名詞", "普通名詞", "*"),
        ("で", "だ", "だ", "助動詞", "*", "連用形-一般"),
        ("は", "は", "は", "助詞", "係助詞", "*"),
        ("ない", "ない", "無い", "形容詞", "非自立可能", "終止形-一般"),
    ])
    pattern = TokenPattern.from_list([
        {"surface": "わけ"}, {"surface": "で"}, {"surface": "は", "optional": True}, {"lemma": "ない"},
    ])
    match = pattern.match_at(tokens, 0)
    assert match is not None and match.highlight_indices == (0, 1, 2, 3)

    without_wa = [t for t in tokens if t.surface != "は"]
    match = pattern.match_at(without_wa, 0)
    assert match is not None and len(match.highlight_indices) == 3


def test_pattern_does_not_run_past_end_of_tokens():
    _, tokens = build_tokens([("食べ", "食べる", "食べる", "動詞", "一般", "連用形-一般")])
    pattern = TokenPattern.from_list([{"pos": ["動詞"], "context": True}, {"lemma": "たい"}])
    assert pattern.match_at(tokens, 0) is None


@pytest.mark.parametrize(
    "spec",
    [
        [],
        [{}],
        [{"surfce": "て"}],
        [{"pos": "動詞"}],
        [{"surface": ["て", 1]}],
        [{"pos": ["動詞"], "context": True}],
        [{"surface": "は", "optional": True}],
    ],
)
def test_invalid_patterns_are_rejected(spec):
    with pytest.raises(PatternError):
        TokenPattern.from_list(spec)
