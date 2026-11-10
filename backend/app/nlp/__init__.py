"""NLP pipeline: tokenization, pattern matching and JLPT classification.

Everything in this package except :mod:`app.nlp.tokenizer` is pure Python,
so the matching logic can be unit-tested without SudachiPy or a database.
"""

from app.nlp.analyzer import AnalysisResult, TextAnalyzer, Tokenizer, estimate_level
from app.nlp.grammar import GrammarMatch, GrammarMatcher, GrammarRule
from app.nlp.pattern import PatternError, PatternMatch, TokenPattern
from app.nlp.types import JLPTLevel, Token
from app.nlp.vocabulary import VocabularyEntry, VocabularyMatch, VocabularyMatcher

__all__ = [
    "AnalysisResult",
    "GrammarMatch",
    "GrammarMatcher",
    "GrammarRule",
    "JLPTLevel",
    "PatternError",
    "PatternMatch",
    "TextAnalyzer",
    "Token",
    "TokenPattern",
    "Tokenizer",
    "VocabularyEntry",
    "VocabularyMatch",
    "VocabularyMatcher",
    "estimate_level",
]
