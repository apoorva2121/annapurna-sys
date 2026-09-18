"""The scheme's rules, as pure functions: no database, no clock, no employee.

Everything here is a statement about *fairness* rather than about arithmetic, and each one is a
line from `docs/workload-fairness.md` or ADR 0011 turned into something a test can hold.

**Volume never stands alone.** A volume weight may not exceed the combined accuracy and rating
weights. Without that rule the system pays people to rush, which is the opposite of the goal — and
a restaurant that pays for speed gets speed at the cost of the two things customers actually notice.

**Only controllable metrics carry weight.** A waiter penalised for the tandoor running slow will
correctly conclude the system is stupid and ignore all of it. Context metrics are shown with a
weight of zero, which is not decoration: it is what makes a low score *explainable* to the person
holding it.

**Every metric is a rate.** A four-hour shift and an eight-hour shift are not comparable, and a raw
total measures the roster rather than the person.

**Approved absence is excluded from the attendance denominator.** Leave, sickness, maternity or
paternity, religious observance, and any day somebody was not rostered. A scored attendance metric
that counted an approved absence as a miss would disadvantage exactly the people employment law
protects, and it would do so while looking neutral.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import PerformanceMetricKind

_POINTS = Decimal("0.01")
_ONE = Decimal("1")
# Weights are given as fractions and must sum to one, within a hundredth — the tolerance exists
# because a human types 0.25 + 0.20 + 0.20 + 0.15 + 0.10 + 0.10 and should not be refused for it.
_SUM_TOLERANCE = Decimal("0.01")

# The metrics a scheme may weight, and which of them a person actually controls. **This mapping is
# the ethical core of the module**: everything marked `CONTEXT` is displayed and scores nothing.
METRICS: dict[str, PerformanceMetricKind] = {
    # Controllable — the things a person can do differently tomorrow.
    "accuracy": PerformanceMetricKind.CONTROLLABLE,
    "rating": PerformanceMetricKind.CONTROLLABLE,
    "volume": PerformanceMetricKind.CONTROLLABLE,
    "speed": PerformanceMetricKind.CONTROLLABLE,
    "attendance": PerformanceMetricKind.CONTROLLABLE,
    "assists": PerformanceMetricKind.CONTROLLABLE,
    # Context — shown beside the score, weighted zero, and the reason a low score is explainable.
    "kitchen_delay": PerformanceMetricKind.CONTEXT,
    "section_footfall": PerformanceMetricKind.CONTEXT,
    "table_size": PerformanceMetricKind.CONTEXT,
    "revenue_per_cover": PerformanceMetricKind.CONTEXT,
}

# `docs/workload-fairness.md`'s suggested starting point, and it satisfies the volume rule with
# room to spare: volume 20 against accuracy 25 + rating 20.
SUGGESTED_WEIGHTS: dict[str, str] = {
    "accuracy": "0.25",
    "rating": "0.20",
    "volume": "0.20",
    "speed": "0.15",
    "attendance": "0.10",
    "assists": "0.10",
}

# Below this many scored people, the team view shows nobody but the viewer. With three waiters,
# naming the top two names the third — which defeats "never publish a bottom ranking" by
# arithmetic rather than by intent. Five rather than four because a four-person team with one
# obvious top and one obvious bottom is the same problem with an extra step.
MIN_TEAM_SIZE = 5

# Reasons a day is not counted against somebody's attendance. Tested as a list rather than trusted
# as a habit, for the reason in the module docstring.
EXCLUDED_FROM_ATTENDANCE = frozenset({"leave", "sick", "maternity", "paternity", "observance"})


class SchemeError(ValueError):
    """A scheme that would be unfair if saved. Raised with the sentence a person needs."""


@dataclass(frozen=True, slots=True)
class Metric:
    """One figure on somebody's score, with everything needed to argue with it."""

    key: str
    value: Decimal
    kind: PerformanceMetricKind
    # How many *things* the rate was computed from. `docs/workload-fairness.md` §5: a wrong
    # attribution then shows up as a wrong number of things, which a person can point at, rather
    # than as an unexplained score, which they cannot.
    count: int

    @property
    def weighted(self) -> bool:
        return self.kind is PerformanceMetricKind.CONTROLLABLE


def validate_weights(weights: dict[str, object]) -> dict[str, Decimal]:
    """Refuse a scheme that would pay people to do the wrong thing.

    Four refusals, each with the sentence somebody needs rather than a code:

    - a metric this product does not compute;
    - a **context** metric given weight, which would score somebody for the tandoor;
    - weights that do not sum to one, because then "25%" means nothing;
    - **volume above accuracy plus rating**, which is the rule ADR 0011 names and the one that
      keeps the whole feature honest.
    """
    parsed: dict[str, Decimal] = {}
    for key, raw in weights.items():
        kind = METRICS.get(key)
        if kind is None:
            raise SchemeError(
                f"'{key}' is not a metric this product computes. The ones it does are: "
                f"{', '.join(sorted(METRICS))}."
            )
        weight = _decimal(key, raw)
        if weight < 0:
            raise SchemeError(f"'{key}' cannot have a negative weight.")
        if kind is PerformanceMetricKind.CONTEXT and weight > 0:
            raise SchemeError(
                f"'{key}' is context, not something a person controls, so it cannot carry weight. "
                "It is shown beside the score and counts for nothing — which is what makes a low "
                "score explainable rather than an accusation."
            )
        parsed[key] = weight

    total = sum(parsed.values(), Decimal(0))
    if abs(total - _ONE) > _SUM_TOLERANCE:
        raise SchemeError(f"The weights add up to {total}, and they have to add up to 1.")

    volume = parsed.get("volume", Decimal(0))
    quality = parsed.get("accuracy", Decimal(0)) + parsed.get("rating", Decimal(0))
    if volume > quality:
        raise SchemeError(
            f"Volume is weighted {volume} against accuracy and rating together at {quality}. "
            "Volume never stands alone: weighted above the two quality measures, this pays people "
            "to rush, which is the opposite of what it is for."
        )
    return parsed


def _decimal(key: str, raw: object) -> Decimal:
    try:
        return Decimal(str(raw))
    except (ArithmeticError, TypeError, ValueError) as error:
        raise SchemeError(f"'{key}' has a weight that is not a number.") from error


def points_for(metrics: dict[str, Metric], weights: dict[str, Decimal]) -> Decimal:
    """Points out of a hundred, from the controllable metrics only.

    A metric the scheme does not weight contributes nothing; a metric the scheme weights and the
    period did not produce contributes nothing either, rather than a zero that would read as a
    failure. Somebody who worked one shift is not bad at five things they never did.
    """
    total = Decimal(0)
    for key, weight in weights.items():
        metric = metrics.get(key)
        if metric is None or not metric.weighted:
            continue
        total += metric.value * weight
    return (total * 100).quantize(_POINTS, ROUND_HALF_UP)


def visible_team(scored: int) -> bool:
    """Whether a team is large enough for anybody to be shown anybody else's row."""
    return scored >= MIN_TEAM_SIZE
