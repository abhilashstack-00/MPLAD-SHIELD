import { useScored } from "../data/loadScored";
import { formatNumber } from "../lib/format";

const LABELS: Record<string, string> = {
  sanctioned_records: "Sanctioned records",
  completed_records: "Completed records",
  expenditure_payment_records: "Expenditure payment records",
  sanctioned_distinct_ids: "Distinct sanctioned work IDs",
  completed_distinct_ids: "Distinct completed work IDs",
  expenditure_distinct_works: "Distinct works with payments",
  completed_matched_to_sanctioned: "Completed matched to sanctioned",
  completed_unmatched: "Completed unmatched",
  expenditure_matched_to_sanctioned: "Expenditure matched to sanctioned",
  expenditure_unmatched: "Expenditure unmatched",
  works_with_both_completion_and_payments: "Works with completion and payments",
  duplicate_ids_in_sanctioned: "Duplicate IDs in sanctioned",
  duplicate_ids_in_completed: "Duplicate IDs in completed",
  match_rate_completed_pct: "Completed match rate (%)",
  match_rate_expenditure_pct: "Expenditure match rate (%)",
};

/**
 * Ingestion, matching and validation, in the open.
 *
 * This page exists because a screening system that cannot describe its own
 * gaps should not be trusted about anything else. Nothing is dropped silently:
 * every quarantined row is counted here with the reason it was removed.
 */
export function DataQuality() {
  const { data_quality: q, meta } = useScored();

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Data quality</h1>
        <p>
          Source: {meta.data_source}. Ingested from {meta.source_files.length} files,
          aged against {meta.as_of_date}.
        </p>
      </div>

      <section className="card">
        <h2 className="card__title">Work-ID matching</h2>
        <div className="table-wrap">
          <table className="data">
            <tbody>
              {Object.entries(q.matching).map(([key, value]) => (
                <tr key={key} style={{ cursor: "default" }}>
                  <td>{LABELS[key] ?? key}</td>
                  <td className="num">{formatNumber(value, key.includes("pct") ? 2 : 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid grid--2">
        <section className="card">
          <h2 className="card__title">Quarantined rows ({q.quarantined_rows})</h2>
          {q.quarantine.length === 0 ? (
            <p className="muted">No rows were quarantined.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">Source</th>
                    <th scope="col" className="num">Rows</th>
                    <th scope="col">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {q.quarantine.map((row) => (
                    <tr key={`${row.quarantine_source}-${row.quarantine_reason}`} style={{ cursor: "default" }}>
                      <td>{row.quarantine_source}</td>
                      <td className="num">{row.rows}</td>
                      <td className="muted">{row.quarantine_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card">
          <h2 className="card__title">Consistency checks</h2>
          <div className="table-wrap">
            <table className="data">
              <tbody>
                {Object.entries({ ...q.dates, ...q.amounts }).map(([key, value]) => (
                  <tr key={key} style={{ cursor: "default" }}>
                    <td>{key.replace(/_/g, " ")}</td>
                    <td className="num">{value === null ? "—" : formatNumber(Number(value), 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="card">
        <h2 className="card__title">Column completeness</h2>
        <div className="table-wrap" style={{ maxHeight: 460, overflowY: "auto" }}>
          <table className="data">
            <thead>
              <tr>
                <th scope="col">Dataset</th>
                <th scope="col">Column</th>
                <th scope="col" className="num">Present</th>
                <th scope="col" className="num">Missing</th>
                <th scope="col" className="num">Complete</th>
                <th scope="col" className="num">Distinct</th>
              </tr>
            </thead>
            <tbody>
              {q.columns.map((c) => (
                <tr key={`${c.dataset}-${c.column}`} style={{ cursor: "default" }}>
                  <td className="muted">{c.dataset}</td>
                  <td>{c.column}</td>
                  <td className="num">{formatNumber(c.non_null)}</td>
                  <td className="num">{formatNumber(c.missing)}</td>
                  <td className="num">{c.completeness_pct}%</td>
                  <td className="num">{formatNumber(c.distinct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
