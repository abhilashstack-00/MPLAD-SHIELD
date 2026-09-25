import { StatCard } from "../components/StatCard";
import { RiskBadge } from "../components/RiskBadge";
import { ModeBanner } from "../components/ModeBanner";
import { useScored } from "../data/loadScored";
import { formatINRCompact, formatNumber, formatPct } from "../lib/format";
import { colorForLabel } from "../lib/indicators";
import type { RiskBand } from "../types/scored";

/**
 * Screening overview.
 *
 * Every figure comes from the engine's `dashboard` block. The UI counts
 * nothing itself, and each headline states what it means rather than leaving
 * a bare number to be interpreted.
 */
export function Dashboard() {
  const { dashboard: d, meta, data_quality } = useScored();
  const maxReason = Math.max(...d.flag_reasons.map((r) => r.works), 1);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Review prioritisation overview</h1>
        <p>AI-assisted screening of MPLADS works for human review</p>
      </div>

      <ModeBanner
        mode={meta.data_mode}
        source={meta.data_source}
        asOf={meta.as_of_date}
        engine={meta.engine_version}
      />

      <div className="grid grid--3">
        <StatCard
          label="Works ingested"
          value={formatNumber(d.works_total)}
          sub={`${formatNumber(data_quality.coverage.works_completed)} completed · ${formatNumber(
            d.works_with_expenditure
          )} with payment records`}
          to="/works"
        />
        <StatCard
          label="High analytical priority"
          value={formatNumber(d.high_priority)}
          sub={`Indicator at or above ${d.bands.high} of 100`}
          to="/queue"
        />
        <StatCard
          label="Flagged for review"
          value={formatNumber(d.works_requiring_review)}
          sub={`${formatPct((d.works_requiring_review / d.works_total) * 100, 1)} of the register`}
          to="/queue"
        />
      </div>

      <div className="grid grid--3">
        <StatCard
          label="Total sanctioned"
          value={formatINRCompact(d.total_sanctioned)}
          sub="Sum of sanctioned amounts in the supplied export"
        />
        <StatCard
          label="Recorded expenditure"
          value={formatINRCompact(d.total_expenditure)}
          sub="Aggregated from payment-level records only"
        />
        <StatCard
          label="Mean data completeness"
          value={formatPct(d.mean_data_completeness * 100, 0)}
          sub="Across the fields the detectors require"
          to="/quality"
        />
      </div>

      <div className="grid grid--2">
        <section className="card">
          <h2 className="card__title">Analytical priority bands</h2>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">Band</th>
                  <th scope="col" className="num">Works</th>
                  <th scope="col" className="num">Share</th>
                  <th scope="col" className="num">Mean indicator</th>
                </tr>
              </thead>
              <tbody>
                {d.risk_distribution.map((band) => (
                  <tr key={band.risk_band} style={{ cursor: "default" }}>
                    <td><RiskBadge band={band.risk_band as RiskBand} /></td>
                    <td className="num">{formatNumber(band.works)}</td>
                    <td className="num">{formatPct(band.share_pct, 1)}</td>
                    <td className="num">{band.mean_score.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <h2 className="card__title">Leading indicator, for flagged works</h2>
          <div className="stack" style={{ gap: "var(--space-3)" }}>
            {d.flag_reasons.map((reason) => (
              <div key={reason.reason}>
                <div className="row-between" style={{ marginBottom: "var(--space-1)" }}>
                  <span>{reason.reason}</span>
                  <span className="num muted">{formatNumber(reason.works)}</span>
                </div>
                <div className="bar">
                  <span
                    className="bar__seg"
                    style={{
                      width: `${(reason.works / maxReason) * 100}%`,
                      background: colorForLabel(reason.reason),
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="card">
        <h2 className="card__title">What this system does not claim</h2>
        <ul style={{ margin: 0, paddingLeft: "var(--space-5)" }} className="muted">
          {meta.limitations.map((line) => (
            <li key={line} style={{ marginBottom: "var(--space-2)" }}>{line}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
