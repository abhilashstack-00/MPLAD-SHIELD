import { pointsByIndicator, type Work } from "../types/scored";
import { INDICATOR_COLOR } from "../lib/indicators";

const MATERIAL_POINTS = 3;

/**
 * How a score was arrived at.
 *
 * The engine defines the risk score as the sum of these points, so the bar and
 * the rows genuinely add up to the number above them. A reviewer who asks
 * "why 82?" gets arithmetic, not a summary.
 */
export function PointsBreakdown({ work }: { work: Work }) {
  const all = pointsByIndicator(work);
  const material = all.filter((i) => i.points >= MATERIAL_POINTS);
  const other = all
    .filter((i) => i.points > 0 && i.points < MATERIAL_POINTS)
    .reduce((sum, i) => sum + i.points, 0);

  const detailByLabel = new Map(
    (work.explanation ?? []).map((e) => [e.indicator, e.detail])
  );
  const total = Math.max(work.risk_score, 0.01);

  if (material.length === 0) {
    return <p className="muted">No indicator contributed materially to this score.</p>;
  }

  return (
    <div>
      <div className="bar" role="img" aria-label="Contribution of each indicator">
        {material.map((i) => (
          <span
            key={i.key}
            className="bar__seg"
            style={{ width: `${(i.points / total) * 100}%`, background: INDICATOR_COLOR[i.key] }}
          />
        ))}
        {other > 0 && (
          <span
            className="bar__seg"
            style={{ width: `${(other / total) * 100}%`, background: "var(--border-strong)" }}
          />
        )}
      </div>

      <div style={{ marginTop: "var(--space-4)" }}>
        {material.map((i) => (
          <div className="breakdown__row" key={i.key}>
            <span className="breakdown__swatch" style={{ background: INDICATOR_COLOR[i.key] }} />
            <div>
              <div className="breakdown__label">{i.label}</div>
              {detailByLabel.get(i.label) && (
                <div className="breakdown__detail">{detailByLabel.get(i.label)}</div>
              )}
            </div>
            <div className="breakdown__points">
              {i.points.toFixed(1)} pts
              <span className="breakdown__share">{((i.points / total) * 100).toFixed(0)}%</span>
            </div>
          </div>
        ))}
        {other > 0 && (
          <div className="breakdown__row">
            <span className="breakdown__swatch" style={{ background: "var(--border-strong)" }} />
            <div>
              <div className="breakdown__label muted">Other indicators</div>
              <div className="breakdown__detail">None individually material</div>
            </div>
            <div className="breakdown__points muted">{other.toFixed(1)} pts</div>
          </div>
        )}
      </div>
    </div>
  );
}
