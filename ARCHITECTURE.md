# ARCHITECTURE.md

How MPLAD-SHIELD fits together — current state, target state, and the contract
between the two halves.

---

## 0. What exists today

| Component | Status |
|---|---|
| Python ingestion of four eSAKSHI exports | **Built**, 100% reconciliation |
| Unified work-level dataset (20,187 works) | **Built** |
| Six detectors, ten tiered rules | **Built** |
| Scoring with exact decomposition | **Built**, verified |
| Stakeholder rollups, trends, early warning | **Built** |
| Reviewer briefings | **Built**, 5,100 generated |
| React dashboard, eleven pages | **Built**, TypeScript strict |
| Reviewer workflow (browser-local) | **Built** — records verdicts locally; submits nowhere |
| CSV export from every table view | **Built** |
| Automated tests | **Built**, 67 passing |
| Express API, PostgreSQL, PostGIS, auth | **Not built** — see §6 |

## 1. Shape of the system

Two halves that meet at a file.

```
  REGISTER                 ENGINE (Python)                UI (React)
  ────────                 ───────────────                ──────────
  MPLADS portal            features.py                    Dashboard
  export / CSV    ──────>  detectors.py     ──────>       Priority queue
  or synthetic             models.py        scored.json   Projects
  generator                scoring.py                     Risk analysis
                           pipeline.py                    Project detail
```

The engine is a **batch job**, not a service. It reads a register, scores every
work, writes `outputs/scored.json`, and exits. The UI reads that file and never
calls a model.

## 2. Why batch, not live inference

This is a deliberate constraint and agents should not "fix" it.

- **Demo safety.** Nothing can break mid-presentation because a Python process
  died or a request timed out. The numbers on screen were computed before anyone
  walked into the room.
- **Reproducibility.** Same register, same seed, identical scores. Figures quoted
  on a slide stay true.
- **Correctness.** Peer comparison, duplicate detection and DBSCAN are all
  *population* operations — they need the whole register, not one row. Scoring a
  single project in isolation is not meaningfully possible.
- **Cost.** Scoring 50,000 works takes under two minutes. Re-running on register
  refresh is cheaper and simpler than keeping a model warm.

Per-request inference would buy nothing and cost all four.

## 3. Engine internals

```
register (DataFrame)
   │
   ├─ features.build()          peer groups, robust z-scores, delay ratio,
   │                            expenditure gap, agency share, completeness
   │
   ├─ detectors                 cost_deviation · delay · expenditure_mismatch
   │                            duplicate (TF-IDF char n-grams + haversine)
   │                            compliance (deterministic rule engine)
   │
   ├─ models.MultivariateDetector
   │      RobustScaler → IsolationForest → rank transform → top 15% only
   │                   → DBSCAN (noise = corroborating vote)
   │                   → SHAP TreeExplainer (optional, degrades gracefully)
   │
   ├─ scoring.score()           noisy-OR in log space → 0–100
   │                            exact per-indicator decomposition
   │                            explanations, confidence, bands
   │
   ├─ scoring.priority_queue()  ranked shortlist
   ├─ scoring.agency_rollup()   Project → Agency → District
   ├─ evaluate.evaluate()       ROC-AUC, AP, precision/recall @ k
   │
   └─ pipeline.export()         scored.json · scored.csv ·
                                priority_queue.csv · benchmark.json
```

Detector independence is the point: each returns `[0, 1]` and knows nothing about
the others, so one can be replaced without touching the rest.

## 4. The data contract

`outputs/scored.json` is the interface between the halves. Changing its shape is
a breaking change for the UI — update `web/src/types/scored.ts` in the same
commit.

```jsonc
{
  "generated_by": "MPLAD-SHIELD risk engine",
  "disclaimer": "Risk scores indicate statistically unusual patterns …",

  "dashboard": {
    "projects_analysed": 1200,
    "potential_risks": 273,
    "pending_review": 107,
    "risk_distribution": [ { "risk_band", "projects", "mean_score",
                             "mean_confidence", "share_pct" } ],
    "flag_reasons":      [ { "reason", "projects" } ],
    "weights":           { "cost_deviation": 0.55, … },   // indicator caps
    "bands":             { "high": 70.0, "medium": 45.0 }
  },

  "priority_queue": [ { "project_id", "district", "state", "work_category",
                        "implementing_agency", "effective_cost", "risk_score",
                        "risk_band", "confidence", "primary_reason",
                        "review_status" } ],

  "agencies": [ { "district", "implementing_agency", "works", "total_cost",
                  "mean_risk", "high_risk_works", "high_risk_rate" } ],

  "projects": [ {
    // identity and register fields
    "project_id", "state", "district", "block", "latitude", "longitude",
    "constituency", "sector", "work_category", "work_description",
    "implementing_agency", "sanction_date", "expected_completion_date",
    "actual_completion_date", "sanctioned_cost", "revised_cost",
    "effective_cost", "expenditure", "physical_progress_pct", "status",

    // derived context
    "peer_median_cost", "peer_cost_percentile", "peer_size", "cost_robust_z",
    "overrun_days", "expected_duration_days", "expenditure_ratio_pct",
    "progress_gap_pct", "cost_escalation_pct", "duplicate_match_id",
    "compliance_reasons", "agency_work_share",
    "isolation_forest_score", "dbscan_is_noise",

    // result
    "risk_score", "risk_band", "confidence", "primary_reason",
    "review_status", "assessment",
    "points_cost_deviation", "points_delay", "points_expenditure_mismatch",
    "points_duplicate", "points_compliance", "points_multivariate",

    "explanation": [ { "indicator", "points", "share_pct", "detail" } ]
  } ],

  "benchmark": { "roc_auc", "average_precision", "at_k", "by_anomaly_type", … }
}
```

**Invariant:** the six `points_*` fields sum to `risk_score` within 0.15. The UI
may rely on this.

**Note:** `explanation` holds only indicators contributing ≥ 3 points, capped at
the top three — so its points may sum to less than the score. Use the `points_*`
fields for the full bar, `explanation` for the written reasons.

## 5. Frontend

```
web/src/
  types/scored.ts       generated from the contract above — single source of truth
  data/loadScored.ts    fetch + parse + validate scored.json once, cache in context
  pages/                Dashboard · Queue · Projects · RiskAnalysis · ProjectDetail
  components/           StatCard · RiskBadge · ScoreDisplay · PointsBreakdown
                        ConfidenceMeter · QueueTable · FilterChip · PeerComparison
  lib/format.ts         formatINR, formatPct, formatDate — no inline formatting
```

State: the whole scored payload lives in one React context, loaded once. Filtering
and search are client-side over that array — at register scale (tens of thousands
of rows) this is fast and removes an entire class of loading states. Server-side
paging arrives with the API in §6.

## 6. Target architecture — NOT BUILT

> **Status: design proposal.** Nothing in this section exists in the codebase.
> There is no Express server, no PostgreSQL database, no PostGIS extension and
> no authentication. The schema and endpoints below are a plan to be revised,
> not a description of running software. They are written down so the work has
> a starting point, and flagged so nobody mistakes a sketch for a system.


```
┌──────────────┐   HTTPS    ┌──────────────┐        ┌────────────────────┐
│  React UI    │ ─────────> │ Node/Express │ ─────> │ PostgreSQL+PostGIS │
└──────────────┘   REST     └──────────────┘  SQL   └────────────────────┘
                                   ▲                          ▲
                                   │ reads scores             │ writes scores
                                   │                          │
                            ┌──────────────────────────────────┐
                            │  Python engine (scheduled batch) │
                            └──────────────────────────────────┘
```

The engine still does not sit in the request path. It runs on a schedule or on
register refresh, writes to the database, and Express serves what it finds.

### Schema sketch — proposed, not implemented

```sql
projects        project_id PK, state, district, block, geom GEOGRAPHY(POINT),
                constituency, sector, work_category, work_description,
                implementing_agency, sanction_date, expected_completion_date,
                actual_completion_date, sanctioned_cost, revised_cost,
                expenditure, physical_progress_pct, status, ingested_at

scoring_runs    run_id PK, started_at, register_hash, engine_version,
                config_snapshot JSONB        -- reproducibility

scores          run_id FK, project_id FK, risk_score, risk_band, confidence,
                primary_reason, PRIMARY KEY (run_id, project_id)

score_points    run_id, project_id, indicator, points, detail TEXT

reviews         review_id PK, project_id FK, reviewer_id, status, outcome,
                note, reviewed_at        -- becomes labels for tuning
```

`config_snapshot` matters: a score is only defensible if the thresholds that
produced it can be recovered months later.

PostGIS earns its place in duplicate detection — `ST_DWithin` replaces the
in-memory haversine once the register outgrows a single process.

### API surface — proposed, not implemented

```
GET  /api/dashboard                    headline counts, distribution, reasons
GET  /api/queue?limit=&band=           ranked review queue
GET  /api/projects?q=&district=&page=  searchable register
GET  /api/projects/:id                 full detail with points and explanation
GET  /api/agencies?district=           agency rollup
POST /api/reviews                      record a reviewer outcome
GET  /api/runs/:id/config              the thresholds behind a given score
```

## 7. Migration path

| Stage | Change | Everything else stays |
|---|---|---|
| Now | Engine + JSON + UI | — |
| Real data | `pipeline.load(csv)` replaces the generator | Detectors, UI, contract |
| Persistence | Export writes to Postgres instead of JSON | Detectors, scoring |
| API | Express serves the tables; UI swaps fetch target | Engine, components |
| Scale | PostGIS spatial joins; server-side paging | Contract shape |

Each step is independently shippable. Nothing requires a rewrite, because the
contract in §4 is the only coupling between the halves.

## 8. Operational notes

- **Reproducibility.** Record the seed and `engine_version` behind any figure
  used in a presentation or report.
- **Re-scoring cadence.** On register refresh. Scores are snapshots of a run, not
  live values — the UI shows the run timestamp.
- **Failure modes.** A missing SHAP install degrades explanations, not scoring. A
  malformed register fails at `pipeline.load` with the missing columns named.
  Missing fields lower confidence rather than becoming zeros.
- **Privacy.** The register concerns works and agencies, not individuals. No
  personal data is scored, and none should be added.
