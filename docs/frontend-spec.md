# Frontend Specification — Next.js Reader

## Goals

Show a Japanese article with JLPT grammar and vocabulary highlighted in place.
The learner can filter by level, and clicking a highlight shows its formula and meaning.

## Stack

Next.js (App Router) · TypeScript · Tailwind CSS · TanStack Query for data fetching.

## Routes

| Route              | Purpose                                                        |
|--------------------|----------------------------------------------------------------|
| `/`                | Article list (`GET /api/v1/articles`) + "paste text" box       |
| `/articles/[id]`   | Reader view (`GET /articles/{id}` + `/articles/{id}/highlights`) |
| `/playground`      | Ad-hoc analysis via `POST /api/v1/parse` (nothing is stored)    |

## Core components

- `<ReaderText text highlights activeLevels />` renders the text as a list of segments (algorithm below).
- `<LevelFilter />` toggles N5–N1 and grammar/vocabulary. The choice is kept in the URL query (`?level=N3&level=N2`).
- `<GrammarPopover highlight />` shows the label, `conjugation_formula`, `meaning_en` / `meaning_id`, and `contextual_meaning`.
- `<LevelSummary counts />` shows a bar of `level_counts` and the `estimated_level`.

## ⚠️ Offset units

The API returns **Unicode code-point** offsets (`meta.offset_unit = "unicode_codepoint"`).
JavaScript strings are indexed in UTF-16 code units, and the two disagree for characters outside the BMP (for example 𠮷 or emoji).
Always slice with code points:

```ts
const chars = Array.from(text);                       // one entry per code point
const slice = (s: number, e: number) => chars.slice(s, e).join("");
```

## Rendering overlapping highlights (boundary sweep)

Highlights can nest or overlap. For example, 〜てしまう and 〜ている both match inside 忘れてしまっている.
Instead of nesting `<span>`s, split the text at every boundary:

1. Collect every `start` and `end` and add `0` and `chars.length`. Sort and de-duplicate them.
2. For each adjacent pair `[a, b)`, find the active highlights `h` where `h.start <= a && h.end >= b`.
3. Render one `<span>` per segment. Style it by the hardest active level, and add underline layers when more than one grammar highlight is active.
4. On click, open a popover that lists every highlight active in that segment.

Cost: O(n log n) in the number of highlights. The text is never re-tokenised on the client.

## Level colour tokens

| Level | Token            | Suggested colour |
|-------|------------------|------------------|
| N5    | `--jlpt-n5`      | green            |
| N4    | `--jlpt-n4`      | teal             |
| N3    | `--jlpt-n3`      | blue             |
| N2    | `--jlpt-n2`      | purple           |
| N1    | `--jlpt-n1`      | red              |

Grammar highlights get a background tint. Vocabulary highlights get a dotted underline, so the two stay distinguishable when they overlap.

## TypeScript contract (mirror of `app/schemas.py`)

```ts
type JLPTLevel = "N5" | "N4" | "N3" | "N2" | "N1";

interface Highlight {
  id?: number;
  kind: "grammar" | "vocabulary";
  jlpt_level: JLPTLevel;
  start: number;            // inclusive, code points
  end: number;              // exclusive, code points
  token_start: number;
  token_end: number;
  surface: string;
  contextual_meaning?: string;
  grammar?: { id: number | null; slug: string; label: string;
              conjugation_formula: string; meaning_en: string; meaning_id?: string };
  vocabulary?: { id: number | null; lemma: string; reading: string; meaning_en: string };
}
```
