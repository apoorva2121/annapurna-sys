# Customer Experience Model

Vision doc §18 collects ratings. Ratings are the *least* useful CX data a restaurant has: they are
sparse, biased toward extremes, and arrive after the customer has already decided never to return.

The premise here is different: **most unhappy diners in India never complain. They just don't come
back.** So the product's job is not to collect complaints. It is to detect dissatisfaction that was
never spoken, and to fix the operational causes before the customer leaves.

## The two things that actually drive dissatisfaction

Not food quality. In a competent kitchen, food quality is stable. What varies nightly is **time**
and **accuracy**, and both are already instrumented by the KOT timestamps in the domain model.

**Time.** Four intervals, all derivable from timestamps we already capture:

| Interval | From → to | Target | Why it matters |
|---|---|---|---|
| Seat-to-order | table occupied → order placed | < 6 min | The most common silent irritation |
| Order-to-first-food | placed → first item served | < 12 min | Empty table with no food is the worst state |
| Order-to-complete | placed → all items served | < 25 min | Items arriving separately splits the table |
| **Bill-to-settle** | bill requested → payment done | **< 4 min** | **The single most complained-about moment in Indian dining** |

Bill-to-settle deserves emphasis. A guest who enjoyed everything and then waited eleven minutes for
the bill leaves annoyed, and that is the memory that survives. It is trivially measurable, entirely
within staff control, and almost nobody measures it.

**Accuracy.** Wrong item, missing item, wrong customisation (Jain, no onion, less spicy), items
arriving out of sequence. Each already links to order line → waiter → station.

## Quoted time beats fast time

Telling a table "about 15 minutes" and delivering in 14 beats saying nothing and delivering in 11.
Since we know per-dish prep times and current kitchen load, we can quote honestly — and the waiter
app should show the quote to give.

When the kitchen is genuinely backed up, the system should say so at the point of ordering rather
than letting the waiter promise something the kitchen can't do.

## Silent dissatisfaction — the signals worth watching

None of these require the customer to say anything:

- **Returned or largely uneaten dishes.** Already a waste event (`returned`); it is also the
  strongest CX signal in the building. One record, two modules.
- **No repeat order.** Table ordered drinks/starters and nothing more — often means the first course
  disappointed, or service vanished.
- **Long gap before the second round.** Usually nobody came to the table.
- **Rating collected but no comment** at 3/5. A 3 with silence is a customer who is done.
- **A regular who stops.** Came 4+ times, then 45 days of nothing. This is the highest-value
  intervention in the whole product and costs one phone call.

## Feedback capture that actually works

- **At the table, before they leave.** QR on the bill folder, three taps, order-linked. Response
  rates are an order of magnitude above next-day SMS.
- **Three questions maximum.** Food, service, would-you-return. Free text optional. Every extra
  question halves completion.
- **Always order-linked.** Feedback not attached to an order can't reach the dish, waiter, station
  or prep time — and is nearly worthless. Anonymous feedback is accepted but flagged as low-value.
- **Never ask twice in one visit.**

## Recognition — cheap, and disproportionately effective

Phone number is the key (already the customer's natural key). On the waiter's screen when a known
number is attached to a table:

> **Ravi Kumar** · 7th visit · usually orders Butter Chicken + Butter Naan · **no onion/garlic** ·
> last visit rated 5 · birthday 14 Mar

Two things follow, both nearly free and both strongly repeat-driving:

- **Preferences persist across visits.** Jain, no onion/garlic, allergy, spice level. Asking a
  regular for the fourth time whether they eat onion is a small insult; remembering is a small
  delight. In this market that matters more than almost any feature we could build.
- **Occasions.** Birthday and anniversary capture, with a reminder the week before.

## Complaint recovery, not complaint logging

A logged complaint that nobody resolves is worse than no system. Every complaint carries:
severity → owner → resolution SLA → what was done (comp, remake, refund, apology) → whether the
customer returned afterwards.

That last field is the only real measure of recovery, and it closes back to the order ledger.

## Connecting CX to operations — the point of all of it

This is vision doc §18's example, made concrete and answerable because the data is connected:

> Ratings fell to 3.4 between 8–10 PM on Fri/Sat.
> In that window: order-to-first-food rose from 11 to 19 minutes; tandoor station ran 2.3× its
> average load; two waiters covered 14 tables; three Biryani remakes.
> **Not a food problem. A tandoor capacity and staffing problem on weekend peak.**

## What we measure

Per shift, per waiter, per station: the four time intervals, accuracy rate, return/remake rate,
feedback response rate and average, silent-dissatisfaction signal count, and repeat-visit rate for
customers served. Repeat-visit rate is the one that correlates with revenue; everything else is a
leading indicator of it.
