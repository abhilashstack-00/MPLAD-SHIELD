import { useMemo, useState } from "react";
import { StatCard } from "../components/StatCard";
import { EmptyState } from "../components/EmptyState";
import { ModeBanner } from "../components/ModeBanner";
import { ExportButton } from "../components/ExportButton";
import { useScored } from "../data/loadScored";
import { formatDate, formatINR, formatINRCompact, formatNumber } from "../lib/format";

/**
 * Works recommended by an MP but never sanctioned.
 *
 * These are invisible to every other page, and to any analysis built on the
 * sanctioned register, because they carry no work ID at all — their entry in
 * the recommendation export begins "NA-". They are a different administrative
 * problem from a sanctioned work running late: nothing has been approved,
 * nothing has been spent, and the person to chase sits at the sanctioning
 * authority rather than the implementing agency.
 */
export function Pipeline() {
  const { recommendation_pipeline: pipeline, meta, national } = useScored();
  const [state, setState] = useState("");

  const rows = useMemo(
    () => pipeline.oldest.filter((r) => !state || r.state === state),
    [pipeline.oldest, state]
  );

  const states = useMemo(
    () => pipeline.by_state.map((s) => s.state).filter(Boolean) as string[],
    [pipeline.by_state]
  );

  if (!pipeline.available) {
    return (
      <EmptyState
        title="No recommendation register loaded"
        body="Add Works_Recommended.xlsx to data/raw and re-run the pipeline to see works recommended but not yet sanctioned."
      />
    );
  }

  const maxWorks = Math.max(...pipeline.by_state.map((s) => s.works), 1);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Recommendation pipeline</h1>
        <p>
          Works recommended by Members of Parliament that have not been sanctioned.
        </p>
      </div>

      <ModeBanner
        mode={meta.data_mode}
        source={meta.data_source}
        asOf={meta.as_of_date}
        engine={meta.engine_version}
      />

      <div className="grid grid--3">
        <StatCard
          label="Recommended, not sanctioned"
          value={formatNumber(pipeline.works)}
          sub="No work ID assigned and no sanction date recorded"
        />
        <StatCard
          label="Value held in the pipeline"
          value={formatINRCompact(pipeline.value)}
          sub="Recommended amounts awaiting sanction"
        />
        <StatCard
          label="Share of all recommendations"
          value={`${((pipeline.works / (pipeline.works + national.works)) * 100).toFixed(1)}%`}
          sub={`${formatNumber(pipeline.works + national.works)} works recommended in total`}
        />
      </div>

      <p className="disclaimer">
        A recommendation awaiting sanction is not by itself irregular. Scrutiny,
        estimation and administrative approval all take time, and some
        recommendations are properly declined. What this page provides is
        visibility: these works appear in no other view, because the sanctioned
        register — the source every other page draws on — cannot contain them.
      </p>

      <section className="card">
        <h2 className="card__title">Pipeline by state</h2>
        <div className="stack" style={{ gap: "var(--space-3)" }}>
          {pipeline.by_state.slice(0, 12).map((row) => (
            <div key={row.state ?? "unknown"}>
              <div className="row-between" style={{ marginBottom: "var(--space-1)" }}>
                <span>{row.state ?? "—"}</span>
                <span className="num muted">
                  {formatNumber(row.works)} · {formatINRCompact(row.value)}
                </span>
              </div>
              <div className="bar">
                <span
                  className="bar__seg"
                  style={{
                    width: `${(row.works / maxWorks) * 100}%`,
                    background: "var(--ind-cost_deviation)",
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="row-between">
          <h2 className="card__title" style={{ marginBottom: 0 }}>
            Longest awaiting sanction
          </h2>
          <ExportButton rows={rows} name="recommendation_pipeline" />
        </div>
        <p className="muted" style={{ fontSize: 13 }}>
          Oldest recommendations first. A long wait may reflect a work properly
          held back, or one that has simply been forgotten — the record alone
          cannot distinguish them.
        </p>

        <select
          className="input"
          value={state}
          onChange={(e) => setState(e.target.value)}
          aria-label="Filter by state"
          style={{ marginBottom: "var(--space-4)" }}
        >
          <option value="">All states</option>
          {states.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <div className="table-wrap" style={{ maxHeight: 520, overflowY: "auto" }}>
          <table className="data">
            <thead>
              <tr>
                <th scope="col">Recommended on</th>
                <th scope="col">Description</th>
                <th scope="col">District</th>
                <th scope="col">State</th>
                <th scope="col">Recommended by</th>
                <th scope="col" className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} style={{ cursor: "default" }}>
                  <td>{formatDate(row.recommended_on)}</td>
                  <td>{(row.work_description ?? "—").slice(0, 60)}</td>
                  <td>{row.district ?? "—"}</td>
                  <td>{row.state ?? "—"}</td>
                  <td className="muted">{row.mp_name ?? "—"}</td>
                  <td className="num">{formatINR(row.recommended_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
