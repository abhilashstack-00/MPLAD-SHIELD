# MPLAD-SHIELD — Risk Intelligence and Review Prioritisation for MPLADS

Reads official MPLADS exports, reconciles sanctioned works with completion and
payment records, and ranks works by how unusual they look against comparable
works — producing a prioritised list for human review.

**Detect → Explain → Prioritise → Investigate.** The system identifies unusual
patterns. Human authorities make every decision.

---

## Two data modes — know which one you are looking at

This repository can run in two modes, and confusing them is the single most
damaging mistake available here. The dashboard shows a banner on every page
naming the mode, and every payload carries `meta.data_mode`.

| | Real data | Synthetic benchmark |
|---|---|---|
| Command | `build_data.py` then `score_works.py` | `run.py` |
| Output | `outputs/` | `outputs/synthetic_benchmark/` |
| `meta.data_mode` | `official_export` | `synthetic_benchmark` |
| Records | 20,187 works from the supplied exports | 1,200 generated works |
| Purpose | Screening real works for review | Measuring detector precision and recall |

The synthetic mode exists for one reason: real MPLADS data carries no fraud
labels, so precision and recall cannot be measured on it. The benchmark plants
known irregularities so the detectors can be scored against ground truth. Its
figures describe the detectors, never real-world performance.

To check what you are looking at:

```bash
python -c "import json; print(json.load(open('outputs/scored.json'))['meta']['data_mode'])"
```

---

## Quick start — real MPLADS data

Put the five exports in `data/raw/`, all from the **same House** and ideally the
same download session so the totals reconcile:

- `Works_Sanctioned.xlsx`
- `Works_Completed.xlsx`
- `Expenditure_on_Completed_and_On-going_Works_as_on_Date.xlsx`
- `Works_Recommended.xlsx`
- `Allocated_Limit_for_Honble_MPs.xlsx`

The allocation export must match the works exports. A Lok Sabha allocation file
will not join a Rajya Sabha works register — the two describe different MPs
entirely, and the pipeline detects and reports this rather than forcing a join.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python build_data.py          # ingest and reconcile  -> data/interim/
python score_works.py         # score                 -> outputs/
python -m pytest tests/ -q     # 67 tests

cd web
npm install
npm run sync                  # copies both payloads into web/public/
npm run dev                   # http://localhost:5173
```

`openpyxl` cannot read these exports — they carry a malformed stylesheet — so
ingestion uses `python-calamine`. This is a hard requirement, not a preference.

---

## What the pipeline does

```
Works_Sanctioned.xlsx ─┐
Works_Completed.xlsx   ├─> ingest ─> validate ─> unified work-level table
Expenditure.xlsx       ┘            (quarantine)         │
Allocated_Limit.xlsx ──> MP-level context only           v
                                                    risk engine
                                                         │
                                          scored.json + work_details.json
                                                         │
                                                    React dashboard
```

**Sanctioned is the spine.** Every sanctioned work appears exactly once.
Expenditure is payment-level — 17,000 payments across 10,072 works, one work
carrying 121 — so it is aggregated to one row per work *before* joining. A
direct join would multiply works by their payment count and inflate every
downstream figure; there is an assertion that fails loudly if row count changes.

**Matching is exact.** Work IDs (`WS/MP187/2023-2024/1199`) sit inside the
`Work` column of the sanctioned and completed exports and in a dedicated column
in expenditure. On the supplied data: 100.0% of completed and 100.0% of
expenditure works resolve to a sanctioned work, with zero duplicates and zero
unmatched records.

**Nothing is dropped silently.** Four Grand Total rows were quarantined, each
logged with its source file and original row number, and shown on the Data
Quality page.

---

## The six detectors

| Indicator | What it checks | Max points alone |
|---|---|---|
| Cost deviation | Sanctioned amount against the peer median, in log space, using MAD | 55 |
| Timeline | Duration against the peer group's own median; recommendation-to-sanction lag | 30 |
| Expenditure consistency | Shortfall on completed works, missing payment records, fragmentation | 50 |
| Similarity | Character n-gram TF-IDF within a district | 45 |
| Compliance | Deterministic rules, weighted by tier | 60 |
| Multivariate | Isolation Forest + DBSCAN over scale-free features | 30 |

**A detector never runs on a field that does not exist.** It reports `skipped`
with the missing field named. Silence is not a zero — the Detectors page shows
exactly what ran and what did not.

**Peer groups cascade.** `work_type + state` → `work_type` → `category + state`
→ `state`, taking the first with at least 8 members. This matters: the scheme's
own `Work category` field is 97.3% "Normal/Others", so comparing within it puts
a road beside a classroom. The 96-value work type from the expenditure export
is far stronger, and the peer level used is shown on every work.

**Combination.** Indicators combine as independent evidence (noisy-OR) rather
than a weighted average, so a work flagrant on one dimension is not diluted by
five quiet ones. Computed in log space, which makes the score *exactly* the sum
of its indicator points — the UI asserts this on load.

---

## Risk versus confidence

They are different questions and are never merged.

**Risk indicator (0–100)** — how unusual the observed patterns are under the
configured detectors. Not a probability of fraud, not a legal finding.

**Confidence** — how much that judgement can be relied on: record completeness,
how many detectors could run, and above all peer-group strength. A work whose
only peer group was the broad category fallback carries lower confidence than
one compared against its own work type, and the reason is stated in words on
the work's page.

A high indicator with low confidence means check the record, not inspect the
work.

---

## Limitations

1. **No fraud labels exist for real MPLADS data**, so precision and recall
   cannot be measured on it. Any such figure in this repository comes from the
   synthetic benchmark and describes the detectors only.
2. **No rule threshold here is quoted from an MPLADS guideline document.** Each
   is tagged `configurable`, `heuristic`, `financial_consistency` or
   `data_quality`, and weighted accordingly. The ₹1 crore single-work ceiling is
   a prototype value and must be confirmed before real use.
3. **Two rules cannot run at all** on the supplied exports — inadmissible
   category and cost revision — because no field supports them. They report
   `not_evaluated`, never "passed".
4. **`district` is inferred** from the IDA text. Its meaning requires
   confirmation; the raw IDA string is always kept alongside.
5. **`Work Status` is a workflow stage, not progress.** Only 919 works ever read
   "Work Completed" while 10,232 appear in the completed export. The completed
   file is authoritative.
6. **The allocation file is cumulative** over an MP's tenure (≈₹15.4 crore
   average), not the annual ₹5 crore entitlement.
7. **Similar descriptions are not confirmed duplicates.** They are candidates
   for verification, shown side by side for a human to judge.
8. **No live government integration.** Nothing here connects to any MPLADS API.

---

## Layout

```
mplad_shield/
  ingest/        readers, normalise, validate, build_dataset, settings
  risk/          config, features, detectors, pipeline   (V2 — real data)
  config.py features.py detectors.py models.py scoring.py evaluate.py
  data_gen.py    synthetic generator                     (V1 — benchmark only)
build_data.py    ingest the exports
score_works.py   score them
run.py           synthetic benchmark
web/             React dashboard (8 pages)
data/raw/        put the exports here (git-ignored)
outputs/         real payload
```

## Tests

```bash
python -m pytest tests/ -q          # 67 tests
python -m pytest tests/test_ingest.py -q   # 23 — reading, parsing, matching
python -m pytest tests/test_risk.py -q     # 25 — detectors, scoring, export
python -m pytest tests/test_engine.py -q   # 19 — synthetic benchmark
```

The ingestion and risk suites build miniature workbooks shaped like the real
exports — title row, headers on row 2, IDs inside descriptions, a Grand Total
row — so they test the parsing rather than depending on the data being present.
One test runs against the real files when they are in `data/raw/` and is skipped
otherwise.

The properties worth knowing are asserted, not assumed: a detector missing its
field reports `skipped` and never `0.0`; the score decomposes exactly into the
points shown; a weak peer group lowers confidence; and no output wording claims
fraud.

## Further reading

- `VIVA.md` — questions, honest answers, demo flow, figures to memorise
- `AUDIT.md` — dataset profile and detector compatibility
- `UPGRADE_PLAN.md` — what remains
