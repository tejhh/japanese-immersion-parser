"""Grammar detection against the real seed rules, using hand-built Sudachi-style tokens."""

from __future__ import annotations

from app.nlp import JLPTLevel
from tests.conftest import build_tokens

V, P, AUX = "動詞", "助詞", "助動詞"


def slugs(matches):
    return [m.rule.slug for m in matches]


def test_seed_rules_all_parse(grammar_rules):
    assert len(grammar_rules) >= 15
    assert {r.level for r in grammar_rules} == set(JLPTLevel)
    assert len({r.slug for r in grammar_rules}) == len(grammar_rules)


def test_te_iru_highlights_only_the_grammar_part(grammar_matcher):
    text, tokens = build_tokens([
        ("本", "本", "本", "名詞", "普通名詞", "*"),
        ("を", "を", "を", P, "格助詞", "*"),
        ("読ん", "読む", "読む", V, "一般", "連用形-撥音便"),
        ("で", "で", "で", P, "接続助詞", "*"),
        ("いる", "いる", "居る", V, "非自立可能", "終止形-一般"),
        ("。", "。", "。", "補助記号", "句点", "*"),
    ])
    [match] = grammar_matcher.find(tokens, text)
    assert match.rule.slug == "te-iru"
    assert (match.start, match.end, match.surface) == (4, 7, "でいる")
    assert text[match.start:match.end] == match.surface
    assert match.context_lemmas == ("読む",)
    assert "読む" in match.contextual_meaning


def test_nakereba_naranai_n4(grammar_matcher):
    text, tokens = build_tokens([
        ("行か", "行く", "行く", V, "非自立可能", "未然形-一般"),
        ("なけれ", "ない", "ない", AUX, "*", "仮定形-一般"),
        ("ば", "ば", "ば", P, "接続助詞", "*"),
        ("なら", "なる", "成る", V, "非自立可能", "未然形-一般"),
        ("ない", "ない", "ない", AUX, "*", "終止形-一般"),
    ])
    [match] = grammar_matcher.find(tokens, text)
    assert match.rule.slug == "nakereba-naranai"
    assert match.level is JLPTLevel.N4
    assert match.surface == "なければならない"


def test_nested_grammar_points_are_all_reported(grammar_matcher):
    # 忘れてしまっている → 〜てしまう (N4) and 〜ている (N5) overlap.
    text, tokens = build_tokens([
        ("忘れ", "忘れる", "忘れる", V, "一般", "連用形-一般"),
        ("て", "て", "て", P, "接続助詞", "*"),
        ("しまっ", "しまう", "仕舞う", V, "非自立可能", "連用形-促音便"),
        ("て", "て", "て", P, "接続助詞", "*"),
        ("いる", "いる", "居る", V, "非自立可能", "終止形-一般"),
    ])
    matches = grammar_matcher.find(tokens, text)
    assert sorted(slugs(matches)) == ["te-iru", "te-shimau"]
    by_slug = {m.rule.slug: m for m in matches}
    assert by_slug["te-shimau"].surface == "てしまっ"
    assert by_slug["te-iru"].surface == "ている"
    assert by_slug["te-iru"].context_lemmas == ("しまう",)


def test_single_token_alternative_pattern(grammar_matcher):
    text, tokens = build_tokens([
        ("雨", "雨", "雨", "名詞", "普通名詞", "*"),
        ("にもかかわらず", "にもかかわらず", "にも拘らず", P, "接続助詞", "*"),
    ])
    [match] = grammar_matcher.find(tokens, text)
    assert match.rule.slug == "ni-mo-kakawarazu"
    assert (match.start, match.end) == (1, 8)


def test_level_filter(grammar_matcher):
    text, tokens = build_tokens([
        ("行き", "行く", "行く", V, "非自立可能", "連用形-一般"),
        ("たい", "たい", "たい", AUX, "*", "終止形-一般"),
    ])
    assert slugs(grammar_matcher.find(tokens, text)) == ["tai"]
    assert grammar_matcher.find(tokens, text, levels={JLPTLevel.N1}) == []


def test_same_rule_matches_repeatedly_without_overlap(grammar_matcher):
    text, tokens = build_tokens([
        ("食べ", "食べる", "食べる", V, "一般", "連用形-一般"),
        ("たい", "たい", "たい", AUX, "*", "連用形-一般"),
        ("し", "し", "し", P, "接続助詞", "*"),
        ("寝", "寝る", "寝る", V, "一般", "連用形-一般"),
        ("たい", "たい", "たい", AUX, "*", "終止形-一般"),
    ])
    matches = grammar_matcher.find(tokens, text)
    assert [(m.start, m.end) for m in matches] == [(2, 4), (6, 8)]


def test_no_false_positive_on_plain_noun_phrase(grammar_matcher):
    text, tokens = build_tokens([
        ("学校", "学校", "学校", "名詞", "普通名詞", "*"),
        ("に", "に", "に", P, "格助詞", "*"),
        ("行く", "行く", "行く", V, "非自立可能", "終止形-一般"),
    ])
    assert grammar_matcher.find(tokens, text) == []
