import { useScored } from "../data/loadScored";

/**
 * What the system does, what it does not, and how the indicator is built.
 *
 * Written to be read aloud in a viva. Everything here is checkable against the
 * Detectors and Data quality pages rather than asserted.
 */
export function Methodology() {
  const { meta, dashboard } = useScored();

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Methodology and transparency</h1>
        <p>How the analytical indicator is produced, and what it does not mean.</p>
      </div>

      <section className="card">
        <h2 className="card__title">What this system does</h2>
        <p>
          It reads official MPLADS exports, reconciles sanctioned works with
          completion and payment records, and ranks works by how unusual they
          look against comparable works. The output is a prioritised list for
          human review: <strong>Detect → Explain → Prioritise → Investigate</strong>.
        </p>
        <h2 className="card__title" style={{ marginTop: "var(--space-5)" }}>
          What it does not do
        </h2>
        <ul style={{ margin: 0, paddingLeft: "var(--space-5)" }}>
          {meta.limitations.map((line) => (
            <li key={line} style={{ marginBottom: "var(--space-2)" }}>{line}</li>
          ))}
          <li>It does not replace auditors, district authorities or inspection teams.</li>
          <li>It is not connected to any live government system.</li>
        </ul>
      </section>

      <section className="card">
        <h2 className="card__title">How the indicator is calculated</h2>
        <p>
          Six detectors each return a value between 0 and 1. They are combined
          as independent evidence rather than averaged, so a work that is
          flagrant on one dimension is not diluted by five quiet ones. The
          combination runs in log space, which makes the result exactly
          decomposable: the points shown against each indicator always sum to
          the score.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th scope="col">Indicator</th>
                <th scope="col" className="num">Maximum points alone</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(dashboard.caps).map(([key, cap]) => (
                <tr key={key} style={{ cursor: "default" }}>
                  <td>{key.replace(/_/g, " ")}</td>
                  <td className="num">{Math.round(cap * 100)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>
          Bands: High at {dashboard.bands.high} and above, Medium from{" "}
          {dashboard.bands.medium}. Chosen to produce a queue a district team can
          work through, and recorded with every run.
        </p>
      </section>

      <section className="card">
        <h2 className="card__title">Peer comparison</h2>
        <p>
          Nothing is judged against a national average. Each work is compared
          against works of the same type in the same state where possible. The
          scheme's own category field is 97% "Normal/Others", so where no work
          type is available the comparison falls back to a broader group — and
          that fallback lowers the confidence attached to the result rather than
          being hidden.
        </p>
      </section>

      <section className="card">
        <h2 className="card__title">Risk versus confidence</h2>
        <p>
          The indicator says how unusual the observed patterns are. Confidence
          says how much that judgement can be relied on, given how complete the
          record is, how many detectors could run, and how strong the peer group
          was. A high indicator with low confidence is a prompt to check the
          record first, not to inspect the work.
        </p>
      </section>

      <section className="card">
        <h2 className="card__title">Run provenance</h2>
        <dl className="kv">
          <dt>Data mode</dt><dd>{meta.data_mode}</dd>
          <dt>Source</dt><dd>{meta.data_source}</dd>
          <dt>Source files</dt><dd>{meta.source_files.join(", ")}</dd>
          <dt>As-of date</dt><dd>{meta.as_of_date}</dd>
          <dt>Engine version</dt><dd>{meta.engine_version}</dd>
          <dt>Config version</dt><dd>{meta.config_version}</dd>
          <dt>Generated at</dt><dd>{meta.generated_at}</dd>
        </dl>
      </section>
    </div>
  );
}
