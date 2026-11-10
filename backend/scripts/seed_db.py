"""Idempotently load JLPT master data from ``database/seeds/*.json``.

Usage (from ``backend/``)::

    python -m scripts.seed_db                     # uses JIP_DATABASE_URL
    python -m scripts.seed_db --seed-dir ../database/seeds

Every grammar entry is validated with the same parser the API uses, so a
malformed pattern fails here instead of at server start-up.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.nlp import GrammarRule, PatternError, VocabularyEntry

DEFAULT_SEED_DIR = Path(__file__).resolve().parents[2] / "database" / "seeds"
DEFAULT_DATABASE_URL = "postgresql://jip:jip@localhost:5432/jip"

GRAMMAR_UPSERT = """
    INSERT INTO grammar_points (slug, label, jlpt_level, conjugation_formula, meaning_en,
                                meaning_id, example_ja, example_en, token_patterns, priority)
    VALUES (%(slug)s, %(label)s, %(jlpt_level)s, %(conjugation_formula)s, %(meaning_en)s,
            %(meaning_id)s, %(example_ja)s, %(example_en)s, %(token_patterns)s, %(priority)s)
    ON CONFLICT (slug) DO UPDATE SET
        label = EXCLUDED.label,
        jlpt_level = EXCLUDED.jlpt_level,
        conjugation_formula = EXCLUDED.conjugation_formula,
        meaning_en = EXCLUDED.meaning_en,
        meaning_id = EXCLUDED.meaning_id,
        example_ja = EXCLUDED.example_ja,
        example_en = EXCLUDED.example_en,
        token_patterns = EXCLUDED.token_patterns,
        priority = EXCLUDED.priority
"""

VOCABULARY_UPSERT = """
    INSERT INTO vocabulary (lemma, reading, part_of_speech, jlpt_level, meaning_en)
    VALUES (%(lemma)s, %(reading)s, %(part_of_speech)s, %(jlpt_level)s, %(meaning_en)s)
    ON CONFLICT (lemma, reading) DO UPDATE SET
        part_of_speech = EXCLUDED.part_of_speech,
        jlpt_level = EXCLUDED.jlpt_level,
        meaning_en = EXCLUDED.meaning_en
"""


def load_seed(path: Path, key: str) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)[key]


def validate(grammar: list[dict[str, Any]], vocabulary: list[dict[str, Any]]) -> None:
    for entry in grammar:
        GrammarRule.from_dict(entry)
    for entry in vocabulary:
        VocabularyEntry.from_dict(entry)
    slugs = [g["slug"] for g in grammar]
    duplicates = {s for s in slugs if slugs.count(s) > 1}
    if duplicates:
        raise PatternError(f"duplicate grammar slugs: {sorted(duplicates)}")


def seed(database_url: str, seed_dir: Path) -> tuple[int, int]:
    grammar = load_seed(seed_dir / "grammar_points.json", "grammar_points")
    vocabulary = load_seed(seed_dir / "vocabulary.json", "vocabulary")
    validate(grammar, vocabulary)

    grammar_rows = [
        {
            "meaning_id": None, "example_ja": None, "example_en": None, "priority": 0,
            **g,
            "token_patterns": Jsonb(g["token_patterns"]),
        }
        for g in grammar
    ]
    vocabulary_rows = [{"part_of_speech": None, **v} for v in vocabulary]

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.executemany(GRAMMAR_UPSERT, grammar_rows)
        cur.executemany(VOCABULARY_UPSERT, vocabulary_rows)
    return len(grammar_rows), len(vocabulary_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database-url", default=os.getenv("JIP_DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    args = parser.parse_args(argv)

    try:
        n_grammar, n_vocab = seed(args.database_url, args.seed_dir)
    except (PatternError, OSError, psycopg.Error) as exc:
        print(f"Seeding failed: {exc}", file=sys.stderr)
        return 1
    print(f"Seeded {n_grammar} grammar points and {n_vocab} vocabulary entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
