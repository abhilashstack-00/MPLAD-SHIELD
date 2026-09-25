# PRD — MPLAD-SHIELD

**Problem Statement ID:** 26102 · **Team:** Vigilantes · **SIH 2026**

---

## 1. The problem

MPLADS sanctions thousands of small works across every district each year. Cost
overruns, stalled works, duplicate sanctions and guideline breaches are all
recorded — project by project, in a register that grows faster than anyone can
read it.

The gap is not recording. It is **prioritisation**. A district officer with
capacity to inspect fifty works has no way to know which fifty. Existing systems
monitor each project in isolation, so a pattern visible only across projects — the
same work sanctioned twice in neighbouring villages, one agency holding an odd
share of a district's money — is invisible by construction.

## 2. What we are building

A risk-scoring layer that reads the MPLADS register and returns a **ranked
review queue**: every work scored 0–100, with the reasons for that score stated
in terms an officer can act on, and a confidence level saying how much of the
record was actually observed.

### What this is not

This is the most important boundary in the product, and it governs wording
everywhere:

- It does **not** determine fraud, irregularity, or wrongdoing.
- It does **not** take action against a project, an agency, or an official.
- It does **not** replace audit or inspection.

A high score means *statistically unusual relative to comparable works*. It is a
prompt to look, nothing more. Every screen and every export carries this framing.

## 3. Users

| User | What they need | What they get |
|---|---|---|
| District authority | To know which works to inspect this month | A ranked shortlist, not a register dump |
| Auditor / inspection team | To spend limited visit capacity well | The flagged minority, with a specific question per visit |
| MPLADS monitoring team | To catch problems during execution | Patterns surfaced while works are still correctable |
| Policy stakeholder | Aggregate view across constituencies | Risk trends by district, agency, category |

## 4. Core concepts

Every part of the system is built on these. Agents and contributors should treat
the definitions as fixed.

**Peer group.** A work is compared only against the same work category in the
same state. A ₹40 lakh community hall is unremarkable; a ₹40 lakh toilet block is
not. No global averages are used anywhere.

**Indicator.** One dimension of risk, valued 0–1. There are six:

| Indicator | Meaning | Max points |
|---|---|---|
| `cost_deviation` | Sanctioned cost above the peer median (robust z-score) | 55 |
| `delay` | Overrun past the category's expected duration | 45 |
| `expenditure_mismatch` | Funds drawn ahead of physical progress | 60 |
| `duplicate` | Text and location similarity to a nearby work | 65 |
| `compliance` | Deterministic MPLADS guideline checks | 75 |
| `multivariate` | Isolation Forest + DBSCAN over the feature matrix | 40 |

**Risk score.** Indicators combine as independent evidence, not a weighted
average, so one flagrant dimension can carry a work on its own. The combination
is exactly decomposable: the per-indicator points always sum to the score.

**Bands.** High ≥ 70 · Medium ≥ 45 · Low < 45. Only High enters the review queue
by default.

**Confidence.** Separate from risk: 70% record completeness, 30% peer-group
adequacy. A high score on a half-empty record must be visibly marked as such —
never silently averaged into the ranking.

## 5. Scope

### Built and verified in this repository

- Python risk engine: six detectors, rule engine, Isolation Forest, DBSCAN, SHAP
  attribution, peer grouping, confidence scoring
- Labelled synthetic benchmark with measured precision and recall
- `scored.json` export contract, and its TypeScript types in
  `web/src/types/scored.ts`
- 14 tests, including the score-decomposition invariant

### Built elsewhere, not yet in this repository

- Prototype V1 UI: dashboard, priority queue, projects list with search, risk
  analysis with filters, project detail. Currently reads its own demo data and
  must be repointed at `scored.json`.

### Designed but not built

- Express API, PostgreSQL + PostGIS persistence, reviewer actions. The schema and
  endpoints in ARCHITECTURE.md §6 are a proposal to revise, not a specification
  already implemented.

### Next (V3)

- Real MPLADS register ingestion via `pipeline.load`, replacing the generator
- Reviewer actions: mark reviewed, record outcome, add a note
- Outcome feedback — reviewer verdicts become labels that tune thresholds

### Later (V4 / V5)

- Express API and PostgreSQL + PostGIS persistence
- Scheduled re-scoring on register refresh
- Multi-district and state-level rollout, role-based access

### Explicitly out of scope

- Any automated enforcement, penalty, or blocking of a sanction
- Naming or scoring individuals
- Predicting fraud, or any output phrased as a probability of fraud
- Real-time per-request model inference (see ARCHITECTURE.md for why)

## 6. Functional requirements

### 6.1 Dashboard

- Headline counts: projects analysed, potential risks, pending review
- Risk distribution across the three bands with share percentages
- "Why projects are flagged" — counts by primary reason
- Every count traceable to the underlying filtered list on click

### 6.2 Priority review queue

- Ranked by `risk_score` descending, tie-broken by `confidence` descending —
  between two equal scores, the better-documented work is the better use of a
  site visit
- Columns: project ID, district, category, cost, score, band, confidence,
  primary reason, review status
- Row click opens project detail

### 6.3 Projects

- Full register, searchable by project ID, district, agency, sector, category
- Sortable by score, cost, sanction date
- Must remain usable at 50,000+ rows (virtualised list, server-side paging in V5)

### 6.4 Risk analysis

- Filter by band and by indicator (show every work where `duplicate` is material)
- Peer-group context: where a work sits in its category's cost distribution
- Agency rollup: Project → Agency → District, with mean risk and high-risk rate

### 6.5 Project detail

This screen is the product. It must show:

- Score, band, confidence
- **Points contributed by each indicator**, summing to the score — not just the
  top reason
- A specific sentence per contributing indicator, with the actual numbers
  ("97% of funds drawn against 44% physical progress"), never a bare label
- Peer comparison: this work's cost against its peer median and percentile
- The matched project ID where a duplicate was detected
- Any guideline rules violated, quoted
- The standing assessment line, verbatim

## 7. Non-functional requirements

- **Explainability is not optional.** No score may be displayed without its
  breakdown reachable in one click. A screen that shows a number with no path to
  its reasons is a bug.
- **Human-in-the-loop.** The system ranks; officers decide. No screen may present
  a conclusion.
- **Reproducibility.** The same register and seed must produce identical scores.
  Demo figures must be quotable and stable.
- **Degrade honestly.** Missing fields lower confidence; they never silently
  become zeros that look like findings.
- **Performance.** Scoring 50,000 works completes in under two minutes on a
  laptop. The UI renders the queue in under one second.

## 8. Success metrics

Measured on the labelled benchmark; see README for the caveat that these are
synthetic.

| Metric | Current | Target |
|---|---|---|
| ROC-AUC | 0.977 | ≥ 0.95 |
| Precision @ top 50 | 0.74 | ≥ 0.70 |
| Recall @ top 100 | 0.80 | ≥ 0.85 |
| Lift over base rate @ 50 | ~10× | ≥ 8× |

Product metric once deployed: share of inspections that find something, before
and after. That is the number that decides whether this was worth building.

## 9. Known risks

| Risk | Mitigation |
|---|---|
| Benchmark is synthetic; real data will score differently | Stated plainly in README and in any presentation; re-benchmark on first real register |
| False positives erode trust | Works are ranked, not accused; reasons and peer context shown; confidence surfaced |
| Thresholds in `config.py` are illustrative | Marked CONFIGURABLE; must be checked against the current guideline edition before real use |
| Duplicate and delay detectors are the weakest (recall 0.59 / 0.53) | Named as the next tuning priority; do not over-tune on synthetic data |
| Scores could be read as accusations | Fixed wording throughout; see AGENTS.md for the banned vocabulary |
