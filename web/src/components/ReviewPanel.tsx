import { useEffect, useState } from "react";
import { REVIEW_LABELS, REVIEW_ORDER, useReviews, type ReviewStatus } from "../lib/reviewState";

/**
 * Records a reviewer's verdict against one work.
 *
 * The banner is not boilerplate. This prototype has no backend, so a verdict
 * recorded here stays in this browser and is filed with nobody. An interface
 * that implied otherwise would be actively misleading in a governance
 * context, which is the one place that matters most.
 */
export function ReviewPanel({ workId }: { workId: string }) {
  const { setReview, reviews } = useReviews();
  const existing = reviews[workId];
  const [note, setNote] = useState(existing?.note ?? "");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setNote(existing?.note ?? "");
  }, [workId, existing?.note]);

  const apply = (status: ReviewStatus) => {
    setReview(workId, status, note);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  };

  return (
    <section className="card">
      <h2 className="card__title">Reviewer action</h2>

      <div className="chips" style={{ marginBottom: "var(--space-4)" }}>
        {REVIEW_ORDER.map((status) => (
          <button
            key={status}
            type="button"
            className={`chip${existing?.status === status ? " chip--on" : ""}`}
            aria-pressed={existing?.status === status}
            onClick={() => apply(status)}
          >
            {REVIEW_LABELS[status]}
          </button>
        ))}
        {existing && (
          <button type="button" className="chip" onClick={() => apply("not_reviewed")}>
            Clear
          </button>
        )}
      </div>

      <label htmlFor="review-note" className="stat__label">
        Note
      </label>
      <textarea
        id="review-note"
        className="input"
        rows={3}
        value={note}
        placeholder="What did you check, and what did you find?"
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => existing && setReview(workId, existing.status, note)}
      />

      <div className="row-between" style={{ marginTop: "var(--space-3)" }}>
        <span className="muted" style={{ fontSize: 12.5 }}>
          {existing
            ? `${REVIEW_LABELS[existing.status]} · recorded ${new Date(
                existing.reviewed_at
              ).toLocaleString("en-IN")}`
            : "No verdict recorded for this work."}
        </span>
        {saved && <span className="badge badge--Low">Saved locally</span>}
      </div>

      <p className="disclaimer" style={{ marginTop: "var(--space-4)" }}>
        Verdicts are stored in this browser only. This prototype has no backend
        and submits nothing to any government system. In deployment these records
        become the reviewed-outcome labels that would, for the first time, allow
        detector performance to be measured against real findings.
      </p>
    </section>
  );
}
