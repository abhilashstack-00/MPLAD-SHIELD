import { useNavigate } from "react-router-dom";
import { RiskBadge } from "./RiskBadge";
import { EmptyState } from "./EmptyState";
import { formatINRCompact } from "../lib/format";
import type { QueueRow } from "../types/scored";
import { REVIEW_LABELS, useReviews } from "../lib/reviewState";

/**
 * Ranked list of works for review.
 *
 * Confidence sits beside the score deliberately: a high score on a work whose
 * only peer group was a broad category is a weaker prompt than the same score
 * backed by same-work-type comparison, and a reviewer choosing what to inspect
 * needs to see that without opening the record.
 */
export function QueueTable({
  rows,
  emptyTitle = "No works match these filters",
  emptyBody,
}: {
  rows: QueueRow[];
  emptyTitle?: string;
  emptyBody?: string;
}) {
  const navigate = useNavigate();
  const { statusOf } = useReviews();
  if (rows.length === 0) return <EmptyState title={emptyTitle} body={emptyBody} />;

  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th scope="col">Work ID</th>
            <th scope="col">Description</th>
            <th scope="col">District</th>
            <th scope="col" className="num">Sanctioned</th>
            <th scope="col">Status</th>
            <th scope="col" className="num">Indicator</th>
            <th scope="col">Band</th>
            <th scope="col">Confidence</th>
            <th scope="col">Main reason</th>
            <th scope="col">Review</th>
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
              <td>{(row.work_description ?? "—").slice(0, 60)}</td>
              <td>{row.district ?? "—"}</td>
              <td className="num">{formatINRCompact(row.sanction_amount)}</td>
              <td className="muted">{row.work_status ?? "—"}</td>
              <td
                className="num score-cell"
                aria-label={`${Math.round(row.risk_score)} out of 100, ${row.risk_band} priority`}
              >
                {Math.round(row.risk_score)}
              </td>
              <td><RiskBadge band={row.risk_band} /></td>
              <td>{row.confidence_band}</td>
              <td>{row.primary_reason}</td>
              <td className="muted">
                {statusOf(row.work_id) === "not_reviewed"
                  ? "—"
                  : REVIEW_LABELS[statusOf(row.work_id)]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
