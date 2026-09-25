import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatCard } from "../components/StatCard";
import { EmptyState } from "../components/EmptyState";
import { ModeBanner } from "../components/ModeBanner";
import { ExportButton } from "../components/ExportButton";
import { useScored } from "../data/loadScored";
import { formatINRCompact, formatNumber, formatPct } from "../lib/format";
import type { RollupRow } from "../types/scored";

type Audience = "ministry" | "state" | "district" | "mp" | "agency";

const AUDIENCES: { key: Audience; label: string; blurb: string }[] = [
  { key: "ministry", label: "Ministry", blurb: "National position across every state" },
  { key: "state", label: "State Nodal Authority", blurb: "Districts within a state" },
  { key: "district", label: "District Authority", blurb: "Districts ranked by flagged works" },
  { key: "mp", label: "Member of Parliament", blurb: "Works recommended, by MP" },
  { key: "agency", label: "Payee concentration", blurb: "Context only, never a finding" },
];

/**
 * The same evidence at the level each audience acts on.
 *
 * Deliberately one page with a scope selector rather than four dashboards.
 * The columns are identical at every level, because a Ministry user comparing
 * states and a district officer comparing payees are asking the same question
 * and should not have to learn two tables to ask it.
 */
export function Stakeholders() {
  const { national, rollups, fund_utilisation, meta } = useScored();
  const [audience, setAudience] = useState<Audience>("ministry");
  const [state, setState] = useState<string>("");
  const navigate = useNavigate();

  const states = useMemo(
    () => rollups.state.map((r) => r.state).filter(Boolean).sort() as string[],
    [rollups.state]
  );

  const { rows, nameOf, heading } = useMemo(() => {
    switch (audience) {
      case "ministry":
        return {
          rows: rollups.state,
          nameOf: (r: RollupRow) => r.state ?? "—",
          heading: "State",
        };
      case "state":
        return {
          rows: rollups.district.filter((r) => !state || r.state === state),
          nameOf: (r: RollupRow) => `${r.district ?? "—"}`,
          heading: "District",
        };
      case "district":
        return {
          rows: rollups.district,
          nameOf: (r: RollupRow) => `${r.district ?? "—"}, ${r.state ?? "—"}`,
          heading: "District",
        };
      case "mp":
        return {
          rows: rollups.mp,
          nameOf: (r: RollupRow) => `${r.mp_name ?? "—"}`,
          heading: "Member of Parliament",
        };
      default:
        return {
          rows: rollups.vendor,
          nameOf: (r: RollupRow) => `${r.primary_vendor ?? "—"}`,
          heading: "Payee",
        };
    }
  }, [audience, rollups, state]);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Stakeholder views</h1>
        <p>The same screening evidence, aggregated to the level each authority acts on.</p>
      </div>

      <ModeBanner
        mode={meta.data_mode}
        source={meta.data_source}
        asOf={meta.as_of_date}
        engine={meta.engine_version}
      />

      <div className="grid grid--3">
        <StatCard
          label="Works screened nationally"
          value={formatNumber(national.works)}
          sub={`${national.states} states · ${national.districts} districts · ${national.mps} MPs`}
        />
        <StatCard
          label="Sanctioned / disbursed"
          value={formatINRCompact(national.sanctioned)}
          sub={`${formatINRCompact(national.expenditure)} recorded — ${formatPct(
            national.utilisation_pct ?? 0, 1
          )} utilisation`}
        />
        <StatCard
          label="High priority nationally"
          value={formatNumber(national.high_risk)}
          sub={`${formatNumber(national.flagged)} flagged · ${formatPct(
            national.completion_pct, 1
          )} completed`}
          to="/queue"
        />
      </div>

      <section className="card">
        <h2 className="card__title">Scope</h2>
        <div className="chips">
          {AUDIENCES.map((option) => (
            <button
              key={option.key}
              type="button"
              className={`chip${audience === option.key ? " chip--on" : ""}`}
              aria-pressed={audience === option.key}
              onClick={() => setAudience(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="muted" style={{ marginBottom: 0, fontSize: 13 }}>
          {AUDIENCES.find((a) => a.key === audience)?.blurb}
        </p>

        {audience === "state" && (
          <div style={{ marginTop: "var(--space-4)" }}>
            <select
              className="input"
              value={state}
              onChange={(e) => setState(e.target.value)}
              aria-label="Select a state"
            >
              <option value="">All states</option>
              {states.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        )}
      </section>

      {audience === "agency" && (
        <p className="disclaimer">
          A payee associated with many works is not by itself a finding. Concentration
          has ordinary explanations — a single empanelled contractor in a small
          district, for instance. Shown as context for a reviewer, and it feeds no score.
        </p>
      )}

      {audience === "mp" && <p className="disclaimer">{fund_utilisation.note}</p>}

      {audience === "mp" && fund_utilisation.allocation_joined && (
        <section className="card" style={{ padding: 0 }}>
          <div className="table-wrap" style={{ maxHeight: 520, overflowY: "auto" }}>
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">Member of Parliament</th>
                  <th scope="col">State</th>
                  <th scope="col" className="num">Works</th>
                  <th scope="col" className="num">Allocated</th>
                  <th scope="col" className="num">Sanctioned</th>
                  <th scope="col" className="num">Spent</th>
                  <th scope="col" className="num">High priority</th>
                </tr>
              </thead>
              <tbody>
                {fund_utilisation.rows.slice(0, 200).map((row) => (
                  <tr key={`${row.mp_name}-${row.state}`} style={{ cursor: "default" }}>
                    <td><strong>{row.mp_name ?? "—"}</strong></td>
                    <td>{row.state ?? "—"}</td>
                    <td className="num">{formatNumber(row.works)}</td>
                    <td className="num">
                      {formatINRCompact(row.allocated_amount_cumulative ?? null)}
                    </td>
                    <td className="num">
                      {formatPct(row.sanctioned_pct_of_allocation ?? 0, 1)}
                    </td>
                    <td className="num score-cell">
                      {formatPct(row.spent_pct_of_allocation ?? 0, 1)}
                    </td>
                    <td className="num">{formatNumber(row.high_risk)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <div className="chips">
        <ExportButton rows={rows} name={`rollup_${audience}`} />
      </div>

      <section className="card" style={{ padding: 0 }}>
        {rows.length === 0 ? (
          <EmptyState title="No records at this level" />
        ) : (
          <div className="table-wrap" style={{ maxHeight: 620, overflowY: "auto" }}>
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">{heading}</th>
                  <th scope="col" className="num">Works</th>
                  <th scope="col" className="num">Sanctioned</th>
                  <th scope="col" className="num">Utilisation</th>
                  <th scope="col" className="num">Completed</th>
                  <th scope="col" className="num">High priority</th>
                  <th scope="col" className="num">High-risk rate</th>
                  <th scope="col" className="num">Mean indicator</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 300).map((row, index) => (
                  <tr
                    key={`${nameOf(row)}-${index}`}
                    onClick={() =>
                      navigate(`/works?q=${encodeURIComponent(String(nameOf(row).split(",")[0]))}`)
                    }
                  >
                    <td><strong>{nameOf(row)}</strong></td>
                    <td className="num">{formatNumber(row.works)}</td>
                    <td className="num">{formatINRCompact(row.sanctioned)}</td>
                    <td className="num">{formatPct(row.utilisation_pct ?? 0, 1)}</td>
                    <td className="num">{formatPct(row.completion_pct ?? 0, 1)}</td>
                    <td className="num score-cell">{formatNumber(row.high_risk)}</td>
                    <td className="num">{formatPct(row.high_risk_pct ?? 0, 1)}</td>
                    <td className="num">{(row.mean_risk ?? 0).toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="muted" style={{ fontSize: 13 }}>
        Utilisation is recorded disbursement against sanctioned amount. Where a work
        carries no payment record it contributes to the denominator only, so a low
        figure can reflect incomplete records rather than unspent money.
      </p>
    </div>
  );
}
