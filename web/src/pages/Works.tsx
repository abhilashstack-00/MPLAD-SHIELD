import { useMemo, useState } from "react";
import { QueueTable } from "../components/QueueTable";
import { useScored } from "../data/loadScored";
import type { QueueRow } from "../types/scored";

const PAGE_SIZE = 100;

/** The full register, searchable client-side over the loaded payload. */
export function Works() {
  const { works } = useScored();
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(PAGE_SIZE);

  const rows = useMemo<QueueRow[]>(() => {
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? works.filter((w) =>
          [
            w.work_id, w.district, w.state, w.work_category, w.work_type,
            w.mp_name, w.work_description, w.primary_vendor,
          ].join(" ").toLowerCase().includes(needle)
        )
      : works;

    return matched
      .slice()
      .sort((a, b) => b.risk_score - a.risk_score)
      .map((w) => ({
        work_id: w.work_id,
        work_description: w.work_description,
        state: w.state,
        district: w.district,
        work_category: w.work_category,
        sanction_amount: w.sanction_amount,
        work_status: w.work_status,
        risk_score: w.risk_score,
        risk_band: w.risk_band,
        confidence: w.confidence,
        confidence_band: w.confidence_band,
        primary_reason: w.primary_reason,
      }));
  }, [works, query]);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Works</h1>
        <p>Search the register by work ID, district, state, category, MP or vendor</p>
      </div>

      <input
        className="input"
        type="search"
        placeholder="Search works…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setVisible(PAGE_SIZE);
        }}
        aria-label="Search works"
      />

      <p className="muted" style={{ fontSize: 13, margin: 0 }}>
        {rows.length.toLocaleString("en-IN")} matching works
      </p>

      <section className="card" style={{ padding: 0 }}>
        <QueueTable
          rows={rows.slice(0, visible)}
          emptyTitle="No works match that search"
          emptyBody="Try a district, state or category name."
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
