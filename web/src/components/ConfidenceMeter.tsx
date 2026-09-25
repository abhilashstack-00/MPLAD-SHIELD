/**
 * Confidence in the record, not in the risk.
 *
 * Deliberately uses the neutral ramp rather than the risk palette, and sits
 * beside the score rather than inside a tooltip: if a high score rests on a
 * half-empty record, the reviewer has to see that without hovering.
 */
export function ConfidenceMeter({ value, note }: { value: number; note?: string }) {
  const filled = Math.round(value * 3);
  const label = value >= 0.85 ? "High" : value >= 0.6 ? "Moderate" : "Low";

  return (
    <div>
      <div className="stat__label">Confidence</div>
      <div
        className="conf"
        role="img"
        aria-label={`Confidence ${label}, ${Math.round(value * 100)} percent`}
      >
        {[0, 1, 2].map((i) => (
          <span key={i} className={`conf__seg${i < filled ? " conf__seg--on" : ""}`} />
        ))}
      </div>
      <div className="stat__sub">
        {label} · {Math.round(value * 100)}%
      </div>
      {note && <div className="stat__sub">{note}</div>}
    </div>
  );
}
