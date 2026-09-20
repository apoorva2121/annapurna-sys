import { useId, useState, type ReactElement } from 'react';

import { fraction, niceTicks, runs, toPlotValue } from './plot';
import type { SeriesPoint } from '@staff/api/analytics';

/**
 * One metric over time, drawn by hand.
 *
 * **There is no charting library in this product, and this file is why one is not needed.**
 * `reportDiscipline` rule 3 keeps `recharts`, `chart.js`, `d3` and the rest out of `package.json`
 * altogether: half a megabyte in a PWA a waiter loads on a three-year-old Android buys four
 * numbers somebody reads in two seconds. A line and some ticks are a couple of hundred lines of
 * SVG, and hand-drawing them is also the only way to hit `dataviz`'s mark specs exactly — a 2px
 * stroke, an 8px end marker ringed in the surface colour, a hairline solid grid — rather than
 * fighting a library's defaults to approximate them.
 *
 * **One y-axis, always, and it starts at zero.** `dataviz`'s first non-negotiable. A second scale
 * is how two unrelated measures are made to look correlated, and a lifted baseline exaggerates
 * every wiggle on the chart.
 *
 * **One series, so no legend** — the heading names what is plotted, and a legend box with a single
 * swatch restates it.
 *
 * **A null bucket is a hole, not a zero.** The API sends `null` for a bucket with no trading, and
 * the line breaks there. Drawing zero would invent a catastrophic day the restaurant was simply
 * shut, which is the failure this chart exists to make visible rather than to manufacture.
 *
 * The pieces below are split out not for reuse — nothing else renders them — but because eslint's
 * complexity budget is a fair proxy for "one function doing several jobs", and a chart genuinely
 * is several: a grid, a line, a marker, a hit layer, a tooltip.
 */

/** The plot box in user units. The SVG scales to its container; these are the coordinates the path
 *  is written in, not pixels on anybody's screen. */
const WIDTH = 720;
const HEIGHT = 260;
const PAD = { top: 16, right: 20, bottom: 34, left: 68 };
const PLOT_W = WIDTH - PAD.left - PAD.right;
const PLOT_H = HEIGHT - PAD.top - PAD.bottom;
/** Wide enough for "₹1,23,456.50" at 13px plus padding, which is the longest figure this product
 *  can produce — `numeric(12,2)` capped by what one restaurant takes in a week. */
const TOOLTIP_W = 150;

export type TrendChartProps = {
  points: SeriesPoint[];
  /** Formats a figure for a person. Takes the **server string**, never a plot number — see
   *  `plot.ts`. Money goes through `formatINR`; a count renders as itself. */
  format: (value: string | null) => string;
  /** Formats an **axis tick**, which is a number this chart generated rather than a figure the
   *  server sent — so it is a scale label, not an amount anybody reconciles. Money drops its paise
   *  here (`dataviz`: ticks round to clean numbers); the exact value stays in the tooltip and the
   *  table. Defaults to `format`. */
  formatTick?: (value: string) => string;
  /** How many business dates a whole bucket holds — 1 for a day, 7 for a week. A bucket with
   *  fewer traded days is marked, because a week the shop was shut for five days is not a quiet
   *  week and must not read as one. */
  bucketDays: number;
  ariaLabel: string;
  emptyLabel: string;
  formatSpan: (point: SeriesPoint) => string;
  formatTraded: (traded: number, of: number) => string;
  /** Drill-through. M19 criterion 6: every figure opens the rows it came from. */
  onSelect?: (point: SeriesPoint) => void;
  selectLabel: (point: SeriesPoint) => string;
};

/** One bucket, with its value already resolved to something drawable. */
type Plotted = { point: SeriesPoint; index: number; value: number | null };

type Scale = { x: (index: number) => number; y: (value: number) => number; band: number };

function scaleFor(count: number, top: number): Scale {
  return {
    // A single point has no span to divide, and dividing by zero would place it at NaN. It sits
    // in the middle, which is the only honest place for it.
    x: (index) => (count === 1 ? PAD.left + PLOT_W / 2 : PAD.left + (index / (count - 1)) * PLOT_W),
    y: (value) => PAD.top + PLOT_H - fraction(value, top) * PLOT_H,
    band: PLOT_W / Math.max(count, 1),
  };
}

export function TrendChart(props: TrendChartProps): ReactElement {
  const { points, format, ariaLabel, emptyLabel, onSelect, selectLabel } = props;
  const clipId = useId();
  const [active, setActive] = useState<number | null>(null);

  const plotted: Plotted[] = points.map((point, index) => ({
    point,
    index,
    value: toPlotValue(point.value),
  }));
  const drawable = plotted.filter((entry) => entry.value !== null);

  if (drawable.length === 0) {
    return (
      <p className="text-muted-foreground py-8 text-center text-sm" role="status">
        {emptyLabel}
      </p>
    );
  }

  const ticks = niceTicks(Math.max(...drawable.map((entry) => entry.value ?? 0)));
  const top = ticks.at(-1) ?? 1;
  const scale = scaleFor(points.length, top);

  // The tooltip appears only for a bucket that has something in it: hovering a week the shop was
  // shut should say nothing rather than say zero.
  const hovered = active === null ? undefined : plotted[active];
  const shown = hovered === undefined || hovered.value === null ? undefined : hovered;

  return (
    <div className="relative w-full">
      <svg
        viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
        className="h-auto w-full overflow-visible"
        role="img"
        aria-label={ariaLabel}
        preserveAspectRatio="xMidYMid meet"
        onPointerLeave={() => {
          setActive(null);
        }}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={PAD.left} y={PAD.top} width={PLOT_W} height={PLOT_H} />
          </clipPath>
        </defs>

        <Grid ticks={ticks} scale={scale} format={props.formatTick ?? format} />
        <XLabels plotted={plotted} scale={scale} formatSpan={props.formatSpan} />

        <g clipPath={`url(#${clipId})`}>
          <ShortBuckets plotted={plotted} scale={scale} bucketDays={props.bucketDays} />
          <Line plotted={plotted} scale={scale} />
        </g>

        <EndMarker plotted={drawable} scale={scale} />
        {shown === undefined ? null : <Crosshair entry={shown} scale={scale} />}

        <HitTargets plotted={plotted} scale={scale} onHover={setActive} onSelect={onSelect} />

        {shown === undefined ? null : (
          <Tooltip
            entry={shown}
            scale={scale}
            format={format}
            bucketDays={props.bucketDays}
            formatSpan={props.formatSpan}
            formatTraded={props.formatTraded}
          />
        )}
      </svg>

      {/* Keyboard and screen-reader reach for the same drill-through the pointer has. Visually
          hidden rather than absent: a chart nobody can tab into is a chart some people cannot
          use at all. */}
      {onSelect === undefined ? null : (
        <ul className="sr-only">
          {points.map((point) => (
            <li key={`key-${point.starts_on}`}>
              <button
                type="button"
                onClick={() => {
                  onSelect(point);
                }}
              >
                {selectLabel(point)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Gridlines and the y-axis. Recessive by token, never a raw grey, and they follow the theme —
 *  which is exactly why grid and axis are *not* locked chart tokens. */
function Grid({
  ticks,
  scale,
  format,
}: {
  ticks: number[];
  scale: Scale;
  format: (value: string) => string;
}): ReactElement {
  return (
    <>
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={PAD.left}
            x2={PAD.left + PLOT_W}
            y1={scale.y(tick)}
            y2={scale.y(tick)}
            className="stroke-border"
            strokeWidth={1}
          />
          <text
            x={PAD.left - 10}
            y={scale.y(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            className="fill-muted-foreground text-[11px] tabular-nums"
          >
            {format(String(tick))}
          </text>
        </g>
      ))}
    </>
  );
}

/** Selective x labels only (`dataviz`: never a label on every point). First, last, and a few
 *  evenly spaced between — enough to orient, few enough never to collide. */
function XLabels({
  plotted,
  scale,
  formatSpan,
}: {
  plotted: Plotted[];
  scale: Scale;
  formatSpan: (point: SeriesPoint) => string;
}): ReactElement {
  const last = plotted.length - 1;
  const every = Math.max(1, Math.ceil(plotted.length / 4));
  const anchor = (index: number): 'start' | 'middle' | 'end' => {
    if (index === 0) {
      return 'start';
    }
    return index === last ? 'end' : 'middle';
  };

  return (
    <>
      {plotted
        .filter(({ index }) => index === 0 || index === last || index % every === 0)
        .map(({ point, index }) => (
          <text
            key={point.starts_on}
            x={scale.x(index)}
            y={HEIGHT - 12}
            textAnchor={anchor(index)}
            className="fill-muted-foreground text-[11px]"
          >
            {formatSpan(point)}
          </text>
        ))}
    </>
  );
}

/** A bucket that traded fewer days than it holds gets a faint column behind it rather than a
 *  different line colour: colour carries the series, and there is only one series. */
function ShortBuckets({
  plotted,
  scale,
  bucketDays,
}: {
  plotted: Plotted[];
  scale: Scale;
  bucketDays: number;
}): ReactElement {
  return (
    <>
      {plotted
        .filter(({ point }) => point.days_traded < bucketDays)
        .map(({ point, index }) => (
          <rect
            key={`short-${point.starts_on}`}
            x={scale.x(index) - scale.band / 2}
            y={PAD.top}
            width={scale.band}
            height={PLOT_H}
            className="fill-muted"
            opacity={0.55}
          />
        ))}
    </>
  );
}

/** The line, one `<path>` per unbroken run. A single path with a gap would need NaN in its path
 *  data, which some renderers answer by dropping the whole path. */
function Line({ plotted, scale }: { plotted: Plotted[]; scale: Scale }): ReactElement {
  return (
    <>
      {runs(plotted, (entry) => entry.value).map((run) => (
        <path
          key={run[0]?.point.starts_on}
          d={run
            .map((entry, position) => {
              const command = position === 0 ? 'M' : 'L';
              const px = String(scale.x(entry.index));
              const py = String(scale.y(entry.value ?? 0));
              return `${command} ${px} ${py}`;
            })
            .join(' ')}
          fill="none"
          className="stroke-series-1"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </>
  );
}

/** >= 8px across, ringed in the surface colour so it stays legible where it crosses the grid. */
function EndMarker({ plotted, scale }: { plotted: Plotted[]; scale: Scale }): ReactElement | null {
  const last = plotted.at(-1);
  if (last === undefined) {
    return null;
  }
  return (
    <circle
      cx={scale.x(last.index)}
      cy={scale.y(last.value ?? 0)}
      r={4}
      className="fill-series-1 stroke-card"
      strokeWidth={2}
    />
  );
}

function Crosshair({ entry, scale }: { entry: Plotted; scale: Scale }): ReactElement {
  return (
    <g pointerEvents="none">
      <line
        x1={scale.x(entry.index)}
        x2={scale.x(entry.index)}
        y1={PAD.top}
        y2={PAD.top + PLOT_H}
        className="stroke-muted-foreground"
        strokeWidth={1}
      />
      <circle
        cx={scale.x(entry.index)}
        cy={scale.y(entry.value ?? 0)}
        r={5}
        className="fill-series-1 stroke-card"
        strokeWidth={2}
      />
    </g>
  );
}

/** One transparent rect per bucket, each a full band wide, because a 4px dot is not a hit
 *  target. */
function HitTargets({
  plotted,
  scale,
  onHover,
  onSelect,
}: {
  plotted: Plotted[];
  scale: Scale;
  onHover: (index: number) => void;
  // Explicitly `| undefined` rather than optional — see the note in BarChart's `Row`.
  onSelect: ((point: SeriesPoint) => void) | undefined;
}): ReactElement {
  return (
    <>
      {plotted.map(({ point, index }) => (
        <rect
          key={`hit-${point.starts_on}`}
          x={scale.x(index) - scale.band / 2}
          y={PAD.top}
          width={Math.max(scale.band, 8)}
          height={PLOT_H}
          fill="transparent"
          onPointerEnter={() => {
            onHover(index);
          }}
          onClick={
            onSelect === undefined
              ? undefined
              : () => {
                  onSelect(point);
                }
          }
          className={onSelect === undefined ? undefined : 'cursor-pointer'}
        />
      ))}
    </>
  );
}

/**
 * Drawn *inside* the SVG rather than as a positioned div, because an absolutely positioned overlay
 * needs an inline `style` and eslint forbids one — inline styles bypass the token system and the
 * theme. SVG geometry is presentation attributes, not CSS, so the same layout arrives without
 * reaching around the rule. It flips to the left of the crosshair near the right edge, so it is
 * never clipped.
 */
function Tooltip({
  entry,
  scale,
  format,
  bucketDays,
  formatSpan,
  formatTraded,
}: {
  entry: Plotted;
  scale: Scale;
  format: (value: string | null) => string;
  bucketDays: number;
  formatSpan: (point: SeriesPoint) => string;
  formatTraded: (traded: number, of: number) => string;
}): ReactElement {
  const anchorX = scale.x(entry.index);
  const flip = anchorX + 12 + TOOLTIP_W > PAD.left + PLOT_W;
  const boxX = flip ? anchorX - 12 - TOOLTIP_W : anchorX + 12;
  const short = entry.point.days_traded < bucketDays;

  return (
    <g pointerEvents="none">
      <rect
        x={boxX}
        y={PAD.top + 4}
        width={TOOLTIP_W}
        height={short ? 62 : 44}
        rx={6}
        className="fill-card stroke-border"
        strokeWidth={1}
      />
      <text x={boxX + 10} y={PAD.top + 20} className="fill-muted-foreground text-[11px]">
        {formatSpan(entry.point)}
      </text>
      <text
        x={boxX + 10}
        y={PAD.top + 38}
        className="fill-foreground text-[13px] font-medium tabular-nums"
      >
        {format(entry.point.value)}
      </text>
      {short ? (
        <text x={boxX + 10} y={PAD.top + 54} className="fill-muted-foreground text-[11px]">
          {formatTraded(entry.point.days_traded, bucketDays)}
        </text>
      ) : null}
    </g>
  );
}
