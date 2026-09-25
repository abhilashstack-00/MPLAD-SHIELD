/**
 * Display formatting. Every number the UI renders passes through here.
 *
 * Inlining `toLocaleString` at call sites is how a product ends up showing
 * Rs 12,418,938 on one screen and Rs 1,24,18,938 on another. Indian grouping is
 * not the default for most locales, so it has to be deliberate and central.
 */

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const INR_COMPACT = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Rupees in Indian grouping: 1,24,18,938 — not 12,418,938. */
export function formatINR(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return INR.format(value);
}

/** Short form for dense table cells: ₹1.2Cr, ₹15.8L. */
export function formatINRCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return INR_COMPACT.format(value);
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/**
 * Ordinal suffix for percentile text ("32nd percentile"). Handles the teens,
 * which the naive last-digit rule gets wrong.
 */
export function ordinal(value: number): string {
  const n = Math.round(value);
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}
