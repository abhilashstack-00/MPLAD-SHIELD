import { INDICATOR_LABELS, type IndicatorKey } from "../types/scored";

/** One colour per indicator, used everywhere that indicator appears. */
export const INDICATOR_COLOR: Record<IndicatorKey, string> = {
  cost_deviation: "var(--ind-cost_deviation)",
  timeline: "var(--ind-delay)",
  expenditure_consistency: "var(--ind-expenditure_mismatch)",
  similarity: "var(--ind-duplicate)",
  compliance: "var(--ind-compliance)",
  multivariate: "var(--ind-multivariate)",
};

const KEY_BY_LABEL = new Map<string, IndicatorKey>(
  (Object.keys(INDICATOR_LABELS) as IndicatorKey[]).map((k) => [INDICATOR_LABELS[k], k])
);

export function colorForLabel(label: string): string {
  const key = KEY_BY_LABEL.get(label);
  return key ? INDICATOR_COLOR[key] : "var(--border-strong)";
}

/** Rule tiers carry different authority; the UI must not present them alike. */
export const RULE_TIER_LABEL: Record<string, string> = {
  verified: "Verified rule",
  financial_consistency: "Financial consistency",
  configurable: "Configurable threshold",
  heuristic: "Analytical heuristic",
  data_quality: "Data quality",
};
