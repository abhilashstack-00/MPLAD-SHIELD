import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RiskBadge } from "../components/RiskBadge";
import { EmptyState } from "../components/EmptyState";
import { ModeBanner } from "../components/ModeBanner";
import { ExportButton } from "../components/ExportButton";
import { useScored } from "../data/loadScored";
import { formatDate, formatINRCompact, formatNumber } from "../lib/format";

/**
 * Works that look likely to stall.
 *
 * Presented as a rule over observable facts, not a forecast. Each row is open
 * past what comparable works took, and either has no payment recorded at all
 * or none for over a year. Saying that plainly is more defensible than calling
 * a threshold a prediction, and a reviewer can check every part of it.
 */
export function EarlyWarning() {
  const { early_warning, meta } = useScored();
  const [state, setState] = useState("");
  const navigate = useNavigate();

  const states = useMemo(
    () => Array.from(new Set(early_warning.map((r) => r.state).filter(Boolean))).sort() as string[],
    [early_warning]
  );

  const rows = useMemo(
    () => early_warning.filter((r) => !state || r.state === state),
    [early_warning, state]
  );

  const noPayment = rows.filter((r) => r.total_expenditure === null).length;

  if (early_warning.length === 0) {
    return (
      <EmptyState
        title="No works currently meet the early-warning criteria"
        body="Works must be open, past their peer-group duration, and without recent payment."
      />
    );
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Early warning</h1>
        <p>
          {formatNumber(early_warning.length)} open works running past what comparable
          works took, with no recent payment activity.
        </p>
      </div>

      <ModeBanner
        mode={meta.data_mode}
        source={meta.data_source}
        asOf={meta.as_of_date}
        engine={meta.engine_version}
      />

      <p className="disclaimer">
        This is a rule over observable facts, not a prediction. A work qualifies when
        it is still open, has run more than 1.5× its peer group's median duration, and
        either carries no payment record or none within the last year. Of the works
        listed, {formatNumber(noPayment)} have no payment recorded at all — which may
        indicate a stalled work or simply a gap in the expenditure export.
      </p>

      <section className="card">
        <select
          className="input"
          value={state}
          onChange={(e) => setState(e.target.value)}
          aria-label="Filter by state"
        >
          <option value="">All states ({formatNumber(early_warning.length)} works)</option>
          {states.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <div className="chips" style={{ marginTop: "var(--space-3)" }}>
          <ExportButton rows={rows} name="early_warning" />
        </div>
      </section>

      <section className="card" style={{ padding: 0 }}>
        <div className="table-wrap" style={{ maxHeight: 640, overflowY: "auto" }}>
          <table className="data">
            <thead>
              <tr>
                <th scope="col">Work ID</th>
                <th scope="col">Description</th>
                <th scope="col">District</th>
                <th scope="col" className="num">Sanctioned</th>
                <th scope="col">Sanctioned on</th>
                <th scope="col" className="num">Days open</th>
                <th scope="col" className="num">Peer median</th>
                <th scope="col">Band</th>
                <th scope="col">Why flagged</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.work_id}
                  tabIndex={0}
                  onClick={() => navigate(`/works/${encodeURIComponent(row.work_id)}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") navigate(`/works/${encodeURIComponent(row.work_id)}`);
                  }}
                >
                  <td className="mono">{row.work_id}</td>
                  <td>{(row.work_description ?? "—").slice(0, 52)}</td>
                  <td>{row.district ?? "—"}</td>
                  <td className="num">{formatINRCompact(row.sanction_amount)}</td>
                  <td>{formatDate(row.sanction_date)}</td>
                  <td className="num score-cell">
                    {formatNumber(row.days_sanction_to_reference)}
                  </td>
                  <td className="num muted">{formatNumber(row.peer_median_duration)}</td>
                  <td><RiskBadge band={row.risk_band} /></td>
                  <td className="muted">{row.warning_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
