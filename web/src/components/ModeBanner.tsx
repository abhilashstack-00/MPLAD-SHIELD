/**
 * Standing statement of what data is on screen.
 *
 * Present on every page on purpose. The single most damaging thing this
 * interface could do is let a reviewer mistake a synthetic benchmark for
 * official data, so the source is never more than a glance away.
 */
export function ModeBanner({
  mode,
  source,
  asOf,
  engine,
}: {
  mode: string;
  source: string;
  asOf: string;
  engine: string;
}) {
  const official = mode === "official_export";
  return (
    <div className="disclaimer" style={{ marginBottom: "var(--space-4)" }}>
      <strong>{official ? "Official export" : "Synthetic demonstration data"}</strong>
      {" — "}
      {source}. Works still open are aged against {asOf}. Engine {engine}.
      {!official && " Figures on this page are generated for testing and describe no real work."}
    </div>
  );
}
