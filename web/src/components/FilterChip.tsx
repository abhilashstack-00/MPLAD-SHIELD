/**
 * Toggleable filter. The selected state is a filled background, not a border
 * alone -- border-only selection is close to invisible at a glance.
 */
export function FilterChip({
  label,
  active,
  color,
  count,
  onClick,
}: {
  label: string;
  active: boolean;
  color?: string;
  count?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`chip${active ? " chip--on" : ""}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {color && <span className="chip__dot" style={{ background: color }} />}
      {label}
      {count !== undefined && <span className="muted">({count})</span>}
    </button>
  );
}
