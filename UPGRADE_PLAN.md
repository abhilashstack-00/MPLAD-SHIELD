# MPLAD-SHIELD V2 — Upgrade Plan

Staged so that each stage leaves the project runnable and demonstrable. Nothing
is deleted; the synthetic generator is retained as a labelled benchmark mode.

Read `AUDIT.md` first — this plan follows directly from what the real files
turned out to contain.

---

## Guiding constraints

1. **A detector never runs on a field that does not exist.** It reports
   `status: "skipped"` with the missing field named. Silence is not a zero.
2. **Synthetic and official results never share a screen** without a mode label.
3. **Nothing invented.** No progress percentages, no coordinates, no revised
   costs, no agency names beyond what the export carries.
4. **Every claim traceable** to a source file, sheet and row.

---

## Stage 1 — Ingestion layer (new)

**New files:** `mplad_shield/ingest/__init__.py`, `readers.py`, `normalise.py`,
`workid.py`, `validate.py`, `build_dataset.py`

**Why:** the project currently has no way to read a real file. Everything
downstream depends on this.

| Step | Detail |
|---|---|
| Read | `engine="calamine"` — openpyxl fails on these exports (malformed stylesheet) |
| Header | Row 1, not row 0; row 0 is the report title |
| Quarantine | Drop the `Grand Total` row in Allocation; drop the sanctioned row whose Work Status is `17629503056.99`; quarantine the ₹1,276 crore payment. Every removal logged with its source row number |
| Parse | Amounts via a rupee-aware numeric parser; dates via `%d-%b-%Y` |
| Derive | `work_id` by regex from `Work`; `district` from the `IDA` prefix |
| Preserve | `source_file`, `source_sheet`, `source_row`, `ingested_at` on every record |

**Risk:** district parsing from `IDA` is an inference. Mitigation — keep
`ida_raw` alongside and mark the derived field "meaning requires confirmation".

**Acceptance:** 20,187 + 10,232 + 17,000 + 543 records ingested; 100% ID
extraction; matching report reproduces the counts in AUDIT.md Part 3.

---

## Stage 2 — Unified work-level dataset (new)

**New file:** `mplad_shield/ingest/build_dataset.py`

Sanctioned is the spine. Completed left-joins 1:1. Expenditure aggregates to
work level **before** joining — 17,000 payments collapse to 10,072 works with
`total_expenditure`, `payment_count`, `distinct_vendors`, `first/last_payment_date`.

Aggregating before the join is the one step that must not be got wrong: joining
payment rows directly would multiply every sanctioned work by its payment count
and silently inflate every downstream count.

**Acceptance:** exactly 20,187 rows out; `total_expenditure` populated for
10,072; `completion_date` for 10,232; no row multiplication.

---

## Stage 3 — Rework features and detectors

**Modified:** `features.py`, `detectors.py`, `config.py`, `models.py`

| Detector | Change |
|---|---|
| Cost deviation | Peer group becomes a **cascade**: work-type (96 values) → district × state → state × category, taking the first with ≥ `min_peer_group` members. Peer definition and size exported per work |
| Timeline | Empirical median duration per peer group replaces the invented table. Configurable as-of date. Relabelled a screening baseline |
| Expenditure consistency | **Replaces** expenditure-progress mismatch. Ratio, over-disbursement, payment concentration, payments on non-complete works, payment-before-sanction |
| Similarity | Geography filter removed; blocking on state + district + category. Mojibake descriptions excluded. Output relabelled "potentially similar" |
| Rules | Split into `verified` / `configurable` / `heuristic` / `data_quality`. Dead rules removed, not left silently returning zero |
| Multivariate | Feature set rebuilt from available fields |

Every detector returns the agreed envelope: `status`, `signal`, `confidence`,
`reason`, `evidence`, `data_quality`, `requires_review`.

**Risk:** changing peer groups changes every score, invalidating figures already
quoted. Mitigation — re-run and republish the benchmark in the same commit.

---

## Stage 4 — Scoring, confidence and governance

**Modified:** `scoring.py`, `pipeline.py`

The noisy-OR combiner is kept — it is sound and decomposes exactly. Changes are
around it: skipped detectors contribute no evidence and are named in the output;
confidence incorporates detector availability and match quality; scores round to
whole numbers; every record carries a `data_mode` of `official_export` or
`synthetic_benchmark`, plus config version and as-of date.

---

## Stage 5 — Frontend

**Modified:** existing pages. **New:** `DataQuality.tsx`, `SimilarWorks.tsx`,
`Methodology.tsx`, `Detectors.tsx`

The existing five pages and nine components are kept and extended. Additions:
a persistent data-source banner, a data-quality page showing ingestion and
matching statistics, a similar-works explorer showing both records side by side,
a detector page showing what ran and what was skipped, and a methodology page
written for the viva.

Charts stay as inline SVG — no new dependency.

---

## Stage 6 — Tests and documentation

Ingestion tests (header detection, calamine fallback, total-row removal, rupee
and date parsing), matching tests (extraction, unmatched, duplicates),
aggregation tests (no row multiplication), detector-skip tests (a missing field
produces `skipped`, never `0.0`), and scoring invariants.

Docs: README rewritten for real data; data dictionary; corrected ARCHITECTURE
with implemented-vs-planned split; `VIVA.md` with honest answers to the twelve
challenging questions.

---

## Sequencing

Stages 1–2 first and alone: until real records flow end to end, everything after
is speculation. Stage 3 is the largest and should be reviewed detector by
detector. Stages 5–6 only once numbers are stable.

## What will not be built

Backend API, PostgreSQL/PostGIS, authentication, graph exploration, embeddings.
The audit shows no data need for them, and they cannot be demonstrated in five
minutes. They stay labelled as future architecture.
