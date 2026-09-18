import type { ReactElement } from 'react';

import { strings } from '@staff/strings';
import type { Comparison } from '@staff/api/reports';

/**
 * One headline number with what it is being compared against.
 *
 * **A stat tile, not a one-bar chart.** The `dataviz` skill's own rule: a handful of headline
 * numbers is a KPI row, and a chart of one value is a chart of nothing.
 *
 * **The delta is never rendered in an alert colour**, and that is a deliberate reading of
 * `docs/ui/conventions.md`. The six alert colours are locked and `critical` means *somebody must
 * act now*. Revenue being down against yesterday is information, not an alarm — painting it red
 * would spend the product's strongest signal on a Tuesday being quieter than a Monday, and teach
 * people to ignore red. So the direction is an arrow and a word in muted ink.
 *
 * **`change_percent` may be null, and null is not zero.** It means there was nothing to compare
 * against; the tile says so in words rather than printing "0%", which would read as "unchanged".
 */
export function StatTile({
  label,
  value,
  comparison,
  against = strings.reports.versusPrevious,
  hint,
}: {
  label: string;
  value: string;
  comparison?: Comparison;
  /** What the baseline *is*, in words — "vs yesterday" on the glance, "vs the period before" on a
   *  report. Named rather than assumed: the two are different periods and a tile that said the
   *  wrong one would be confidently wrong. */
  against?: string;
  hint?: string;
}): ReactElement {
  return (
    <section className="flex min-w-40 flex-1 flex-col gap-1 rounded-md border border-border p-4">
      <h3 className="text-sm text-muted-foreground">{label}</h3>
      {/* Tabular so a column of tiles lines up and a changing figure does not shift its neighbours. */}
      <p className="text-3xl font-semibold tabular-nums">{value}</p>
      {comparison === undefined ? null : <Delta comparison={comparison} against={against} />}
      {hint === undefined ? null : <p className="text-xs text-muted-foreground">{hint}</p>}
    </section>
  );
}

function Delta({
  comparison,
  against,
}: {
  comparison: Comparison;
  against: string;
}): ReactElement {
  if (comparison.change_percent === null) {
    return <p className="text-sm text-muted-foreground">{strings.reports.noBaseline}</p>;
  }
  const rose = !comparison.change.startsWith('-');
  return (
    <p className="text-sm text-muted-foreground tabular-nums">
      {/* An arrow and a word: direction is never carried by colour alone, and here it is not
          carried by colour at all. */}
      {rose ? '▲' : '▼'} {comparison.change_percent}% {against}
    </p>
  );
}
