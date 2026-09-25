# MPLAD-SHIELD V2 — Audit

Produced by inspecting the supplied `mplad_shield_engine_ver_2.zip` and the four
MPLADS exports. Every number below came from running code against the actual
files; nothing here is estimated.

---

## Part 1 — Existing project audit

The uploaded ZIP is unmodified from the version previously delivered. 4,814
lines across 39 source files.

| Component | Existing implementation | Purpose | Verdict |
|---|---|---|---|
| Frontend | React 18 + Vite + TS, 5 pages, 9 components, no UI library | Dashboard | **Keep**, extend |
| Python engine | 8 modules, ~1,300 lines | Risk detection | **Reuse core**, rework detectors |
| Data pipeline | `data_gen.py` synthetic generator only | Data source | **Replace** with real ingestion |
| Feature engine | `features.py`, peer groups + robust z | Feature prep | **Modify** for real fields |
| Detectors | 6 detectors in `detectors.py` | Signals | **2 keep, 2 rework, 2 rebuild** |
| Scoring | Noisy-OR in log space | Risk indicator | **Keep** — sound and decomposable |
| Models | IsolationForest + DBSCAN + SHAP | Multivariate | **Keep**, fewer features |
| Tests | 14 tests, synthetic only | Quality | **Expand** to ingestion |
| Output | `scored.json`, 47 fields | Frontend input | **Extend** with provenance |

### How the existing engine works, in plain language

1. **Feature building.** Each work is placed in a *peer group* — same work
   category, same state. Its cost is compared to the group's median using
   median-absolute-deviation rather than standard deviation, so one inflated
   project cannot distort the yardstick it is measured against.
2. **Six detectors** each return a number between 0 and 1. Cost deviation, delay,
   expenditure-vs-progress mismatch, duplicate similarity, compliance rules, and
   a multivariate model.
3. **Combination.** Scores combine as independent evidence (noisy-OR) rather
   than a weighted average, computed in log space so the total decomposes
   exactly back into per-detector points.
4. **Confidence** is separate: 70% record completeness, 30% peer-group adequacy.
5. **Explanations** name the top three contributing indicators with real figures.
6. **Export** writes `scored.json`, which the React UI reads as a static file.

### Assumptions and limitations in the existing code

| Assumption | Location | Official? | Action |
|---|---|---|---|
| `SINGLE_WORK_CEILING` ₹1 crore | `config.py` | **Unverified** | Make configurable, relabel as prototype rule |
| `MAX_COST_ESCALATION_PCT` 10% | `config.py` | **Unverified** | **Dead** — no revised-cost field exists |
| `EXPECTED_DURATION_DAYS` (12 categories) | `config.py` | **Invented** | Replace with empirical medians from data |
| `INADMISSIBLE_CATEGORIES` (6 entries) | `config.py` | Plausible but unverified | **Dead** — real data has only 4 categories, none inadmissible |
| `ANNUAL_ENTITLEMENT` ₹5 crore | `config.py` | Scheme-level, but | Allocation file is cumulative, not annual — see §2.4 |
| Indicator caps (0.40–0.75) | `config.py` | Design choice | Document and expose |
| Reference date `2026-09-01` | `features.py` | Technical | **Make configurable as-of date** |
| Peer group = category × state | `features.py` | Design choice | **Weak on real data** — see §4.1 |
| `min_peer_group` = 8 | `config.py` | Design choice | Keep, expose |
| Labelled anomalies | `data_gen.py` | **Synthetic** | Never present as real validation |

---

## Part 2 — Dataset audit

All four files: single sheet named `Sheet1`, title in row 0, headers in row 1.

**Blocking issue found first:** `openpyxl` cannot open any of these files. The
exports carry a malformed stylesheet (`TypeError: Fill() takes no arguments`),
which also breaks `pandas.read_excel` at its default engine. The ingestion layer
must use `engine="calamine"` (`python-calamine`). This is a hard requirement,
not a preference.

### 2.1 Works Sanctioned — 20,188 rows × 12 columns

The spine of the dataset. 20,187 usable rows after the stray total row.

| Column | Non-null | Unique | Note |
|---|---|---|---|
| Work | 100% | 20,187 | Work ID + description concatenated |
| Work category | 100% | **4** | 97.3% "Normal/Others" — see §4.1 |
| State | 100% | 29 | |
| IDA | 100% | 582 | District parseable from prefix |
| Hon'ble MP | 100% | 180 | Name + tenure in brackets |
| Work description | 99.9% | 17,615 | 2,924 rows share a description |
| Recommended date | 100% | 963 | Clean |
| Sanction Date | 100% | 829 | Clean |
| Sanction Amount (₹) | 100% | 4,916 | min ₹10,000 · median ₹5,00,000 · max ₹7.35 cr |
| Work Status | 100% | **7** | Workflow stages, not progress |

Work Status values: Physical Inspection (10,325), Sanction (4,108), Vendor
Identification (2,603), Work partially Completed (2,131), Work Completed (919),
Time Estimation (101) — **plus one row whose status is `17629503056.99`**, a
grand-total figure that has leaked into a data column.

### 2.2 Works Completed — 10,233 rows × 11 columns

Adds `Completion Date` (100%) and `Amount Disbursed` (99.8%). An `Image` column
is present but holds only the literal string "Images" or "N/A" — it carries no
usable information.

### 2.3 Expenditure — 17,001 rows × 11 columns

**Payment-level, not work-level.** 17,000 payments across 10,072 distinct works:
mean 1.69 payments per work, median 1, **maximum 121**.

Two findings worth attention:

- The `Work` column here has only **96 unique values** — it is a work-type
  taxonomy, not a description. This is a far richer category field than the
  4-value `Work category` in the sanctioned file, and materially improves peer
  grouping for the works it covers.
- `Fund Disbursed Amount` maximum is **₹12,76,14,18,099 (₹1,276 crore)** against
  a maximum sanction of ₹7.35 crore. This is either a total row or a data error
  and must be quarantined by validation, not scored.

Also present: `Vendor Name` (5,518 distinct) and `Payment Status` (Payment
Success 16,391 / In-Progress 609).

### 2.4 Allocated Limit — 544 rows × 5 columns

543 MPs plus an explicit **`Grand Total` row of ₹83,42,97,42,527.91** that must
be removed. Per-MP allocations average ≈₹15.4 crore, and the first row is
₹19.03 crore — consistent with **cumulative tenure allocation, not the annual
₹5 crore entitlement**. The existing `ANNUAL_ENTITLEMENT` constant must not be
compared against this column.

This file has no work ID and joins only at MP/constituency level.

---

## Part 3 — Work-ID matching report

IDs follow `WS/MP<num>/<FY>/<serial>`. In the sanctioned and completed files the
ID is prefixed to the description inside the `Work` column; the expenditure file
has a dedicated `Work ID` column.

| Metric | Count |
|---|---:|
| Sanctioned records | 20,187 |
| Completed records | 10,232 |
| Expenditure payment records | 17,000 |
| IDs extracted from `Work` (sanctioned) | 20,187 (100.0%) |
| IDs extracted from `Work` (completed) | 10,232 (100.0%) |
| Distinct works in expenditure | 10,072 |
| **Completed ∩ Sanctioned** | **10,232 (100.0%)** |
| **Expenditure ∩ Sanctioned** | **10,072 (100.0%)** |
| Expenditure ∩ Completed | 5,963 |
| Duplicate IDs within sanctioned | 0 |
| Duplicate IDs within completed | 0 |
| Unmatched / ambiguous | **0** |

This is the single best news in the audit: the three work-level files reconcile
perfectly. No fuzzy matching is required, and no records are stranded.

Date fields all parse with `%d-%b-%Y`, there are no future dates against an
as-of date of 24 Sep 2026, and **zero** works have a sanction date earlier than
their recommendation date.

---

## Part 4 — Detector compatibility

### 4.1 Cost deviation — **runs, but peer grouping must change**

The current peer group is category × state. On real data this collapses:
**97.3% of works are "Normal/Others"**, so the category dimension carries almost
no information and the peer group degenerates into state-level comparison across
unrelated work types.

Three usable replacements, in order of preference:

1. `Expenditure.Work` (96 work types) where available — covers ~50% of works.
2. District (parsed from `IDA`, 579 distinct) × state.
3. Description-derived pseudo-categories via TF-IDF clustering — must be
   labelled a prototype heuristic, not an official classification.

### 4.2 Delay — **runs with honest relabelling**

Computable: recommendation→sanction lag (all works), sanction→completion
(10,232), sanction→as-of age for works still open. The invented
`EXPECTED_DURATION_DAYS` table must go; replace with **empirical medians per
peer group derived from the data itself**, clearly labelled as a screening
baseline rather than an official deadline.

### 4.3 Expenditure — **must be rebuilt**

The current detector compares money drawn against `physical_progress_pct`.
**That field does not exist in any supplied file.** The detector cannot run as
written and must not be faked.

Rebuild around what does exist: total disbursed ÷ sanctioned, over-disbursement,
payment count and concentration, payments recorded against works not marked
complete, and payment dates preceding the sanction date.

### 4.4 Duplicate similarity — **runs, minus geography**

No latitude or longitude exists anywhere, so the haversine radius filter is
dead. Block on state + district + category instead. Text similarity is viable
and there is real signal: **2,924 sanctioned rows share an exact description**
with another row.

One caveat: some descriptions are mojibake — Devanagari has been lost in export
(`P.C.C ??? ?? ???????`). These must be excluded from similarity rather than
matched to each other on their question marks.

### 4.5 Compliance rules — **4 of 6 are dead**

| Rule | Status on real data |
|---|---|
| Inadmissible category | **Dead** — only 4 categories, none inadmissible |
| Cost escalation > 10% | **Dead** — no revised-cost field |
| Expenditure > sanctioned | **Runs** after aggregation |
| Ceiling breach | Runs — 106 works exceed ₹1 cr, but the threshold is unverified |
| Progress vs status | **Dead** — no progress field |
| Agency concentration | Runs — reframe as neutral observation |

New rules the data actually supports: payment before sanction date, completed
status without completion date, duplicate exact descriptions, single payment
exceeding total sanction.

### 4.6 Multivariate — **runs on a reduced feature set**

Of eight current features, `progress_gap_pct`, `physical_progress_pct` and
`cost_escalation_pct` are unavailable. Replacements: recommendation→sanction
lag, payment count, expenditure ratio, vendor concentration, district work share.

---

## Part 5 — Data dictionary

| Field | Source | Meaning | Type | Missing | Used by |
|---|---|---|---|---|---|
| `work_id` | Derived from `Work` / `Work ID` | Unique work reference | String | 0 | Joining |
| `work_description` | Sanctioned | Free-text description | Text | 0.1% | Similarity |
| `work_category` | Sanctioned | 4-value scheme category | Category | <0.1% | Peer group (weak) |
| `work_type` | Expenditure `Work` | 96-value work taxonomy | Category | 50% of works | Peer group (preferred) |
| `state` | All | State | String | 0 | Peer group |
| `district` | Parsed from `IDA` prefix | District name — **meaning requires confirmation** | String | 0 | Peer group, concentration |
| `ida_raw` | All | Implementing District Authority string | String | 0 | Provenance |
| `mp_name` | All | MP name + tenure | String | 0 | Rollup |
| `sanction_amount` | Sanctioned | Amount sanctioned | Numeric | 0 | Cost analysis |
| `recommended_date` | Sanctioned | Date MP recommended | Date | 0 | Timeline |
| `sanction_date` | Sanctioned | Date sanctioned | Date | 0 | Timeline |
| `work_status` | Sanctioned | Workflow stage, **not** progress | Category | 0 | Rules |
| `completion_date` | Completed | Completion date | Date | n/a | Duration |
| `amount_disbursed` | Completed | Amount at completion | Numeric | 0.2% | Cross-check |
| `total_expenditure` | Expenditure, summed | Sum of payments | Numeric | 50% of works | Expenditure ratio |
| `payment_count` | Expenditure, counted | Payments per work | Integer | 50% | Concentration |
| `vendor_name` | Expenditure | Payee — **meaning requires confirmation** | Text | 50% | Relationship analysis |
| `allocated_amount` | Allocation | **Cumulative** tenure allocation | Numeric | 0 | MP-level context only |

Fields the pipeline must **never** fabricate, because no source provides them:
physical progress, revised cost, latitude/longitude, block, sector, vendor
identity beyond the payee string.

---

## Part 6 — Claims that must be corrected

| Current claim | Reality | Fix |
|---|---|---|
| "ROC-AUC 0.977, precision@50 0.74" | Measured on synthetic data with planted anomalies | Confine to a clearly labelled synthetic benchmark page; never quote beside real-data screens |
| "Detects duplicate projects" | Detects textually similar descriptions | Relabel "potentially similar works requiring verification" |
| "Compliance rule violation" | Thresholds unverified against the guideline edition | Split into verified / configurable / heuristic tiers |
| "PostgreSQL + PostGIS, Express API" | Not implemented | Label as future architecture in ARCHITECTURE.md |
| Expenditure-progress mismatch | No progress field exists | Remove the detector; replace with expenditure consistency |
| Expected durations by category | Invented in config | Replace with empirical baselines, labelled as such |
