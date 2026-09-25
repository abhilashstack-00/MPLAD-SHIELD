/**
 * Types for `scored.json` as produced by the V2 engine.
 *
 * Single source of truth for the payload shape. The engine writes this file
 * from official MPLADS exports; the UI reads it as a static asset and computes
 * no risk value of its own.
 */

export type IndicatorKey =
  | "cost_deviation"
  | "timeline"
  | "expenditure_consistency"
  | "similarity"
  | "compliance"
  | "multivariate";

export const INDICATOR_LABELS: Record<IndicatorKey, string> = {
  cost_deviation: "Cost deviation from peers",
  timeline: "Timeline indicator",
  expenditure_consistency: "Expenditure consistency",
  similarity: "Potentially similar work",
  compliance: "Rule-based indicator",
  multivariate: "Unusual combination of indicators",
};

export const INDICATOR_KEYS = Object.keys(INDICATOR_LABELS) as IndicatorKey[];

export type RiskBand = "High" | "Medium" | "Low";
export type ConfidenceBand = "High" | "Medium" | "Low";

type Num = number | null;
type Str = string | null;

export interface Explanation {
  indicator: string;
  points: number;
  share_pct: number;
  detail: string;
}

export interface Work {
  work_id: string;
  work_description: Str;
  work_category: Str;
  /** The 96-value taxonomy from the expenditure export; null where absent. */
  work_type: Str;
  state: Str;
  /** Inferred from the IDA text — meaning requires confirmation. */
  district: Str;
  ida_raw: Str;
  mp_name: Str;

  sanction_amount: Num;
  recommended_date: Str;
  sanction_date: Str;
  completion_date: Str;
  work_status: Str;
  is_completed: boolean;

  total_expenditure: Num;
  expenditure_ratio: Num;
  payment_count: Num;
  max_single_payment: Num;
  distinct_vendors: Num;
  primary_vendor: Str;
  first_payment_date: Str;
  last_payment_date: Str;

  peer_key: Str;
  peer_level: Str;
  peer_size: Num;
  peer_median_cost: Num;
  peer_cost_percentile: Num;
  cost_robust_z: Num;
  peer_strength: Num;

  days_recommendation_to_sanction: Num;
  days_sanction_to_reference: Num;
  peer_median_duration: Num;
  age_basis: Str;

  similar_work_id: Str;
  similarity_score: Num;
  recommended_amount: Num;
  recommended_on: Str;
  sanction_uplift_pct: Num;
  rule_reasons: Str;
  identical_description_count: Num;
  vendor_district_share: Num;

  data_completeness: Num;
  detectors_evaluated: Num;

  risk_score: number;
  risk_band: RiskBand;
  confidence: number;
  confidence_band: ConfidenceBand;
  confidence_reason: Str;
  primary_reason: string;
  /** Plain-language summary composed from computed evidence. */
  briefing?: Str;
  /** Fixed scope statement. Render verbatim. */
  assessment: string;

  source_file: Str;
  source_row: Num;

  points_cost_deviation: number;
  points_timeline: number;
  points_expenditure_consistency: number;
  points_similarity: number;
  points_compliance: number;
  points_multivariate: number;

  explanation: Explanation[];
}

export interface QueueRow {
  work_id: string;
  work_description: Str;
  state: Str;
  district: Str;
  work_category: Str;
  sanction_amount: Num;
  work_status: Str;
  risk_score: number;
  risk_band: RiskBand;
  confidence: number;
  confidence_band: ConfidenceBand;
  primary_reason: string;
}

export interface DetectorStatus {
  detector: string;
  status: "active" | "skipped";
  reason: string;
  records_evaluated: number;
  records_flagged: number;
  missing_fields: string[];
}

export interface RuleStatus {
  rule_id: string;
  name: string;
  rule_type: string;
  source: string;
  status: "evaluated" | "not_evaluated";
  records_flagged: number;
  tier_weight?: number;
  explanation: string;
}

export interface SimilarPair {
  work_id: string;
  similar_work_id: string;
  similarity_score: number;
  state: Str;
  district: Str;
  work_category: Str;
  sanction_amount: Num;
  work_description: Str;
}

export interface BandSummary {
  risk_band: RiskBand;
  works: number;
  mean_score: number;
  mean_confidence: number;
  share_pct: number;
}

export interface DataQuality {
  config: {
    as_of_date: string;
    data_mode: string;
    source_label: string;
    config_version: string;
    files: Record<string, string>;
  };
  matching: Record<string, number>;
  quarantine: { quarantine_source: string; quarantine_reason: string; rows: number }[];
  quarantined_rows: number;
  dates: Record<string, number>;
  amounts: Record<string, number | null>;
  columns: {
    dataset: string;
    column: string;
    non_null: number;
    missing: number;
    completeness_pct: number;
    distinct: number;
  }[];
  coverage: Record<string, number>;
}

export interface RollupRow {
  level: string;
  state?: Str;
  district?: Str;
  mp_name?: Str;
  primary_vendor?: Str;
  works: number;
  sanctioned: Num;
  expenditure: Num;
  completed: number;
  high_risk: number;
  flagged: number;
  mean_risk: Num;
  mean_confidence: Num;
  utilisation_pct: Num;
  completion_pct: Num;
  high_risk_pct: Num;
}

export interface NationalSummary {
  works: number;
  states: number;
  districts: number;
  mps: number;
  sanctioned: number;
  expenditure: number;
  utilisation_pct: Num;
  completed: number;
  completion_pct: number;
  high_risk: number;
  flagged: number;
}

export interface MonthlyPoint {
  month: string;
  /** "sanctioned" | "completed" | "expenditure" */
  series: string;
  count: number;
  amount: Num;
}

export interface RiskMonth {
  month: string;
  works: number;
  high_risk: number;
  high_risk_pct: Num;
}

export interface FundUtilisationRow {
  mp_name: Str;
  state: Str;
  works: number;
  sanctioned: Num;
  expenditure: Num;
  completed: number;
  high_risk: number;
  utilisation_pct: Num;
  constituency?: Str;
  allocated_amount_cumulative?: Num;
  sanctioned_pct_of_allocation?: Num;
  spent_pct_of_allocation?: Num;
  allocation_matched?: boolean;
}

export interface EarlyWarningRow {
  work_id: string;
  work_description: Str;
  state: Str;
  district: Str;
  mp_name: Str;
  sanction_amount: Num;
  sanction_date: Str;
  days_sanction_to_reference: Num;
  peer_median_duration: Num;
  days_since_last_payment: Num;
  total_expenditure: Num;
  risk_score: number;
  risk_band: RiskBand;
  confidence_band: ConfidenceBand;
  warning_reason: string;
}

export interface PipelineState {
  state: Str;
  works: number;
  value: Num;
}

export interface PipelineWork {
  work_description: Str;
  work_category: Str;
  state: Str;
  district: Str;
  mp_name: Str;
  recommended_amount: Num;
  recommended_on: Str;
}

export interface RecommendationPipeline {
  available: boolean;
  works: number;
  value: number;
  by_state: PipelineState[];
  oldest: PipelineWork[];
}

export interface ScoredPayload {
  meta: {
    generated_at: string;
    /** "official_export" or "synthetic_benchmark" — drives the mode banner. */
    data_mode: string;
    data_source: string;
    as_of_date: string;
    engine_version: string;
    config_version: string;
    source_files: string[];
    limitations: string[];
  };
  dashboard: {
    works_total: number;
    works_requiring_review: number;
    high_priority: number;
    works_completed: number;
    works_with_expenditure: number;
    total_sanctioned: number;
    total_expenditure: number;
    mean_data_completeness: number;
    risk_distribution: BandSummary[];
    flag_reasons: { reason: string; works: number }[];
    caps: Record<IndicatorKey, number>;
    bands: { high: number; medium: number };
  };
  detectors: DetectorStatus[];
  rules: RuleStatus[];
  data_quality: DataQuality;
  national: NationalSummary;
  rollups: {
    state: RollupRow[];
    district: RollupRow[];
    mp: RollupRow[];
    vendor: RollupRow[];
  };
  trends: { monthly: MonthlyPoint[]; risk_by_month: RiskMonth[] };
  fund_utilisation: {
    rows: FundUtilisationRow[];
    allocation_joined: boolean;
    match_rate_pct: number;
    note: string;
  };
  early_warning: EarlyWarningRow[];
  recommendation_pipeline: RecommendationPipeline;
  priority_queue: QueueRow[];
  similar_pairs: SimilarPair[];
  works: Work[];
}

/** Points contributed by each indicator, descending. */
export function pointsByIndicator(
  work: Work
): { key: IndicatorKey; label: string; points: number }[] {
  return INDICATOR_KEYS.map((key) => ({
    key,
    label: INDICATOR_LABELS[key],
    points: (work[`points_${key}` as keyof Work] as number) ?? 0,
  })).sort((a, b) => b.points - a.points);
}

/**
 * The engine defines the score as the sum of its rounded indicator points, so
 * this holds exactly. A payload that fails it is stale or hand-edited, and any
 * breakdown drawn from it would misrepresent how a work was scored.
 */
export function assertDecomposition(work: Work, tolerance = 0.05): boolean {
  // The startup index intentionally omits point fields; the full detail
  // payload carries them when a reviewer opens a work.
  if (!INDICATOR_KEYS.some((key) => `points_${key}` in work)) return true;
  const total = INDICATOR_KEYS.reduce(
    (sum, key) => sum + ((work[`points_${key}` as keyof Work] as number) ?? 0),
    0
  );
  return Math.abs(total - work.risk_score) <= tolerance;
}
