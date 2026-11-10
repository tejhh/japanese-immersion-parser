"""Pydantic request/response models — the public JSON contract of the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app import __version__
from app.nlp import AnalysisResult, GrammarMatch, JLPTLevel, Token, VocabularyMatch

HighlightKind = Literal["grammar", "vocabulary"]


# ---- shared building blocks -------------------------------------------------


class GrammarRef(BaseModel):
    id: int | None
    slug: str
    label: str = Field(examples=["〜ている"])
    conjugation_formula: str = Field(examples=["V-て形 + いる"])
    meaning_en: str
    meaning_id: str | None = None


class VocabularyRef(BaseModel):
    id: int | None
    lemma: str
    reading: str
    meaning_en: str


class Highlight(BaseModel):
    """A positioned span in the source text. ``end`` is exclusive."""

    id: int | None = None
    kind: HighlightKind
    jlpt_level: JLPTLevel
    start: int = Field(ge=0, description="Inclusive Unicode code-point offset")
    end: int = Field(gt=0, description="Exclusive Unicode code-point offset")
    token_start: int
    token_end: int
    surface: str
    contextual_meaning: str | None = None
    grammar: GrammarRef | None = None
    vocabulary: VocabularyRef | None = None

    @classmethod
    def from_grammar(cls, m: GrammarMatch) -> Highlight:
        r = m.rule
        return cls(
            kind="grammar",
            jlpt_level=r.level,
            start=m.start,
            end=m.end,
            token_start=m.token_start,
            token_end=m.token_end,
            surface=m.surface,
            contextual_meaning=m.contextual_meaning,
            grammar=GrammarRef(
                id=r.id,
                slug=r.slug,
                label=r.label,
                conjugation_formula=r.conjugation_formula,
                meaning_en=r.meaning_en,
                meaning_id=r.meaning_id,
            ),
        )

    @classmethod
    def from_vocabulary(cls, m: VocabularyMatch) -> Highlight:
        e = m.entry
        return cls(
            kind="vocabulary",
            jlpt_level=e.level,
            start=m.start,
            end=m.end,
            token_start=m.token_index,
            token_end=m.token_index + 1,
            surface=m.surface,
            contextual_meaning=e.meaning_en,
            vocabulary=VocabularyRef(id=e.id, lemma=e.lemma, reading=e.reading, meaning_en=e.meaning_en),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Highlight:
        """Build from a ``v_current_highlights`` row."""
        grammar = vocabulary = None
        if row["kind"] == "grammar":
            grammar = GrammarRef(
                id=row["grammar_id"],
                slug=row["grammar_slug"],
                label=row["grammar_label"],
                conjugation_formula=row["grammar_formula"],
                meaning_en=row["grammar_meaning_en"],
                meaning_id=row["grammar_meaning_id"],
            )
        else:
            vocabulary = VocabularyRef(
                id=row["vocab_id"],
                lemma=row["vocab_lemma"],
                reading=row["vocab_reading"],
                meaning_en=row["vocab_meaning_en"],
            )
        return cls(
            id=row["id"],
            kind=row["kind"],
            jlpt_level=row["jlpt_level"],
            start=row["start_index"],
            end=row["end_index"],
            token_start=row["token_start"],
            token_end=row["token_end"],
            surface=row["surface"],
            contextual_meaning=row["contextual_meaning"],
            grammar=grammar,
            vocabulary=vocabulary,
        )


def highlights_from_result(result: AnalysisResult) -> list[Highlight]:
    items = [Highlight.from_grammar(m) for m in result.grammar]
    items += [Highlight.from_vocabulary(m) for m in result.vocabulary]
    items.sort(key=lambda h: (h.start, -(h.end - h.start), h.kind))
    return items


class TokenOut(BaseModel):
    surface: str
    dictionary_form: str
    reading: str
    pos: list[str]
    start: int
    end: int

    @classmethod
    def from_token(cls, t: Token) -> TokenOut:
        return cls(
            surface=t.surface,
            dictionary_form=t.dictionary_form,
            reading=t.reading,
            pos=list(t.pos),
            start=t.start,
            end=t.end,
        )


class AnalysisMeta(BaseModel):
    analyzer_version: str = __version__
    tokenizer: dict[str, str]
    elapsed_ms: float
    offset_unit: Literal["unicode_codepoint"] = "unicode_codepoint"


# ---- /parse -------------------------------------------------------------------


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, examples=["日本語を勉強しているが、漢字を忘れてしまった。"])
    levels: list[JLPTLevel] | None = Field(default=None, description="Restrict to these levels")
    include_vocabulary: bool = True
    include_tokens: bool = False


class ParseResponse(BaseModel):
    text_length: int
    token_count: int
    estimated_level: JLPTLevel | None
    level_counts: dict[JLPTLevel, int]
    highlights: list[Highlight]
    tokens: list[TokenOut] | None = None
    meta: AnalysisMeta

    @classmethod
    def from_result(cls, result: AnalysisResult, *, include_tokens: bool) -> ParseResponse:
        return cls(
            text_length=len(result.text),
            token_count=len(result.tokens),
            estimated_level=result.estimated_level,
            level_counts=result.level_counts,
            highlights=highlights_from_result(result),
            tokens=[TokenOut.from_token(t) for t in result.tokens] if include_tokens else None,
            meta=AnalysisMeta(tokenizer=result.tokenizer_info, elapsed_ms=result.elapsed_ms),
        )


# ---- /articles ----------------------------------------------------------------


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    source_url: HttpUrl | None = None


class ArticleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_url: str | None
    char_length: int
    estimated_level: JLPTLevel | None
    parse_status: str
    created_at: datetime


class ArticleDetail(ArticleSummary):
    body: str


class ArticleParsed(BaseModel):
    article: ArticleSummary
    highlight_count: int
    meta: AnalysisMeta


class ArticleHighlights(BaseModel):
    article_id: int
    highlights: list[Highlight]


# ---- /grammar -----------------------------------------------------------------


class GrammarPointOut(BaseModel):
    id: int
    slug: str
    label: str
    jlpt_level: JLPTLevel
    conjugation_formula: str
    meaning_en: str
    meaning_id: str | None
    example_ja: str | None
    example_en: str | None


class ReloadResult(BaseModel):
    grammar_rules: int
    vocabulary_entries: int
