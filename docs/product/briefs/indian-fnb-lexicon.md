# Build brief · `indian-fnb-lexicon`

**Status: brief, not scope.** Written 2026-09-11 for an external model to build against. Promoting
it into `docs/modules.md` is a separate, deliberate decision.

**Rationale:** `docs/product/candidate-flagship-features.md` §A. This is the moat under
bill-to-ledger, it needs no customer data, and it can be built and verified today.

---

## What it is

A standalone Python package that turns a messy line off an Indian supplier's bill into a canonical
ingredient and a quantity in base units — with a confidence, a provenance, and a refusal to guess.

```
"2 bora aloo @ 1100"        →  potato · 100000 g (range 90000–120000) · medium · needs confirmation
"TMT 5 kg"                  →  tomato · 5000 g · high
"पनीर 5 नग"                  →  paneer · 5 unit · high
"dahi 2 tin"                →  curd · ambiguous: tin is 15 kg (oil) or 15 l (dairy) · REFUSE
```

## The one acceptance criterion that matters

**It must refuse to be confidently wrong.**

A `gunny` is *approximately* 50 kg and varies by commodity, region and supplier. A model asked for
its weight will answer `50000 g` without hesitating. If that number reaches the stock ledger as
fact, the stock is wrong, and wrong stock destroys the theoretical-vs-actual variance — which is the
single thing this product sells (CLAUDE.md invariant 7).

So: an entry that says *"50 kg ± regional, confirm"* is **more valuable** than one that is
confidently precise. Any evaluation of this package that rewards coverage over calibration is
measuring the wrong thing.

---

## Hard boundaries

- **Never imports `app.*`.** The application will depend on this package; this package knows nothing
  about the application.
- **No database access of any kind.** No SQLAlchemy, no connection strings, no I/O beyond reading
  its own bundled data files.
- **No OCR and no images.** Input is text. Extraction from a photograph is a separate concern with a
  separate failure mode; conflating them makes both untestable.
- **Pure functions.** Same input, same output, no hidden state, no network.
- Its own tests, its own version, its own changelog.

## Public surface

Keep it small. Four things:

```python
def resolve(text: str, *, catalogue: Sequence[CatalogueEntry] | None = None) -> Resolution: ...
def parse_quantity(text: str) -> QuantityParse: ...
def parse_line(text: str, *, catalogue: Sequence[CatalogueEntry] | None = None) -> LineParse: ...
def lexicon() -> Lexicon: ...   # the bundled data, for callers that want to inspect it
```

`catalogue` is the tenant's own ingredient list when one exists. Supplied, the resolver ranks against
it; omitted, it ranks against the bundled canonical list. This is what lets the package be useful on
day one *and* get better per tenant — without the package ever holding tenant state.

### Returns

Nothing returns a bare answer. Everything returns **ranked candidates with a score and a reason**.

```python
@dataclass(frozen=True)
class Candidate:
    canonical_key: str          # "potato"
    display_name: str           # "Potato"
    base_unit: Literal["g", "ml", "unit"]
    score: float                # 0..1
    matched_via: str            # which alias or rule fired — a human must be able to audit this

@dataclass(frozen=True)
class Resolution:
    candidates: tuple[Candidate, ...]     # ranked, may be empty
    ambiguous: bool                       # two or more candidates too close to separate

@dataclass(frozen=True)
class QuantityParse:
    quantity: Decimal | None              # in base units; None when it cannot be determined
    base_unit: Literal["g", "ml", "unit"] | None
    low: Decimal | None                   # range, when the pack unit is not exact
    high: Decimal | None
    confidence: Literal["high", "medium", "low"]
    provenance: Literal["verified", "practitioner", "generated"]
    needs_confirmation: bool
    note: str                             # e.g. "tin is 15 kg for oil and 15 l for dairy"
```

`Decimal`, never `float` — CLAUDE.md invariant 3 applies to quantities as much as to money, and this
package feeds a ledger.

---

## The data, and how it must be sourced

### Ingredients

Target roughly 500–800 entries: what an Indian restaurant kitchen actually buys. Each carries a
canonical key, an English display name, a **base unit** (`g` / `ml` / `unit`, per invariant 5), a
category, and a density where `ml`↔`g` conversion is meaningful.

### Aliases

This is the bulk of the value. Per ingredient:

- **Regional names** in Hindi, Marathi, Tamil, Bengali, Gujarati — in **both** Devanagari/native
  script and common transliteration, including the spelling variants people actually write
  (`Kanda` / `Kandaa` / `कांदा`)
- **Supplier shorthand** — `TMT`, `Aloo`, `Dahi`, `Pnr`, the abbreviations that vary by supplier and
  sometimes by delivery boy
- **Trade names and grades** — `Hybrid tomato`, `Nasik onion`, `Basmati 1121`

### Pack units — the hard part

`nag`, `pkt`, `gunny`, `bora`, `tin`, `peti`, `dozen`, `kg`, `gm`, `ltr`, `ml`, `quintal`.

Each conversion entry must carry:

| Field | Why |
|---|---|
| `token` | `gunny` |
| `applies_to` | commodity or `*` — a `tin` of oil and a `tin` of dairy differ |
| `nominal`, `low`, `high` | **a range, not a point.** This is the whole discipline |
| `region` | where this holds |
| `provenance` | `verified` / `practitioner` / `generated` |
| `source` | citation when `verified` |

**`generated` entries may never be returned with `confidence: high`, and always set
`needs_confirmation`.** That rule is the package's spine. A generated conversion is a hypothesis to
put in front of a store manager, not a fact to write to a ledger.

### Verification

Generate broadly, then verify narrowly and honestly:

1. produce the full set, every row marked `generated`
2. rank by **blast radius** — commodity volume × conversion magnitude. A wrong `gunny` for rice
   costs far more than a wrong `pkt` of bay leaves
3. verify the top decile against a citable source; mark those `verified` with the citation
4. everything else stays `generated`, and the package is explicit that it is a starting point

Do **not** hand back a dataset where every row claims to be verified. The verification status is
data, and falsifying it is worse than a small lexicon.

---

## Tests

Beyond examples, assert the properties — these are what make it safe:

- **no `generated` row is ever returned with high confidence** (the spine rule)
- **every pack-unit conversion carries a provenance**, no exceptions
- **every conversion with `low != high` sets `needs_confirmation`**
- **round-trip**: every alias of every ingredient resolves back to that ingredient
- **ambiguity is reported, not resolved** — `tin` without a commodity returns `ambiguous=True` and a
  note, never a number
- **script coverage**: for each ingredient with a Devanagari alias, the transliteration resolves to
  the same canonical key
- a **golden file** of realistic bill lines — handwritten-style noise, missing spaces, mixed script,
  rate-per-kg-billed-per-sack — with expected outcomes, including the ones that *should* fail

Property-based testing (Hypothesis) for the quantity parser: no input should ever produce a negative
quantity, a `float`, or a high-confidence answer without provenance.

## Out of scope

OCR; images; the application's `ingredient` table; anything that writes; per-tenant learning
(the package accepts a catalogue, it does not remember one); Hindi/Marathi *sentence* understanding —
this is line parsing, not NLP.

## Done means

1. `pip install` it into a clean venv and the tests pass with no database, no network, no `app` package present
2. the spine rule is asserted by a test, not merely honoured
3. the golden file contains lines it deliberately refuses, and the refusals are the reason the file
   is trustworthy
4. a `PROVENANCE.md` states, per category, what fraction is `verified` and against which sources
