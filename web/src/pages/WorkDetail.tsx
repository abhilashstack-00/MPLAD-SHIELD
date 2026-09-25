import { Link, useParams } from "react-router-dom";
import { RiskBadge } from "../components/RiskBadge";
import { ConfidenceMeter } from "../components/ConfidenceMeter";
import { PointsBreakdown } from "../components/PointsBreakdown";
import { PeerComparison } from "../components/PeerComparison";
import { EmptyState } from "../components/EmptyState";
import { DisclaimerBanner } from "../components/DisclaimerBanner";
import { ReviewPanel } from "../components/ReviewPanel";
import { useWork, useWorkDetail } from "../data/loadScored";
import { formatDate, formatINR, formatNumber, formatPct } from "../lib/format";

/**
 * Everything behind one indicator.
 *
 * A reviewer arrives asking why a work was flagged and should leave with a
 * specific question to take to site. Provenance is shown at the bottom so any
 * figure can be traced to a source file and row.
 */
export function WorkDetail() {
  const { workId } = useParams();
  const id = workId ? decodeURIComponent(workId) : undefined;
  const summary = useWork(id);
  const { detail, loaded } = useWorkDetail(id);

  // The index entry renders immediately; the fuller record replaces it once
  // the detail payload arrives, so the page is never blank while waiting.
  const work = detail ?? summary;

  if (!loaded && !summary) {
    return <EmptyState title="Loading work…" />;
  }

  if (!work) {
    return (
      <EmptyState
        title="Work not found"
        body={`No work with ID ${id ?? ""} exists in this scoring run, or its full detail was not exported. Detail is exported for flagged works by default; re-run with --detail-scope all to include every work.`}
      />
    );
  }

  return (
    <div className="stack">
      <div>
        <Link to="/queue" className="back-link">← Back to priority queue</Link>
      </div>

      <div className="page-head">
        <h1>{work.work_description ?? work.work_id}</h1>
        <p>
          <span className="mono">{work.work_id}</span>
          {" · "}{work.district ?? "—"}, {work.state ?? "—"}
          {work.work_type ? ` · ${work.work_type}` : ""}
        </p>
      </div>

      <section className="card">
        <div className="score-panel">
          <div>
            <div className="stat__label">Analytical risk indicator</div>
            <div className="score-panel__value">
              {Math.round(work.risk_score)}
              <span className="score-panel__of"> / 100</span>
            </div>
            <div style={{ marginTop: "var(--space-2)" }}>
              <RiskBadge band={work.risk_band} />
            </div>
          </div>
          <ConfidenceMeter value={work.confidence} note={work.confidence_reason ?? undefined} />
          <div>
            <div className="stat__label">Leading indicator</div>
            <div style={{ fontWeight: 600, marginTop: "var(--space-2)" }}>
              {work.primary_reason}
            </div>
            <div className="stat__sub">
              {work.detectors_evaluated ?? 0} of 6 detectors evaluated this work
            </div>
          </div>
        </div>
      </section>

      {work.briefing && (
        <section className="card">
          <h2 className="card__title">Reviewer briefing</h2>
          <p style={{ margin: 0 }}>{work.briefing}</p>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
            Composed from the figures the detectors produced. Every sentence traces
            to a field in the record — nothing here is generated text.
          </p>
        </section>
      )}

      <section className="card">
        <h2 className="card__title">How this indicator was reached</h2>
        <PointsBreakdown work={work} />
      </section>

      <div className="grid grid--2">
        <section className="card">
          <h2 className="card__title">Peer comparison</h2>
          <PeerComparison work={work} />
        </section>

        <section className="card">
          <h2 className="card__title">Financial record</h2>
          <dl className="kv">
            <dt>Sanctioned amount</dt>
            <dd>{formatINR(work.sanction_amount)}</dd>
            <dt>Recorded expenditure</dt>
            <dd>
              {work.total_expenditure === null
                ? "No payment record"
                : `${formatINR(work.total_expenditure)} (${formatPct(
                    (work.expenditure_ratio ?? 0) * 100, 0
                  )} of sanction)`}
            </dd>
            <dt>Payments</dt>
            <dd>
              {work.payment_count === null
                ? "—"
                : `${formatNumber(work.payment_count)} across ${formatNumber(
                    work.distinct_vendors
                  )} vendor(s)`}
            </dd>
            <dt>Largest single payment</dt>
            <dd>{formatINR(work.max_single_payment)}</dd>
            <dt>Principal payee</dt>
            <dd>{work.primary_vendor ?? "—"}</dd>
          </dl>
        </section>
      </div>

      <div className="grid grid--2">
        <section className="card">
          <h2 className="card__title">Timeline</h2>
          <dl className="kv">
            <dt>Recommended</dt>
            <dd>{formatDate(work.recommended_date)}</dd>
            <dt>Sanctioned</dt>
            <dd>{formatDate(work.sanction_date)}</dd>
            <dt>Recommendation to sanction</dt>
            <dd>
              {work.days_recommendation_to_sanction === null
                ? "—"
                : `${formatNumber(work.days_recommendation_to_sanction)} days`}
            </dd>
            <dt>Completed</dt>
            <dd>{work.completion_date ? formatDate(work.completion_date) : "Not recorded"}</dd>
            <dt>Elapsed</dt>
            <dd>
              {work.days_sanction_to_reference === null
                ? "—"
                : `${formatNumber(work.days_sanction_to_reference)} days (to ${
                    work.age_basis === "completion_date" ? "completion" : "the as-of date"
                  })`}
            </dd>
            <dt>Peer median duration</dt>
            <dd>
              {work.peer_median_duration === null
                ? "Not available"
                : `${formatNumber(work.peer_median_duration)} days`}
            </dd>
            <dt>Workflow status</dt>
            <dd>{work.work_status ?? "—"}</dd>
          </dl>
        </section>

        <section className="card">
          <h2 className="card__title">Rule checks and relationships</h2>
          {work.rule_reasons ? (
            <ul style={{ margin: "0 0 var(--space-4)", paddingLeft: "var(--space-5)" }}>
              {work.rule_reasons.split("; ").map((reason) => (
                <li key={reason} style={{ marginBottom: "var(--space-2)" }}>{reason}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No configured rule was triggered for this work.</p>
          )}
          <dl className="kv">
            <dt>Similar work nearby</dt>
            <dd>
              {work.similar_work_id ? (
                <Link
                  to={`/works/${encodeURIComponent(work.similar_work_id)}`}
                  className="back-link"
                >
                  {work.similar_work_id} ({(work.similarity_score ?? 0).toFixed(2)})
                </Link>
              ) : (
                "None above the similarity threshold"
              )}
            </dd>
            <dt>Implementing authority</dt>
            <dd>{work.ida_raw ?? "—"}</dd>
            <dt>Member of Parliament</dt>
            <dd>{work.mp_name ?? "—"}</dd>
          </dl>
        </section>
      </div>

      <section className="card">
        <h2 className="card__title">Provenance</h2>
        <dl className="kv">
          <dt>Source file</dt>
          <dd>{work.source_file ?? "—"}</dd>
          <dt>Source row</dt>
          <dd>{work.source_row ?? "—"}</dd>
          <dt>Peer group</dt>
          <dd>{work.peer_key ?? "None assigned"}</dd>
          <dt>Data completeness</dt>
          <dd>{formatPct((work.data_completeness ?? 0) * 100, 0)}</dd>
        </dl>
      </section>

      <ReviewPanel workId={work.work_id} />

      <DisclaimerBanner text={work.assessment} />
    </div>
  );
}
