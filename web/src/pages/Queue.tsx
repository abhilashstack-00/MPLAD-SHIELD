import { useMemo, useState } from "react";
import { QueueTable } from "../components/QueueTable";
import { FilterChip } from "../components/FilterChip";
import { ModeBanner } from "../components/ModeBanner";
import { ExportButton } from "../components/ExportButton";
import { REVIEW_LABELS, useReviews } from "../lib/reviewState";
import { useScored } from "../data/loadScored";
import type { QueueRow, RiskBand } from "../types/scored";

const BANDS: RiskBand[] = ["High", "Medium", "Low"];
const PAGE_SIZE = 100;

/**
 * The ranked shortlist a reviewer works through.
 *
 * Order comes from the engine — indicator first, then confidence. The UI does
 * not re-rank, it only filters.
 */
export function Queue() {
  const { priority_queue, meta, dashboard } = useScored();
  const [bands, setBands] = useState<RiskBand[]>([]);
  const [state, setState] = useState<string>("");
  const [hideReviewed, setHideReviewed] = useState(false);
  const { statusOf, count } = useReviews();
  const [visible, setVisible] = useState(PAGE_SIZE);

  const states = useMemo(
    () => Array.from(new Set(priority_queue.map((r) => r.state).filter(Boolean))).sort(),
    [priority_queue]
  );

  const rows = useMemo<QueueRow[]>(
    () =>
      priority_queue
        .filter((r) => bands.length === 0 || bands.includes(r.risk_band))
        .filter((r) => !state || r.state === state)
        .filter((r) => !hideReviewed || statusOf(r.work_id) === "not_reviewed"),
    [priority_queue, bands, state, hideReviewed, statusOf]
  );

  // Exported rows carry the reviewer's own verdict alongside the engine's
  // output, which is what makes the file useful away from the screen.
  const exportRows = rows.map((r) => ({
    ...r,
    review_status: REVIEW_LABELS[statusOf(r.work_id)],
  }));

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Priority review queue</h1>
        <p>
          {priority_queue.length.toLocaleString("en-IN")} high and medium priority works by analytical indicator, out of{" "}
          {dashboard.works_total.toLocaleString("en-IN")} screened
        </p>
      </div>

      <ModeBanner
        mode={meta.data_mode}
        source={meta.data_source}
        asOf={meta.as_of_date}
        engine={meta.engine_version}
      />

      <section className="card">
        <div className="chips">
          {BANDS.map((band) => (
            <FilterChip
              key={band}
              label={band}
              active={bands.includes(band)}
              onClick={() => {
                setBands((b) =>
                  b.includes(band) ? b.filter((x) => x !== band) : [...b, band]
                );
                setVisible(PAGE_SIZE);
              }}
            />
          ))}
        </div>
        <div className="chips" style={{ marginTop: "var(--space-3)" }}>
          <button
            type="button"
            className={`chip${hideReviewed ? " chip--on" : ""}`}
            aria-pressed={hideReviewed}
            onClick={() => setHideReviewed((v) => !v)}
          >
            Hide works I have reviewed ({count})
          </button>
          <ExportButton rows={exportRows} name="priority_queue" />
        </div>

        <div style={{ marginTop: "var(--space-4)" }}>
          <select
            className="input"
            value={state}
            onChange={(e) => {
              setState(e.target.value);
              setVisible(PAGE_SIZE);
            }}
            aria-label="Filter by state"
          >
            <option value="">All states</option>
            {states.map((s) => (
              <option key={s} value={s ?? ""}>{s}</option>
            ))}
          </select>
        </div>
      </section>

      <section className="card" style={{ padding: 0 }}>
        <QueueTable
          rows={rows.slice(0, visible)}
          emptyTitle="No works match these filters"
          emptyBody="Clear a filter to widen the queue."
        />
      </section>

      {visible < rows.length && (
        <button
          type="button"
          className="chip"
          style={{ alignSelf: "flex-start" }}
          onClick={() => setVisible((v) => v + PAGE_SIZE)}
        >
          Show {Math.min(PAGE_SIZE, rows.length - visible)} more
        </button>
      )}
    </div>
  );
}
