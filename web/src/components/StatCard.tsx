import { Link } from "react-router-dom";

/**
 * A dashboard headline figure. Every stat links to the filtered list behind it:
 * a count a reviewer cannot drill into is decoration.
 */
export function StatCard({
  label,
  value,
  sub,
  to,
}: {
  label: string;
  value: string | number;
  sub?: string;
  to?: string;
}) {
  const body = (
    <>
      <div className="stat__label">{label}</div>
      <div className="stat__value">{value}</div>
      {sub && <div className="stat__sub">{sub}</div>}
    </>
  );

  return to ? (
    <Link to={to} className="stat">
      {body}
    </Link>
  ) : (
    <div className="stat">{body}</div>
  );
}
