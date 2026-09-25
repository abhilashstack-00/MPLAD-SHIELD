import { useScored } from "../data/loadScored";
import { formatNumber } from "../lib/format";
import { RULE_TIER_LABEL } from "../lib/indicators";

/**
 * What ran, what was skipped, and why.
 *
 * A detector that could not run reports `skipped` with the missing field
 * named. That distinction is the point of this page: silence and "checked and
 * found nothing" are different claims, and conflating them is how a screening
 * system ends up overstating its own coverage.
 */
export function Detectors() {
  const { detectors, rules, dashboard } = useScored();

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Detectors and rules</h1>
        <p>Detector results depend on the fields available in the supplied data.</p>
      </div>

      <section className="card">
        <h2 className="card__title">Detectors</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">Detector</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">Evaluated</th>
                <th scope="col" className="num">Flagged</th>
                <th scope="col" className="num">Max points</th>
                <th scope="col">What it checks</th>
              </tr>
            </thead>
            <tbody>
              {detectors.map((d) => (
                <tr key={d.detector} style={{ cursor: "default" }}>
                  <td><strong>{d.detector}</strong></td>
                  <td>
                    <span className={`badge badge--${d.status === "active" ? "Low" : "Medium"}`}>
                      {d.status}
                    </span>
                  </td>
                  <td className="num">{formatNumber(d.records_evaluated)}</td>
                  <td className="num">{formatNumber(d.records_flagged)}</td>
                  <td className="num">
                    {Math.round(
                      (dashboard.caps[d.detector as keyof typeof dashboard.caps] ?? 0) * 100
                    )}
                  </td>
                  <td className="muted">
                    {d.reason}
                    {d.missing_fields.length > 0 && (
                      <> Missing: {d.missing_fields.join(", ")}.</>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2 className="card__title">Rule engine</h2>
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          None of these thresholds is quoted from an MPLADS guideline document.
          Each is tagged with the authority it carries, and a rule whose fields
          are unavailable is reported as not evaluated rather than as passed.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">Rule</th>
                <th scope="col">Tier</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">Flagged</th>
                <th scope="col">Basis</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.rule_id} style={{ cursor: "default" }}>
                  <td>
                    <span className="mono">{r.rule_id}</span>
                    <div>{r.name}</div>
                  </td>
                  <td>{RULE_TIER_LABEL[r.rule_type] ?? r.rule_type}</td>
                  <td>
                    <span
                      className={`badge badge--${
                        r.status === "evaluated" ? "Low" : "Medium"
                      }`}
                    >
                      {r.status === "evaluated" ? "evaluated" : "not evaluated"}
                    </span>
                  </td>
                  <td className="num">{formatNumber(r.records_flagged)}</td>
                  <td className="muted">{r.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
