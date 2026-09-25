import type { RiskBand } from "../types/scored";

/**
 * Band label. The word is always present: colour alone must never carry the
 * meaning, both for colour-vision deficiency and because a reviewer scanning a
 * queue at speed reads shapes before hues.
 */
export function RiskBadge({ band }: { band: RiskBand }) {
  return <span className={`badge badge--${band}`}>{band}</span>;
}
