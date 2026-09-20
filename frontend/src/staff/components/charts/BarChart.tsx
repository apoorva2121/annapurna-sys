import { type KeyboardEvent, type ReactElement } from 'react';

import { fraction, toPlotValue } from './plot';

/**
 * Branches beside each other, as horizontal bars.
 *
 * **One measure, so one colour.** `dataviz`: nominal categories compared on a single measure take
 * the *same* hue — bar length already encodes the value, and colouring each branch differently
 * would spend the identity channel re-encoding what length shows. Colouring by rank would be
 * worse still: it repaints the survivors when a filter changes the set, which is the one thing
 * "colour follows the entity" forbids.
 *
 * **The baseline is zero and there is no second axis.** A bar chart that starts anywhere else is
 * the oldest chart lie there is.
 *
 * **A branch with no answer is drawn as no bar, and labelled.** `spend_per_cover` is `null` when
 * nobody sat down, which is a different statement from zero — a zero-length bar at the bottom of a
 * ranking says "worst", and "we have no dine-in guests to average" is not a ranking position.
 */

const WIDTH = 720;
const ROW_H = 40;
const BAR_H = 24; // `dataviz` caps a bar at 24px; the row's leftover is deliberate air.
const NAME_W = 172;
const VALUE_W = 96;
const BAR_X = NAME_W + 12;
const BAR_MAX = WIDTH - BAR_X - VALUE_W;

export type BarDatum = {
  id: string;
  name: string;
  /** The server's string, or `null` for "no answer". Never parsed for display — see `plot.ts`. */
  value: string | null;
  /** The figure as a person reads it, formatted from the server string by the caller. */
  label: string;
  /** A second line under the name: the context that stops the headline being read alone. */
  hint?: string;
};

export type BarChartProps = {
  data: BarDatum[];
  /** Which validated slot paints the bars. Two charts side by side use different slots so a
   *  reader can tell at a glance which measure they are looking at. */
  series: 'series-1' | 'series-2';
  ariaLabel: string;
  emptyLabel: string;
  /** Shown in place of a bar when the value is `null`. */
  noValueLabel: string;
  onSelect?: (datum: BarDatum) => void;
  selectLabel: (datum: BarDatum) => string;
};

export function BarChart({
  data,
  series,
  ariaLabel,
  emptyLabel,
  noValueLabel,
  onSelect,
  selectLabel,
}: BarChartProps): ReactElement {
  if (data.length === 0) {
    return (
      <p className="text-muted-foreground py-8 text-center text-sm" role="status">
        {emptyLabel}
      </p>
    );
  }

  const plotted = data.map((datum) => toPlotValue(datum.value));
  const top = Math.max(...plotted.map((value) => value ?? 0), 0);
  const height = data.length * ROW_H + 8;
  const fill = series === 'series-1' ? 'fill-series-1' : 'fill-series-2';

  return (
    <svg
      viewBox={`0 0 ${String(WIDTH)} ${String(height)}`}
      className="h-auto w-full"
      role="img"
      aria-label={ariaLabel}
      preserveAspectRatio="xMidYMid meet"
    >
      {data.map((datum, index) => (
        <Row
          key={datum.id}
          datum={datum}
          value={plotted[index] ?? null}
          top={top}
          rowY={index * ROW_H + 4}
          fill={fill}
          noValueLabel={noValueLabel}
          onSelect={onSelect}
          selectLabel={selectLabel}
        />
      ))}

      {/* The baseline. Drawn last so no bar sits on top of it. */}
      <line
        x1={BAR_X}
        x2={BAR_X}
        y1={4}
        y2={height - 4}
        className="stroke-border"
        strokeWidth={1}
      />
    </svg>
  );
}

function Row({
  datum,
  value,
  top,
  rowY,
  fill,
  noValueLabel,
  onSelect,
  selectLabel,
}: {
  datum: BarDatum;
  value: number | null;
  top: number;
  rowY: number;
  fill: string;
  noValueLabel: string;
  // Explicitly `| undefined` rather than optional: `exactOptionalPropertyTypes` distinguishes
  // "absent" from "present and undefined", and this prop is forwarded from a caller that may
  // genuinely hold undefined. An internal component says so rather than making every caller
  // conditionally spread the prop.
  onSelect: ((datum: BarDatum) => void) | undefined;
  selectLabel: (datum: BarDatum) => string;
}): ReactElement {
  const barY = rowY + (ROW_H - BAR_H) / 2;
  // A real value always gets a visible sliver, so "very small" never renders as "absent" — which
  // is the difference between a branch that is struggling and one that is shut.
  const length = value === null ? 0 : Math.max(fraction(value, top) * BAR_MAX, 2);

  return (
    <g {...interaction(datum, selectLabel, onSelect)}>
      {/* The whole row is the hit target, not the bar: a 24px bar is a poor thing to aim at, and
          the shortest bar would otherwise be the hardest to click. */}
      <rect x={0} y={rowY} width={WIDTH} height={ROW_H} fill="transparent" />

      <text
        x={0}
        y={datum.hint === undefined ? barY + BAR_H / 2 : barY + BAR_H / 2 - 6}
        dominantBaseline="middle"
        className="fill-foreground text-[13px]"
      >
        {datum.name}
      </text>
      {datum.hint === undefined ? null : (
        <text
          x={0}
          y={barY + BAR_H / 2 + 9}
          dominantBaseline="middle"
          className="fill-muted-foreground text-[11px]"
        >
          {datum.hint}
        </text>
      )}

      {value === null ? (
        <text
          x={BAR_X}
          y={barY + BAR_H / 2}
          dominantBaseline="middle"
          className="fill-muted-foreground text-[12px] italic"
        >
          {noValueLabel}
        </text>
      ) : (
        <Bar barY={barY} length={length} fill={fill} label={datum.label} />
      )}
    </g>
  );
}

/**
 * What makes a row clickable, gathered in one place.
 *
 * Extracted so `Row` stays under eslint's complexity budget — a row that is a button is five
 * conditional props, and five conditionals is most of the budget spent on plumbing rather than on
 * anything about bars. An SVG `<g>` given a button role has to answer Enter and Space itself, or
 * it is a mouse-only target dressed as a control.
 */
function interaction(
  datum: BarDatum,
  selectLabel: (datum: BarDatum) => string,
  onSelect?: (datum: BarDatum) => void,
): Record<string, unknown> {
  if (onSelect === undefined) {
    return {};
  }
  return {
    onClick: () => {
      onSelect(datum);
    },
    onKeyDown: (event: KeyboardEvent) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        onSelect(datum);
      }
    },
    role: 'button',
    tabIndex: 0,
    'aria-label': selectLabel(datum),
    className: 'focus-visible:ring-ring cursor-pointer outline-none focus-visible:ring-2',
  };
}

/** 4px rounded data-end, square at the baseline. SVG has no per-corner radius, so the shape is a
 *  rounded rect with a square patch over the baseline end — exactly the spec, one extra node. */
function Bar({
  barY,
  length,
  fill,
  label,
}: {
  barY: number;
  length: number;
  fill: string;
  label: string;
}): ReactElement {
  return (
    <>
      <rect x={BAR_X} y={barY} width={length} height={BAR_H} rx={4} className={fill} />
      <rect x={BAR_X} y={barY} width={Math.min(4, length)} height={BAR_H} className={fill} />
      <text
        x={BAR_X + length + 8}
        y={barY + BAR_H / 2}
        dominantBaseline="middle"
        className="fill-foreground text-[12px] tabular-nums"
      >
        {label}
      </text>
    </>
  );
}
