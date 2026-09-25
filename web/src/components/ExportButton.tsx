import { downloadCsv, stampedName } from "../lib/csv";

/**
 * Exports exactly the rows currently on screen, filters included.
 *
 * Exporting the unfiltered set would quietly contradict what the reviewer is
 * looking at, and a list that disagrees with the screen it came from is worse
 * than no list.
 */
export function ExportButton({
  rows,
  columns,
  name,
  label = "Export CSV",
}: {
  rows: readonly object[];
  columns?: string[];
  name: string;
  label?: string;
}) {
  return (
    <button
      type="button"
      className="chip"
      disabled={rows.length === 0}
      onClick={() => downloadCsv(stampedName(name), rows as Record<string, unknown>[], columns)}
      title={`Download ${rows.length.toLocaleString("en-IN")} rows as shown`}
    >
      {label} ({rows.length.toLocaleString("en-IN")})
    </button>
  );
}
