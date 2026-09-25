/**
 * Client-side CSV export.
 *
 * Reviewers work offline, circulate lists by email and annotate in Excel. A
 * queue that can only be read on screen stops being useful the moment an
 * officer leaves their desk, so every table view exports exactly what is on
 * screen -- filters applied, nothing hidden.
 */

function escapeCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  // Quote anything containing a delimiter, quote or newline, doubling
  // internal quotes as the CSV convention requires.
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(rows: Record<string, unknown>[], columns?: string[]): string {
  if (rows.length === 0) return "";
  const headers = columns ?? Object.keys(rows[0]);
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => escapeCell(row[h])).join(","));
  }
  return lines.join("\r\n");
}

export function downloadCsv(
  filename: string,
  rows: Record<string, unknown>[],
  columns?: string[]
): void {
  const csv = toCsv(rows, columns);
  if (!csv) return;
  // BOM so Excel opens UTF-8 correctly, which matters for rupee signs and
  // transliterated place names.
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/** Timestamped filename so successive exports do not overwrite each other. */
export function stampedName(prefix: string): string {
  const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
  return `mplad-shield_${prefix}_${stamp}.csv`;
}
