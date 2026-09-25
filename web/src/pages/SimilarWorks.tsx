import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { useScored, useWorkIndex } from "../data/loadScored";
import { formatINRCompact } from "../lib/format";

/**
 * Works whose descriptions closely resemble another nearby work.
 *
 * Both records are shown side by side, because the judgement this page asks a
 * reviewer to make cannot be made from a similarity score alone. The label is
 * "potentially similar", never "duplicate": two works can legitimately share a
 * description across different wards.
 */
export function SimilarWorks() {
  const { similar_pairs } = useScored();
  const index = useWorkIndex();

  if (similar_pairs.length === 0) {
    return <EmptyState title="No potentially similar works were identified" />;
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Potentially similar works</h1>
        <p>
          Description pairs within the same district, ranked by text similarity.
          These require verification and are not confirmed duplicates.
        </p>
      </div>

      <div className="stack">
        {similar_pairs.slice(0, 60).map((pair) => {
          const other = index.get(pair.similar_work_id);
          return (
            <section className="card" key={`${pair.work_id}-${pair.similar_work_id}`}>
              <div className="row-between" style={{ marginBottom: "var(--space-3)" }}>
                <strong>
                  {pair.district ?? "—"}, {pair.state ?? "—"}
                </strong>
                <span className="muted">
                  Similarity {(pair.similarity_score ?? 0).toFixed(2)}
                </span>
              </div>
              <div className="grid grid--2">
                {[
                  { id: pair.work_id, desc: pair.work_description, amount: pair.sanction_amount },
                  {
                    id: pair.similar_work_id,
                    desc: other?.work_description ?? "—",
                    amount: other?.sanction_amount ?? null,
                  },
                ].map((side) => (
                  <div key={side.id} className="card" style={{ boxShadow: "none" }}>
                    <Link to={`/works/${encodeURIComponent(side.id)}`} className="mono back-link">
                      {side.id}
                    </Link>
                    <p style={{ margin: "var(--space-2) 0" }}>{side.desc}</p>
                    <div className="muted">Sanctioned {formatINRCompact(side.amount)}</div>
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
