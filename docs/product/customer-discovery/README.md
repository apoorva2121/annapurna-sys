# Customer discovery — Hyderabad, from 2026-09-28

**Why this folder exists.** On 2026-09-28 the owner asked for a strict critique of the plan to
rebuild Restaurant OS as a plug-and-play feature-pack app. The critique concluded that the rebuild
was the wrong next move, and the decision below was taken. This folder holds the work that
replaced it.

Related: `../comparison.md` (35 competitors, 2026-09-13), `../market-research/`,
`docs/backlog.md`.

---

## State

| Part | What | State | Where |
|---|---|---|---|
| A | Strict critique of the rebuild plan | done | this file, §Decision |
| B | Rebuild plan (fresh repo, 8 packs, stores) | **paused, not cancelled** | `~/.claude/plans/see-u-have-3-woolly-church.md`; artifact `6aCJeZ8tGbKxHHYFLfiz7M` |
| C | Outreach tracker | done | `hyderabad-discovery-tracker.xlsx` |
| D | Target list + scripts + cadence | done | this file, §Playbook |
| E | 20 owner conversations | **not started — this is the next action** | tracker, `Targets` sheet |
| F | Read the pattern, decide what to build | blocked on E | — |

## Resume here

**Next action: fill the `Targets` sheet from Google Maps and send the first 15 Instagram DMs.**
Not "continue the project". No code is to be written until E reaches 20 rows with status `TALKED`.

---

## Decision, 2026-09-28: stop building, go and ask

**Decided:** no further feature work on Restaurant OS until 20 real conversations with Hyderabad
restaurant owners are recorded in the tracker.

**Why.** The product has 80 tables, 930 columns, 62 screens, 55 permissions and modules M00–M19,
and **no restaurant has ever run a real bill through it.** Every remaining question — rebuild or
retrofit, which packs, what price, which segment — is unanswerable without a customer, and
guessing at them produced the current shape.

**The three findings that drove it:**

1. **The demo ends at minute four.** `../comparison.md` already records that printed bills, KOT
   printing, offline billing and a UPI QR are missing or out of scope, and names offline and
   aggregators as *"the two objections likeliest to end a pilot"*. Every ₹999/year Play Store app
   has offline billing. The variance report is never reached in a demo that dies on "bill print
   kaise hoga?".

2. **The flagship feature needs discipline the chosen segment does not have.** Theoretical-vs-actual
   variance requires recipes in grams, weighed deliveries and honest stock counts — daily manual
   effort. `indian-restaurants-keep-no-records` (memory) already names this as the central product
   risk. The product was then built on top of it anyway. A variance figure computed from a guessed
   recipe and an uncounted store room is not a fact, and "the numbers are wrong" is the #3
   complaint across all 35 competitors researched.

3. **Segment is probably wrong.** Single-outlet independents are the lowest willingness to pay,
   highest support cost and least data discipline in the market — worst on all three axes at once.
   Cloud-kitchen operators and 2–5 outlet chains have the margin pressure and the counting habit
   that variance needs.

**Alternatives considered and rejected:**

- *Proceed with the rebuild as planned.* Rejected: months of work to arrive at less product than
  exists today, still with no customer. The second-system trap.
- *Retrofit packs onto the existing app now.* Rejected **for now, not on merit** — it is a
  genuinely good idea and roughly a week's work (entitlement table, two middleware checks, one nav
  filter). But it is a pricing mechanism for a product with no price and no buyer.
- *Pivot to a different market entirely.* Rejected: the owner's only warm access is F&B, and the
  accumulated domain asset (35 competitors, the lexicon, compliance mapped to instruments, 122
  market prices, 223 recipes) is the half that is hard to acquire. Changing market discards it and
  restarts distribution at zero.
- *Build printer + offline + UPI first (4 weeks).* **Recommended, then retracted the same day.**
  Those three are only worth building if the product stays a POS. If the conversations point
  elsewhere, it is four weeks wasted. Conversations first.

**Would reverse this decision if:** a restaurant offers to pay before the 20 conversations are
done. Then stop and build what they asked for.

---

## Deferrals, each with a trigger that can be observed

Written as: *not now, because X. Do it when Y.*

| Deferred | Because | Do it when |
|---|---|---|
| The pack/entitlement retrofit | pricing mechanism for a product with no buyer | a second restaurant wants a different feature shape from the first |
| Thermal printing, offline billing, UPI QR | only correct if the product stays a POS | 4+ of the 20 conversations name billing/printing/offline as the pain |
| The fresh design system + Capacitor + stores | distribution is not the constraint; access is | a restaurant is live and asks for an installable app |
| App Store (iOS) specifically | Indian restaurant staff use cheap Android; store review slows every fix | an actual customer asks for iPhone |
| The full rebuild | see Decision above | the conversations confirm the POS direction *and* a paying customer exists |

---

## What is NOT true yet — read this before trusting anything above

- **No restaurant has used this software.** Staging is live and the owner ran a 332-step manual
  pass; that is not a customer.
- **The 20 conversations have not happened.** Every conclusion here is reasoning from desk
  research, not evidence from a buyer.
- **The competitor research was never validated hands-on.** `../comparison.md` says so itself: no
  demo booked, no product operated, 63 of ~110 tags are vendor marketing.
- **Instagram reply rates (10–20%) are my estimate, not a measured figure.** Treat the first 50
  DMs as the measurement, and correct this file.
- **The tracker's formulas were not machine-verified.** LibreOffice is not installed on this
  machine so `recalc.py` could not run; the formulas were checked by hand against their row
  references instead. Excel will compute them on first open.
- **Aggregator payout reconciliation is an unverified hunch**, not a finding. Nobody has checked
  what Swiggy/Zomato statements contain, whether the data is reachable, or who already does this.

---

## Playbook

### Targets

**Best lead first — HRATS.** Hotels & Restaurants Association of Telangana State, founded 2016 to
bring small and medium eateries under one platform. Office: Hotel Dwaraka Palace, Lakdi Ka Pul,
Rajbhavan Road, Hyderabad 500004. Ask to speak to members for research, not to pitch. One
association relationship beats two hundred cold calls, because you arrive introduced.
Their site (hrats.in) had an expired TLS certificate on 2026-09-28 — get the number from Maps.

**Best-fit segment — cloud kitchens.** `cloudkitchenadda.com/cloud-kitchens/hyderabad` lists 250+
verified Hyderabad cloud kitchens with area, cuisine, address and FSSAI status (updated Sept 2026);
contact details are on each listing page, not the index. Densest areas: Madhapur, Gachibowli,
Kondapur, Kukatpally, Manikonda, Hitech City. Biryani, North Indian and healthy-bowl dominate.
They weigh ingredients because margin is all they have — which is exactly what variance needs.

**Do not target** Paradise, Shah Ghouse, Hyderabad House, Bawarchi. Gatekeepers, enterprise
software already, and unservceable by a solo founder. Sweet spot is **1–5 outlets**, where the
owner is the decision maker.

**Faster than any research I can do:** open Google Maps, search "restaurants in Madhapur", and
copy 50 names with numbers and Instagram links in twenty minutes. That beats a US-indexed web
search every time.

### Channels, ranked

1. **Instagram DM** — strongest remote channel in Indian F&B. The owner usually holds that phone,
   not a staff member. Asynchronous, so no ambush.
2. **LinkedIn** — cloud-kitchen and small-chain operators are actually on it. Best-fit customer
   *and* best answer rate.
3. **Phone, 3–5pm only** — never during a meal service. Ask for the owner in the first sentence.
4. **Email** — dead. Don't.

### Scripts

**Instagram DM**

> Hi! Main Hyderabad mein restaurants ke liye software bana raha hoon. Bechne nahi aaya — abhi
> sirf samajhna hai ki asli problem kya hai.
>
> Aapke [restaurant name] ke baare mein dekha. 10 minute baat kar sakte hain kabhi? Sirf 3 sawaal
> hain. Jo bhi banega, aapko free milega.

Send from a real profile with a photo and a bio. An empty profile gets ignored.

**LinkedIn**

> Hi [name] — I'm building software for Indian restaurants and I'm at the stage of understanding
> the problem properly rather than selling anything. You run [brand] in Hyderabad. Could I ask you
> three questions on a 15-minute call? Happy to share what I learn from other operators in return.

The last line is the hook — operators want to know what their competitors struggle with.

**Phone**

> "Namaste, maalik se baat ho sakti hai? … Sir, main software banata hoon restaurants ke liye.
> Kuch bech nahi raha — 5 minute mein teen sawaal poochne the, seekhne ke liye. Abhi theek hai ya
> baad mein call karoon?"

Asking permission for their time in the first fifteen seconds is what prevents the hangup.

### The three questions — unchanged, every time

1. Pichle mahine paisa kahan gaya jo aapko samajh nahi aaya?
2. Software pe kya kharch karte ho? Kuch band kiya? Kyun?
3. Ek cheez kal theek kar doon — kya?

Record their words, not a summary. The phrase four owners use independently is the product.

### Rules

- Do not demo. Do not pitch. A demo turns them polite and you learn nothing.
- **Do not defend the existing app.** A sentence that threatens 19 modules is the most valuable
  thing you will hear. Write it down and say thank you.
- Phone only 3–5pm.

### Cadence, around a day job

| When | What | Time |
|---|---|---|
| Weeknights | 15 Instagram DMs | 30 min |
| Weeknights | Log every reply, verbatim | 10 min |
| Sat/Sun 3–5pm | Phone calls | 2 hrs |
| Once | HRATS — one email, one call | 20 min |

**Expected yield:** ~10–20% DM reply, about half of those talk. That is 150–200 DMs for 20
conversations. Stopping at 20 DMs and 2 replies proves nothing.

### How to read the result at 20 conversations

| Signal | Meaning |
|---|---|
| 4+ say the same thing | That is the product. Build it, nothing else. |
| All say different things | No product there. Learned in 2 weeks, not a year. A win. |
| Everyone says "sab theek hai" | Wrong question or wrong segment. Change segment. |
| Someone offers to pay first | Stop reading. Build that. |

---

## Sources

- HRATS — https://www.hrats.in/about (TLS certificate expired 2026-09-28; read via search summary)
- Telangana Today, HRATS members meet Tourism Secretary —
  https://telanganatoday.com/telangana-hotels-and-restaurants-association-members-meet-tourism-secretary
- Cloud Kitchen Adda, Hyderabad directory — https://cloudkitchenadda.com/cloud-kitchens/hyderabad
- Existing competitor and market research — `../comparison.md`, `../competitor-research/`,
  `../market-research/`
