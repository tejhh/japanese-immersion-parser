-- =============================================================================
-- Japanese Immersion Reading & JLPT Grammar Parser — PostgreSQL schema
-- Target: PostgreSQL 14+ (tested on 16)
--
-- Tables
--   articles            Raw reading material (Japanese text, no spaces).
--   grammar_points      Master list of JLPT grammar (bunpou) + token-pattern DSL.
--   vocabulary          Master list of JLPT vocabulary keyed by Sudachi lemma.
--   parse_runs          One row per NLP pass over an article (versioned, reproducible).
--   article_highlights  Pre-computed character spans (start/end) for the frontend.
--
-- Character offsets are Unicode code-point indices into articles.body
-- (identical to Python str indexing / PostgreSQL char_length / substr).
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Enumerations
-- -----------------------------------------------------------------------------
CREATE TYPE jlpt_level     AS ENUM ('N5', 'N4', 'N3', 'N2', 'N1');
CREATE TYPE highlight_kind AS ENUM ('grammar', 'vocabulary');
CREATE TYPE parse_status   AS ENUM ('pending', 'processing', 'completed', 'failed');

-- -----------------------------------------------------------------------------
-- Shared trigger: keep updated_at current
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- -----------------------------------------------------------------------------
-- articles
-- -----------------------------------------------------------------------------
CREATE TABLE articles (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title            TEXT         NOT NULL CHECK (length(btrim(title)) > 0),
    body             TEXT         NOT NULL CHECK (length(body) > 0),
    source_url       TEXT,
    body_sha256      CHAR(64)     NOT NULL,
    char_length      INTEGER      GENERATED ALWAYS AS (char_length(body)) STORED,
    estimated_level  jlpt_level,
    parse_status     parse_status NOT NULL DEFAULT 'pending',
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX articles_body_sha256_idx   ON articles (body_sha256);
CREATE INDEX articles_created_at_idx    ON articles (created_at DESC);
CREATE INDEX articles_level_idx         ON articles (estimated_level);

CREATE TRIGGER articles_set_updated_at
    BEFORE UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON COLUMN articles.body_sha256 IS 'Hex SHA-256 of body; lets callers detect duplicate submissions.';
COMMENT ON COLUMN articles.estimated_level IS 'Heuristic difficulty derived from the current parse run.';

-- -----------------------------------------------------------------------------
-- grammar_points (JLPT bunpou master)
-- -----------------------------------------------------------------------------
CREATE TABLE grammar_points (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug                 TEXT        NOT NULL UNIQUE
                                     CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    label                TEXT        NOT NULL,           -- e.g. 〜ている
    jlpt_level           jlpt_level  NOT NULL,
    conjugation_formula  TEXT        NOT NULL,           -- e.g. V-て形 + いる
    meaning_en           TEXT        NOT NULL,
    meaning_id           TEXT,                           -- Indonesian gloss (optional)
    example_ja           TEXT,
    example_en           TEXT,
    token_patterns       JSONB       NOT NULL
                                     CHECK (jsonb_typeof(token_patterns) = 'array'
                                            AND jsonb_array_length(token_patterns) > 0),
    priority             SMALLINT    NOT NULL DEFAULT 0,
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX grammar_points_level_active_idx
    ON grammar_points (jlpt_level) WHERE is_active;

CREATE TRIGGER grammar_points_set_updated_at
    BEFORE UPDATE ON grammar_points
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON COLUMN grammar_points.token_patterns IS
    'Array of alternative patterns; each pattern is an array of token constraints '
    '(surface, lemma, pos, conj, optional, context). See README "Pattern DSL".';

-- -----------------------------------------------------------------------------
-- vocabulary (JLPT word master)
-- -----------------------------------------------------------------------------
CREATE TABLE vocabulary (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lemma           TEXT        NOT NULL,   -- matches Sudachi dictionary/normalized form
    reading         TEXT        NOT NULL,   -- katakana or hiragana
    part_of_speech  TEXT,                   -- Sudachi top-level POS (動詞, 名詞, ...)
    jlpt_level      jlpt_level  NOT NULL,
    meaning_en      TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT vocabulary_lemma_reading_uniq UNIQUE (lemma, reading)
);

CREATE INDEX vocabulary_lemma_idx ON vocabulary (lemma);

-- -----------------------------------------------------------------------------
-- parse_runs (versioned NLP passes)
-- -----------------------------------------------------------------------------
CREATE TABLE parse_runs (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_id        BIGINT       NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    analyzer_version  TEXT         NOT NULL,
    sudachi_dict      TEXT         NOT NULL CHECK (sudachi_dict IN ('small', 'core', 'full')),
    split_mode        CHAR(1)      NOT NULL CHECK (split_mode IN ('A', 'B', 'C')),
    token_count       INTEGER      NOT NULL CHECK (token_count >= 0),
    tokens            JSONB,       -- optional compact token dump [[start,end,lemma,reading,pos],...]
    status            parse_status NOT NULL DEFAULT 'completed',
    error_message     TEXT,
    is_current        BOOLEAN      NOT NULL DEFAULT FALSE,
    elapsed_ms        NUMERIC(10, 2),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    -- target for the composite FK below (guarantees highlight.article_id consistency)
    CONSTRAINT parse_runs_id_article_uniq UNIQUE (id, article_id)
);

-- At most one "current" run per article; older runs are kept for auditing/diffing.
CREATE UNIQUE INDEX parse_runs_one_current_per_article
    ON parse_runs (article_id) WHERE is_current;

-- -----------------------------------------------------------------------------
-- article_highlights (token position mapping)
-- -----------------------------------------------------------------------------
CREATE TABLE article_highlights (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parse_run_id        BIGINT         NOT NULL,
    article_id          BIGINT         NOT NULL,
    kind                highlight_kind NOT NULL,
    grammar_point_id    BIGINT         REFERENCES grammar_points (id) ON DELETE RESTRICT,
    vocabulary_id       BIGINT         REFERENCES vocabulary (id)     ON DELETE RESTRICT,
    jlpt_level          jlpt_level     NOT NULL,   -- snapshot at parse time
    start_index         INTEGER        NOT NULL CHECK (start_index >= 0),
    end_index           INTEGER        NOT NULL,   -- exclusive
    token_start         INTEGER        NOT NULL CHECK (token_start >= 0),
    token_end           INTEGER        NOT NULL,   -- exclusive
    surface             TEXT           NOT NULL,
    contextual_meaning  TEXT,

    CONSTRAINT article_highlights_run_fk
        FOREIGN KEY (parse_run_id, article_id)
        REFERENCES parse_runs (id, article_id) ON DELETE CASCADE,
    CONSTRAINT article_highlights_span_chk  CHECK (end_index > start_index),
    CONSTRAINT article_highlights_token_chk CHECK (token_end > token_start),
    CONSTRAINT article_highlights_surface_chk
        CHECK (char_length(surface) = end_index - start_index),
    CONSTRAINT article_highlights_target_chk CHECK (
        (kind = 'grammar'    AND grammar_point_id IS NOT NULL AND vocabulary_id IS NULL) OR
        (kind = 'vocabulary' AND vocabulary_id    IS NOT NULL AND grammar_point_id IS NULL)
    )
);

CREATE UNIQUE INDEX article_highlights_dedupe_uniq
    ON article_highlights (parse_run_id, kind,
                           COALESCE(grammar_point_id, vocabulary_id),
                           start_index, end_index);
CREATE INDEX article_highlights_article_pos_idx ON article_highlights (article_id, start_index);
CREATE INDEX article_highlights_grammar_idx     ON article_highlights (grammar_point_id)
    WHERE grammar_point_id IS NOT NULL;
CREATE INDEX article_highlights_level_idx       ON article_highlights (article_id, jlpt_level);

-- -----------------------------------------------------------------------------
-- Read model: highlights of the current parse run, enriched for the API
-- -----------------------------------------------------------------------------
CREATE VIEW v_current_highlights AS
SELECT
    h.id,
    h.article_id,
    h.parse_run_id,
    h.kind,
    h.jlpt_level,
    h.start_index,
    h.end_index,
    h.token_start,
    h.token_end,
    h.surface,
    h.contextual_meaning,
    g.id                  AS grammar_id,
    g.slug                AS grammar_slug,
    g.label               AS grammar_label,
    g.conjugation_formula AS grammar_formula,
    g.meaning_en          AS grammar_meaning_en,
    g.meaning_id          AS grammar_meaning_id,
    v.id                  AS vocab_id,
    v.lemma               AS vocab_lemma,
    v.reading             AS vocab_reading,
    v.meaning_en          AS vocab_meaning_en
FROM article_highlights h
JOIN parse_runs r          ON r.id = h.parse_run_id AND r.is_current
LEFT JOIN grammar_points g ON g.id = h.grammar_point_id
LEFT JOIN vocabulary v     ON v.id = h.vocabulary_id;

COMMIT;
