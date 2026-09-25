# VIVA.md — MPLAD-SHIELD

Answers grounded in what is actually built. Where something is not implemented,
say so — a judge who catches an overstatement stops believing the rest.

The sentence to have ready for almost anything:

> The system identifies statistically unusual patterns and ranks works for
> human review. It does not establish fraud, and there are no fraud labels in
> MPLADS data to train on.

---

## Part 1 — Domain basics

**What problem are you solving?**
MPLADS sanctions thousands of small works per district each year. Cost
overruns, stalled works, duplicate sanctions and gaps in records all exist in
the register, but they are recorded project by project and never ranked. A
district officer with capacity to inspect fifty works has no way to know which
fifty. We turn a flat register into a ranked review queue with stated reasons.

**What is MPLADS?**
The Members of Parliament Local Area Development Scheme. Each MP recommends
development works in their constituency; the district authority sanctions and
implements them through implementing agencies. The annual entitlement is ₹5
crore per MP.

**What is eSAKSHI?**
The MPLADS workflow application (MPLADS-eSAKSHI, run by MoSPI) through which
MPs raise recommendations, authorities sanction works and payments are
recorded. Our data comes from its report exports — four Excel files.

**Who does what?**
The MP recommends works and approves fund-enhancement requests but does not
sanction or spend. The District Authority (IDA) sanctions and administers. The
implementing agency executes and draws payments. Our system serves the
authority and audit side, not the MP.

**Is this connected to a live government system?**
No. We work from Excel exports that were supplied to us. Nothing in the
application calls any government API, and we bypass no authentication.

---

## Part 2 — Technical

**Why Python and React?**
Python for the data work — pandas and scikit-learn are where the anomaly
detection lives. React for a dashboard a reviewer can navigate. They are
deliberately separate: the engine writes a JSON file and the UI reads it, so
nothing can break mid-demo because a process died.

**How do you combine the four files?**
Sanctioned is the spine — every sanctioned work appears exactly once.
Completed joins one-to-one. Expenditure is **payment-level**: 17,000 payments
across 10,072 works, one work carrying 121. It is aggregated to one row per
work *before* joining, otherwise a work would be multiplied by its payment
count and every downstream figure would inflate. There is a test asserting the
row count is unchanged.

**How do you match work IDs?**
IDs look like `WS/MP187/2023-2024/1199`. In the sanctioned and completed
exports they are prefixed to the description inside the `Work` column; the
expenditure export has a dedicated column. One regex handles both. On our data:
**100.0% of completed and 100.0% of expenditure works match a sanctioned work,
with zero duplicates and zero unmatched.** No fuzzy matching is needed.

**How does cost anomaly detection work?**
Each work is compared against a peer group, never a national average. We use
the median and median-absolute-deviation rather than mean and standard
deviation, because one inflated sanction would otherwise inflate the very
yardstick it is measured against. Comparison is in log space since amounts span
₹10,000 to ₹7.35 crore. Only the upper tail scores — a cheap work is a saving
or a data problem, not what we are looking for.

**How do you choose peer groups?** *(a strong question to invite)*
A cascade: work type + state → work type → category + state → state, taking the
first with at least 8 members. This matters because the scheme's own
`Work category` field is **97.3% "Normal/Others"** — comparing within it puts a
road beside a classroom. The expenditure export's `Work` column turned out to
hold ~96 work types, which is a far better grouping. About half the register
gets it; the rest falls back, and that fallback **lowers confidence** rather
than being hidden.

**How does expenditure analysis work?**
Payments are summed per work and compared to the sanctioned amount. Note the
direction: in our data **nothing is disbursed above sanction**, so overspend
carries no signal. What does is under-disbursement on a completed work, a
completed work with no payment record at all (4,269 of them), and payment
fragmentation.

**How does duplicate detection work?**
Character n-gram TF-IDF within a district. Character n-grams because real
duplicates differ by a transliteration or typo — "Instalation" against
"Installation" — which word matching misses. We label results **potentially
similar works requiring verification**, never confirmed duplicates, and show
both records side by side for a human to judge.

**Why unsupervised learning? Why not supervised?**
Because there are no labels. No MPLADS export marks a work as fraudulent, so
there is nothing honest to train a classifier on. Isolation Forest and DBSCAN
find works that are unremarkable on every single dimension but implausible in
combination. Claiming supervised fraud detection would require a labelled
dataset we do not have.

**What is the difference between an anomaly and fraud?**
An anomaly is a statistical statement: this work differs from comparable works.
Fraud is a legal finding requiring intent and evidence. A legitimately
expensive hospital is an anomaly and not fraud. Everything we produce is the
first kind, and the wording throughout the application says so.

**How is the risk score calculated?**
Six detectors each return 0 to 1. They combine as **independent evidence**
(noisy-OR) rather than a weighted average — under an average, a work flagrant
on one dimension scores low because the other five are quiet, which is backwards.
The combination runs in log space, which makes the score **exactly** the sum of
its indicator points, so "72/100" decomposes into the points each detector
contributed. There is a test asserting it, and the UI checks it on load.

**How do you handle missing data?**
A detector without its required field reports `skipped` with the field named —
never `0.0`, because a zero is indistinguishable from "checked and found
nothing". Two of our ten rules cannot run at all on this data and say so. The
Detectors page shows what ran and what did not.

**How do you validate the model?**
On a labelled synthetic benchmark, because that is the only place ground truth
exists: ROC-AUC 0.977, precision 0.74 at the top 50, roughly 10× lift over the
base rate. **Those numbers describe the detectors, not performance on real
MPLADS data**, and the application labels the two data modes separately so they
can never be confused.

**What are the limitations?**
See Part 4. Have three ready at all times.

---

## Part 3 — The hard questions

**1. "How do you know an anomaly is fraud?"**
We don't, and we don't claim to. The output is a ranked list of works that
differ from comparable works, with the reasons stated. Confirming anything
requires a site visit and records a reviewer has and we don't. The value is
that an officer inspecting fifty works inspects a better fifty.

**2. "Where did your fraud labels come from?"**
There are none in MPLADS data. That is precisely why the engine is
unsupervised. The only labels anywhere in this project are in a synthetic
register we generate ourselves to measure the detectors, and it is kept in a
separate output directory with its own data-mode banner.

**3. "Why should we trust your risk score?"**
Don't trust the number — read the breakdown. Every score decomposes exactly
into per-detector points, each with the actual figures: "97% of funds drawn
against 44% physical progress", "₹1.90 crore against a peer median of ₹2.10
lakh across 924 comparable works". If you disagree with a reason, you can see
and reject it. A score you cannot interrogate would deserve no trust.

**4. "Why can't the existing MPLADS dashboard do this?"**
eSAKSHI records and monitors works individually and does it well. What it does
not do is compare across works — nothing there tells you this sanction is 40×
its peer median, or that a near-identical work was sanctioned in the next
block. That cross-project view is the gap we identified and the thing we built.

**5. "What if a project is legitimately expensive?"**
Then it should be flagged and cleared in minutes. We compare within peer
groups precisely to reduce this, and show the peer median, percentile and
group size so a reviewer can dismiss it immediately. The cost of a false
positive is a few minutes; the cost of a missed pattern is larger.

**6. "What if the dataset contains incorrect information?"**
It does, and we found some. One sanctioned row had a grand total sitting in its
Work Status column; the expenditure file contained a ₹1,276 crore payment
against a maximum sanction of ₹7.35 crore. Both are quarantined with their
source row numbers and shown on the Data Quality page. We also score data
completeness per work and factor it into confidence.

**7. "What about false positives?"**
Expected and designed for. Works are ranked, not accused. High band is 3.4% of
the register — 681 of 20,187 — which is a queue a district team can work
through. Every flag carries its reasons and peer context so it can be dismissed
quickly, and confidence flags works whose evidence is thin.

**8. "Why AI instead of simple rules?"**
We use both. Deterministic rules catch what rules catch, and they are separated
into tiers by how much authority they carry. But a rule cannot catch a work
that is mildly high on cost, mildly slow, and mildly odd on payments — no
single threshold trips, yet the combination is implausible. That is what the
unsupervised layer is for.

**9. "What happens when data is missing?"**
The detector skips and says which field was missing. Confidence drops.
Nothing is imputed into a finding. A high score with low confidence means
check the record before inspecting the work.

**10. "Is this connected to a live government system?"**
No. Four supplied Excel exports, processed locally. No API, no scraping, no
authentication bypassed.

**11. "What is genuinely implemented, and what is planned?"**
Implemented: ingestion and reconciliation of the four exports, the unified
work-level dataset, six detectors, the rule engine, scoring with exact
decomposition, an eight-page dashboard, and 67 tests.
Not implemented: the Express API, PostgreSQL and PostGIS persistence, reviewer
workflow actions that write back, and authentication. Those are documented as
future architecture, not claimed as existing.

**12. "How would this scale to national data?"**
The engine is O(n) except similarity, which is blocked by district so it never
compares every pair. 20,187 works score in seconds. At national scale the
changes needed are database persistence instead of JSON, server-side paging in
the UI, and PostGIS for spatial blocking — all designed for, none built.

---

## Part 4 — Limitations, stated first

Volunteer at least three before being asked.

1. **The benchmark is synthetic.** Real MPLADS data has no fraud labels, so
   precision and recall cannot be measured on it.
2. **No threshold here is an official MPLADS rule.** The ₹1 crore ceiling is a
   prototype value tagged `configurable` and must be verified.
3. **Two rules cannot run** on the supplied exports and report
   `not_evaluated` rather than "passed".
4. **`district` is inferred** from the IDA text; meaning requires confirmation.
5. **`Work Status` is a workflow stage, not progress** — only 919 works read
   "Work Completed" while 10,232 appear in the completed export.
6. **The allocation file is cumulative** over an MP's tenure, not annual.
7. **Similar is not duplicate.** Two works can legitimately share a description
   across wards.
8. **No physical progress, revised cost or coordinates exist** in the data, so
   three detectors from our original design were removed rather than faked.

---

## Part 5 — Demo flow (3–5 minutes)

1. **Overview** — 20,187 works ingested, banner naming the source. State the
   problem in one line.
2. **Data quality** — 100% match rates, four quarantined rows. Thirty seconds,
   and it buys credibility for everything after.
3. **Priority queue** — 681 High out of 20,187.
4. **Open one work** — the Deoria high-mast lighting at ₹1.90 crore against a
   ₹2.10 lakh peer median.
5. **Points breakdown** — show that the numbers add to the score.
6. **Similar works** — the near-identical pair, side by side. Say "potentially
   similar, requires verification".
7. **Detectors page** — what ran, what was skipped, and why.
8. **Close on limitations.** Say the benchmark is synthetic before anyone asks.

Run entirely from local files. Never depend on a live site.

**If something breaks:** the data is static JSON, so say what the screen would
have shown and move on. Do not debug in front of judges.

---

## Part 6 — Numbers worth memorising

| Figure | Value |
|---|---|
| Works ingested | 20,187 |
| Completed / with payments | 10,232 / 10,072 |
| Payment records aggregated | 17,000 |
| Match rate | 100.0% |
| Rows quarantined | 4 |
| High band | 681 (3.4%) |
| Works with a strong peer group | 8,732 |
| "Normal/Others" share of category | 97.3% |
| Benchmark ROC-AUC *(synthetic)* | 0.977 |
| Tests | 67 |
