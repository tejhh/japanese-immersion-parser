from __future__ import annotations

from app.nlp import GrammarMatcher, JLPTLevel, TextAnalyzer, VocabularyMatcher, estimate_level
from tests.conftest import FakeTokenizer, build_tokens


def test_estimate_level_ignores_rare_outliers():
    levels = [JLPTLevel.N5] * 19 + [JLPTLevel.N1]
    assert estimate_level(levels, min_share=0.1) is JLPTLevel.N5
    assert estimate_level(levels + [JLPTLevel.N1], min_share=0.09) is JLPTLevel.N1
    assert estimate_level([]) is None


def test_analyzer_combines_grammar_and_vocabulary(grammar_rules, vocabulary_entries):
    text, tokens = build_tokens([
        ("財布", "財布", "財布", "名詞", "普通名詞", "*"),
        ("を", "を", "を", "助詞", "格助詞", "*"),
        ("忘れ", "忘れる", "忘れる", "動詞", "一般", "連用形-一般"),
        ("て", "て", "て", "助詞", "接続助詞", "*"),
        ("しまっ", "しまう", "仕舞う", "動詞", "非自立可能", "連用形-促音便"),
        ("た", "た", "た", "助動詞", "*", "終止形-一般"),
        ("。", "。", "。", "補助記号", "句点", "*"),
    ])
    analyzer = TextAnalyzer(
        FakeTokenizer({text: tokens}),
        GrammarMatcher(grammar_rules),
        VocabularyMatcher(vocabulary_entries),
    )
    result = analyzer.analyze(text)

    assert [m.rule.slug for m in result.grammar] == ["te-shimau"]
    assert {(m.entry.lemma, m.level) for m in result.vocabulary} == {
        ("財布", JLPTLevel.N4),
        ("忘れる", JLPTLevel.N5),
    }
    assert result.level_counts[JLPTLevel.N4] == 2
    assert result.estimated_level is JLPTLevel.N4
    assert result.tokenizer_info["engine"] == "fake"

    no_vocab = analyzer.analyze(text, include_vocabulary=False)
    assert no_vocab.vocabulary == ()


def test_vocabulary_skips_function_words(vocabulary_entries):
    _, tokens = build_tokens([("本", "本", "本", "助詞", "係助詞", "*")])  # contrived POS
    assert VocabularyMatcher(vocabulary_entries).find(tokens) == []
