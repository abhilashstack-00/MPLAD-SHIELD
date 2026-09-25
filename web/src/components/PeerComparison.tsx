import { formatINR, ordinal } from "../lib/format";
import type { Work } from "../types/scored";

/**
 * Where this work sits among comparable works.
 *
 * The peer level is shown, not hidden. Half the register falls back to a broad
 * category group where the scheme's own category is 97% "Normal/Others", and a
 * cost finding built on that deserves to be read more sceptically than one
 * built on same-work-type comparison.
 */
export function PeerComparison({ work }: { work: Work }) {
  const { peer_median_cost, peer_cost_percentile, peer_size, sanction_amount, peer_level } = work;

  if (peer_median_cost === null || peer_cost_percentile === null) {
    return (
      <p className="muted">
        No adequate peer group was available, so no cost comparison was attempted
        for this work.
      </p>
    );
  }

  return (
    <div>
      <div className="muted" style={{ fontSize: 13 }}>
        Compared against {peer_size ?? 0} works grouped by <strong>{peer_level}</strong>
      </div>
      <div className="peer">
        <span className="peer__median" style={{ left: "50%" }} />
        <span
          className="peer__mark"
          style={{ left: `${Math.min(Math.max(peer_cost_percentile, 1), 99)}%` }}
        />
      </div>
      <div className="peer__caption">
        <span>Peer median {formatINR(peer_median_cost)}</span>
        <span>
          This work {formatINR(sanction_amount)} · {ordinal(peer_cost_percentile)} percentile
        </span>
      </div>
    </div>
  );
}
