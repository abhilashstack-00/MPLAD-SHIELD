import { useMemo, useState } from "react";
import { ModeBanner } from "../components/ModeBanner";
import { EmptyState } from "../components/EmptyState";
import { useScored } from "../data/loadScored";
import { formatINRCompact, formatNumber, formatPct } from "../lib/format";

type SeriesKey = "sanctioned" | "completed" | "expenditure";

const SERIES: { key: SeriesKey; label: string; colour: string; note: string }[] = [
  { key: "sanctioned", label: "Sanctioned", colour: "var(--ind-cost_deviation)",
    note: "by sanction month" },
  { key: "completed", label: "Completed", colour: "var(--ind-multivariate)",
    note: "by completion month" },
  { key: "expenditure", label: "Expenditure", colour: "var(--ind-expenditure_mismatch)",
    note: "by first payment month" },
];

/**
 * Movement over time.
 *
 * Three series on three different clocks — a work is sanctioned in one month,
 * paid in another and completed in a third — so they are drawn separately
 * rather than stacked, which would imply a relationship the data does not
 * support. Charts are inline SVG: no charting dependency, nothing to load.
 */
export function Trends() {
  const { trends, meta } = useScored();
  const [series, setSeries] = useState<SeriesKey>("sanctioned");
  const [measure, setMeasure] = useState<"count" | "amount">("count");

  const points = useMemo(
    () =>
      trends.monthly
        .filter((p) => p.series === series)
        .sort((a, b) => a.month.localeCompare(b.month)),
    [trends.monthly, series]
  );

  const risk = useMemo(
    () => [...trends.risk_by_month].sort((a, b) => a.month.localeCompare(b.month)),
    [trends.risk_by_month]
  );

  if (points.length === 0) {
    return <EmptyState title="No dated records available for trend analysis" />;
  }

  const values = points.map((p) => (measure === "count" ? p.count : Number(p.amount ?? 0)));
  const peak = Math.max(...values, 1);
  const width = 920;
  const height = 240;
  const barWidth = width / points.length;

  const riskPeak = Math.max(...risk.map((r) => Number(r.high_risk_pct ?? 0)), 1);
  const riskPath = risk
    .map((r, i) => {
      const x = (i / Math.max(risk.length - 1, 1)) * width;
      const y = height - (Number(r.high_risk_pct ?? 0) / riskPeak) * (height - 20);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const total = values.reduce((a, b) => a + b, 0);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Trends</h1>
        <p>
          {points.length} months of activity, {risk.length} months of risk composition.
        </p>
      </div>

      <ModeBanner
        mode={meta.data_mode}
        source={meta.data_source}
        asOf={meta.as_of_date}
        engine={meta.engine_version}
      />

      <section className="card">
        <div className="chips" style={{ marginBottom: "var(--space-3)" }}>
          {SERIES.map((option) => (
            <button
              key={option.key}
              type="button"
              className={`chip${series === option.key ? " chip--on" : ""}`}
              aria-pressed={series === option.key}
              onClick={() => setSeries(option.key)}
            >
              <span className="chip__dot" style={{ background: option.colour }} />
              {option.label}
            </button>
          ))}
        </div>
        <div className="chips">
          {(["count", "amount"] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={`chip${measure === option ? " chip--on" : ""}`}
              aria-pressed={measure === option}
              onClick={() => setMeasure(option)}
            >
              {option === "count" ? "Number of works" : "Rupee value"}
            </button>
          ))}
        </div>

        <h2 className="card__title" style={{ marginTop: "var(--space-5)" }}>
          {SERIES.find((s) => s.key === series)?.label} per month
          <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>
            {" "}— {SERIES.find((s) => s.key === series)?.note}
          </span>
        </h2>

        <div className="table-wrap">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            width="100%"
            height={height}
            role="img"
            aria-label={`${series} per month`}
          >
            {points.map((point, i) => {
              const value = measure === "count" ? point.count : Number(point.amount ?? 0);
              const barHeight = (value / peak) * (height - 24);
              return (
                <rect
                  key={point.month}
                  x={i * barWidth + 1}
                  y={height - barHeight}
                  width={Math.max(barWidth - 2, 1)}
                  height={barHeight}
                  fill={SERIES.find((s) => s.key === series)?.colour}
                >
                  <title>
                    {point.month}:{" "}
                    {measure === "count"
                      ? `${formatNumber(point.count)} works`
                      : formatINRCompact(point.amount)}
                  </title>
                </rect>
              );
            })}
          </svg>
        </div>

        <div className="peer__caption">
          <span>{points[0].month}</span>
          <span>
            Total{" "}
            {measure === "count" ? formatNumber(total) : formatINRCompact(total)}
          </span>
          <span>{points[points.length - 1].month}</span>
        </div>
      </section>

      <section className="card">
        <h2 className="card__title">High-priority share by sanction month</h2>
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          Whether the flagged share is rising, or simply tracking volume. A month with
          few sanctions can swing sharply, so read the line alongside the bars above.
        </p>
        <div className="table-wrap">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            width="100%"
            height={height}
            role="img"
            aria-label="High-priority share by month"
          >
            <path d={riskPath} fill="none" stroke="var(--risk-high)" strokeWidth={2} />
            {risk.map((r, i) => {
              const x = (i / Math.max(risk.length - 1, 1)) * width;
              const y = height - (Number(r.high_risk_pct ?? 0) / riskPeak) * (height - 20);
              return (
                <circle key={r.month} cx={x} cy={y} r={2.5} fill="var(--risk-high)">
                  <title>
                    {r.month}: {formatPct(r.high_risk_pct ?? 0, 1)} of{" "}
                    {formatNumber(r.works)} works
                  </title>
                </circle>
              );
            })}
          </svg>
        </div>
        <div className="peer__caption">
          <span>{risk[0]?.month}</span>
          <span>Peak {formatPct(riskPeak, 1)}</span>
          <span>{risk[risk.length - 1]?.month}</span>
        </div>
      </section>
    </div>
  );
}
