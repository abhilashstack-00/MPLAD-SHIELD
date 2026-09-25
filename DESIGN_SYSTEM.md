# DESIGN_SYSTEM.md

Visual and interaction standards for the MPLAD-SHIELD interface.

The design has one job: make a reviewer trust a number enough to act on it, and
make the reasoning behind that number impossible to miss. Every rule below serves
that, which is why the colour section has as much to say about *not* relying on
colour as about the palette itself.

---

## 1. Colour

### Base

| Token | Hex | Use |
|---|---|---|
| `--surface` | `#FFFFFF` | Cards, tables, panels |
| `--surface-sunken` | `#F4F7FB` | Page background |
| `--surface-raised` | `#FAFCFE` | Nested panels inside cards |
| `--border` | `#D8E2EC` | Card and table borders |
| `--border-strong` | `#B6C6D6` | Input borders, dividers under headers |
| `--nav` | `#16243F` | Sidebar background |
| `--nav-active` | `#2563EB` | Active sidebar item |
| `--nav-text` | `#C4D0E0` | Sidebar labels |

### Text

| Token | Hex | Use |
|---|---|---|
| `--text` | `#1A2332` | Body |
| `--text-muted` | `#5A6B7C` | Captions, secondary labels |
| `--text-heading` | `#1F497D` | Section headings |
| `--text-inverse` | `#FFFFFF` | On `--nav` and on filled badges |

### Risk bands

These three are semantic. Never use them decoratively — a red element that is
not communicating risk trains the reviewer to ignore red.

| Token | Hex | Band | Text on it |
|---|---|---|---|
| `--risk-high` | `#C62828` | ≥ 70 | `#FFFFFF` |
| `--risk-high-bg` | `#FDECEC` | Row/badge background | `#8E1F1F` |
| `--risk-medium` | `#B26A00` | 45–69 | `#FFFFFF` |
| `--risk-medium-bg` | `#FDF3E4` | Row/badge background | `#7A4800` |
| `--risk-low` | `#2E7D4F` | < 45 | `#FFFFFF` |
| `--risk-low-bg` | `#EAF5EE` | Row/badge background | `#1E5334` |

### Indicator accents

Each of the six indicators keeps one colour everywhere it appears — the points
bar on project detail, the filter chip on risk analysis, the dashboard reason
chart. Consistency here is what lets a reviewer learn the vocabulary.

| Indicator | Hex |
|---|---|
| Cost deviation | `#5B6ABF` |
| Delay | `#E8890C` |
| Expenditure-progress mismatch | `#2E7D8F` |
| Duplicate / similar project | `#6741C7` |
| Compliance rule violation | `#B23A48` |
| Unusual overall pattern | `#4A7C59` |

### Confidence

Confidence is not risk and must never borrow the risk palette. Use a neutral
ramp: `#D8E2EC` (low) → `#7E93A8` (medium) → `#3D5A73` (high).

---

## 2. Typography

System stack, no web fonts — the interface must render identically offline
during a demo.

```css
--font: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
--font-mono: "SF Mono", "Cascadia Mono", Consolas, monospace;
```

| Token | Size / line-height | Weight | Use |
|---|---|---|---|
| `--text-display` | 32 / 38 | 700 | Risk score on project detail |
| `--text-h1` | 24 / 30 | 700 | Page titles |
| `--text-h2` | 18 / 24 | 600 | Card headings |
| `--text-h3` | 15 / 20 | 600 | Sub-sections, table headers |
| `--text-body` | 14 / 21 | 400 | Body, table cells |
| `--text-small` | 12.5 / 18 | 400 | Captions, helper text |
| `--text-micro` | 11 / 15 | 600 | Badge labels, uppercase tags |

**Numerals.** Every figure — scores, costs, percentages, points — uses
`font-variant-numeric: tabular-nums`. Columns of numbers that don't align are
harder to scan, and scanning a queue is the primary activity in this product.

**Currency.** Indian grouping, always: `₹1,24,18,938`. A shared
`formatINR()` helper owns this; never inline `toLocaleString`.

---

## 3. Spacing

4px base. Use the scale, not arbitrary values.

`--space-1: 4px` · `--space-2: 8px` · `--space-3: 12px` · `--space-4: 16px` ·
`--space-5: 24px` · `--space-6: 32px` · `--space-8: 48px`

- Card padding: `--space-5`
- Gap between cards: `--space-4`
- Table cell padding: `--space-3` vertical, `--space-4` horizontal
- Page gutter: `--space-6`

## 4. Radius, elevation, motion

```css
--radius-sm: 4px;    /* badges, chips */
--radius-md: 8px;    /* cards, inputs, buttons */
--radius-lg: 12px;   /* modals, the score panel */

--shadow-card: 0 1px 2px rgba(22, 36, 63, 0.06);
--shadow-raised: 0 4px 12px rgba(22, 36, 63, 0.10);
--shadow-modal: 0 16px 40px rgba(22, 36, 63, 0.18);

--motion-fast: 120ms ease-out;   /* hover, focus */
--motion-base: 200ms ease-out;   /* expand, drawer */
```

No animation on score values, band changes, or anything numeric. A figure that
counts up reads as a game, and this product's credibility depends on not feeling
like one. Respect `prefers-reduced-motion` by disabling all transitions.

---

## 5. Components

### StatCard
Dashboard headline figure. Icon, label, value, optional sublabel. Value at
`--text-display`. Whole card is a link to the filtered list behind the number —
a count a reviewer cannot drill into is decoration.

### RiskBadge
Band label. Filled background from `--risk-*-bg`, text from the paired dark
colour, `--text-micro`, uppercase. **Always contains the word** (`HIGH`,
`MEDIUM`, `LOW`) — never colour alone.

### ScoreDisplay
The 0–100 figure with its band. Number at `--text-display`, band badge beside it,
confidence meter beneath. Never shown without the points breakdown reachable in
the same view.

### PointsBreakdown
The heart of the product. A horizontal stacked bar segmented by indicator
accent, then one row per contributing indicator:

```
Compliance rule violation      34.5 pts  (37.8%)
Sanctioned cost exceeds the single-work ceiling of ₹1,00,00,000
```

Rules: segments in descending points order; indicators contributing under 3
points are collapsed into "Other"; the rows must visibly sum to the score; the
detail sentence carries real numbers, never a bare category name.

### ConfidenceMeter
Three-segment bar using the neutral ramp, with the value and a one-line reason
("2 of 7 key fields missing"). Placed adjacent to the score, never in a tooltip —
if a score rests on a thin record, the reviewer must see that without hovering.

### QueueTable
Ranked list. Sticky header, zebra-free (band tint on the score cell carries the
signal), row hover `--surface-sunken`, whole row clickable. Virtualise past 200
rows. Column order matches PRD §6.2.

### FilterChip
Toggleable, on risk analysis. Indicator chips use the indicator accent as a left
marker plus the label text. Selected state is a filled background, not just a
border — border-only selection is invisible at a glance.

### PeerComparison
A distribution strip for the work's category showing the peer median and this
work's position. Annotate with the percentile. This is what converts "cost is
high" into a defensible statement.

### EmptyState
Icon, one line of what would appear here, one action. Required on: empty queue
("No projects currently meet the High-risk threshold"), no search results, and
a register with no scores yet.

### DisclaimerBanner
Persistent on project detail. Neutral styling, not a warning colour — it is a
standing statement of scope, not an alert. Text is fixed; see AGENTS.md §2.2.

---

## 6. Accessibility

Non-negotiable, and several items are direct consequences of what this product
claims to be.

- **Colour is never the only carrier of meaning.** Every band shows its word,
  every indicator shows its label. A reviewer with colour-vision deficiency must
  lose nothing.
- **Contrast:** 4.5:1 for body text, 3:1 for large text and UI borders. The band
  foreground/background pairs in §1 are chosen to clear this.
- **Focus:** 2px `--nav-active` outline with 2px offset on every interactive
  element. Never `outline: none` without a replacement.
- **Keyboard:** the whole queue is operable without a mouse — arrow keys move
  between rows, Enter opens, Escape closes the detail view.
- **Tables:** real `<table>` markup with `<th scope>`. Score cells carry an
  `aria-label` spelling out the band ("82 out of 100, high risk").
- **Targets:** minimum 40×40px.

## 7. Tone in the interface

- State findings in the reviewer's terms: "97% of funds drawn against 44%
  physical progress", not "expenditure anomaly detected".
- Prefer the concrete number to the adjective. "246 days past the 120-day norm"
  beats "significantly delayed".
- Never address the reader as an investigator or the project as a suspect.
- Sentence case for headings and buttons. No exclamation marks anywhere.
- Buttons name the action: "Open project", "Mark reviewed" — not "Submit", "OK".
