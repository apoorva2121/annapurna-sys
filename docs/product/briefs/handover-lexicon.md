# Handover · `indian-fnb-lexicon`

**Paste everything below the line into Fable.** It is self-contained: it assumes no access to this
repository. Acceptance checklist for the result is at the bottom of this file, *above* the line —
do not paste that part.

---

## How to judge what comes back

Check these before reading anything else. In order.

1. **Open `PROVENANCE.md` first.** If it claims a high verified fraction, be suspicious rather than
   pleased — verifying hundreds of regional pack-unit conversions against citable sources is slow
   work, and a model that reports 90% verified has almost certainly relabelled its own guesses.
   A report saying *"8% verified, concentrated in the top-volume commodities; the rest generated"*
   is the honest and more useful answer.
2. **Grep the data for `gunny`.** If it returns a single exact number with no range, the spine rule
   was not implemented and the rest of the package cannot be trusted either.
3. **Run the tests, then break one on purpose.** Change a `generated` row to `confidence: high` and
   confirm a test fails. If nothing fails, the spine rule is a comment rather than a guarantee —
   which is the exact failure mode this project keeps finding in its own code.
4. **Look for refusals in the golden file.** A golden file where every line resolves successfully is
   a golden file that has not been thought about. `tin` with no commodity must refuse.
5. **Check it does not import anything of ours.** `grep -r "^import\|^from" | grep -v stdlib` — it
   should depend on almost nothing.

If 1–4 hold, it is worth integrating. If any fail, send it back with the specific failure — it is a
cheap round trip and a much cheaper one than discovering it after M06 depends on the data.

---

# BRIEF: `indian-fnb-lexicon`

## Context

You are building a standalone Python package for a multi-tenant SaaS product used by **independent
Indian restaurants** — Pune and Mumbai first. The product tracks stock as an append-only ledger and
computes its core insight from the gap between *theoretical* consumption (what the recipes say should
have been used) and *actual* consumption (what a physical count says was used). That variance is the
thing the product sells.

Stock enters the ledger when a delivery is received. Today that means a store manager typing every
line of a supplier's bill, which in practice does not happen — so the ledger stays empty and the
variance number is meaningless. The fix is to photograph the bill and extract the lines.

**Your package is the part that turns extracted text into something the ledger can accept.** You are
not doing OCR. You receive text.

## Why this is hard, and why an off-the-shelf answer fails

Invoice parsing is a solved category — for printed Western invoices with item codes. None of that
survives an Indian supplier bill:

- **No item codes. Ever.** Free text in supplier shorthand: `Kanda`, `TMT`, `Aloo`, `Dahi`, `Pnr`.
  It varies by supplier and sometimes by the person who wrote it that day.
- **Mixed script** — Devanagari and Latin in the same line, with inconsistent transliteration
  (`Kanda` / `Kandaa` / `कांदा`).
- **Units that are not units** — `nag` (piece), `pkt`, `gunny` / `bora` (a sack, roughly 50 kg but it
  depends), `tin` (roughly 15 kg for oil, roughly 15 litres for dairy), `peti` (crate), `dozen`,
  `quintal`. A rate is often quoted per kilo and billed per sack.
- **Two documents for one delivery** — the *kachcha* (informal, handwritten) slip and the *pukka*
  (GST) invoice, which do not always agree.
- Sometimes the "invoice" is a WhatsApp message.

## The one rule that decides whether this package is worth having

**It must refuse to be confidently wrong.**

A `gunny` is *approximately* 50 kg and varies by commodity, region and supplier. If you answer
`50000 g` as fact and that number reaches the stock ledger, the stock is wrong — and wrong stock
destroys the variance calculation, which is the only thing this product sells. The error is silent
and is discovered months later, if ever.

So an entry reading **"50 kg ± regional, confirm"** is *more valuable* than one that is confidently
precise. Throughout this package, calibration beats coverage. Coverage is easy to generate and easy
to measure, which is exactly why optimising for it produces a dataset that looks excellent and cannot
be trusted.

**Concretely — the spine rule, which must be enforced by a test:**

> A conversion whose provenance is `generated` may never be returned with `confidence: "high"`, and
> always sets `needs_confirmation: True`.

## Hard constraints

- **Pure Python package. No database, no network at runtime, no file I/O beyond your own bundled
  data.** Pure functions: same input, same output, no hidden state.
- **`Decimal`, never `float`,** for every quantity. This feeds a financial ledger.
- **Base units are `g`, `ml`, `unit`.** Everything converts to one of those three. Nothing else is
  storable downstream.
- Python 3.12+. Type-annotated throughout, passing `mypy --strict`. Tests with `pytest`.
- Minimal dependencies. Justify any dependency beyond the standard library in the README.

## Public API — keep it this small

```python
def resolve(text: str, *, catalogue: Sequence[CatalogueEntry] | None = None) -> Resolution: ...
def parse_quantity(text: str) -> QuantityParse: ...
def parse_line(text: str, *, catalogue: Sequence[CatalogueEntry] | None = None) -> LineParse: ...
def lexicon() -> Lexicon: ...
```

`catalogue` is the tenant's own ingredient list when one exists. Supplied, rank against it; omitted,
rank against your bundled canonical list. This is what lets the package work on day one *and* improve
per tenant — **without ever holding tenant state.**

Nothing returns a bare answer. Everything returns ranked candidates with a score and an auditable
reason.

```python
@dataclass(frozen=True)
class Candidate:
    canonical_key: str                 # "potato"
    display_name: str                  # "Potato"
    base_unit: Literal["g", "ml", "unit"]
    score: float                       # 0..1
    matched_via: str                   # which alias or rule fired; a human must be able to audit it

@dataclass(frozen=True)
class Resolution:
    candidates: tuple[Candidate, ...]  # ranked; may be empty
    ambiguous: bool                    # two or more too close to separate

@dataclass(frozen=True)
class QuantityParse:
    quantity: Decimal | None           # in base units; None when undeterminable
    base_unit: Literal["g", "ml", "unit"] | None
    low: Decimal | None                # range, when the pack unit is inexact
    high: Decimal | None
    confidence: Literal["high", "medium", "low"]
    provenance: Literal["verified", "practitioner", "generated"]
    needs_confirmation: bool
    note: str                          # "tin is ~15 kg for oil and ~15 l for dairy"
```

Worked examples of intended behaviour:

```
"2 bora aloo @ 1100"   → potato · 100000 g (90000–120000) · medium · generated · needs_confirmation
"TMT 5 kg"             → tomato · 5000 g · high · verified
"पनीर 5 नग"             → paneer · 5 unit · high
"dahi 2 tin"           → AMBIGUOUS — tin is ~15 kg (oil) or ~15 l (dairy). Refuse; do not pick one.
```

## The data

**Ingredients** — roughly 500–800 entries: what an Indian restaurant kitchen actually buys. Each with
a canonical key, English display name, base unit, category, and a density where `ml`↔`g` conversion
is meaningful.

**Aliases** — the bulk of the value. Per ingredient: regional names in Hindi, Marathi, Tamil, Bengali
and Gujarati, in **both** native script and common transliterations including the misspellings people
actually write; supplier shorthand and abbreviations; trade names and grades (`Hybrid tomato`,
`Nasik onion`, `Basmati 1121`).

**Pack units** — the hard part. Each conversion carries: `token`; `applies_to` (a commodity or `*` —
a tin of oil and a tin of dairy differ); `nominal`, `low`, `high` (**a range, never a point**);
`region`; `provenance` (`verified` / `practitioner` / `generated`); and `source` (a citation when
`verified`).

## Verification protocol — follow this exactly

1. Generate broadly. Mark **every** row `generated`.
2. Rank by **blast radius**: commodity volume × conversion magnitude. A wrong `gunny` for rice costs
   far more than a wrong `pkt` of bay leaves.
3. Verify the top decile against citable sources. Mark those `verified` and record the citation.
4. Everything else stays `generated`. The package states plainly that it is a starting point.

**Do not hand back a dataset where every row claims to be verified.** Verification status is data,
and falsifying it is worse than shipping a small lexicon. I would rather receive 600 honest rows than
2000 confident ones.

## Tests — assert the properties, not just examples

- **no `generated` row is ever returned with high confidence** (the spine rule)
- every pack-unit conversion carries a provenance, no exceptions
- every conversion where `low != high` sets `needs_confirmation`
- **round-trip**: every alias of every ingredient resolves back to that ingredient
- **ambiguity is reported, never resolved** — `tin` without a commodity returns `ambiguous=True`
- **script coverage**: where an ingredient has a Devanagari alias, its transliteration resolves to the
  same canonical key
- a **golden file** of realistic bill lines — noisy, missing spaces, mixed script, rate-per-kg
  billed-per-sack — with expected outcomes, **including lines that must fail.** A golden file where
  everything resolves has not been thought about
- property-based tests (Hypothesis) for the quantity parser: no input may produce a negative
  quantity, a `float`, or a high-confidence answer without provenance

## Out of scope

OCR; images; any database; anything that writes; per-tenant learning (you accept a catalogue, you do
not remember one); sentence-level NLP — this is line parsing.

## Deliverable

A repository containing: the package, its bundled data, the test suite, a `README.md` with the
worked examples above, and a **`PROVENANCE.md`** stating — per category — what fraction is `verified`
and against which sources.

Done means: it installs into a clean virtualenv, the tests pass with no database and no network, and
the spine rule is enforced by a failing test when violated rather than by a comment.
