// frontend/src/lib/csv.ts
//
// Minimal RFC 4180 CSV writer. Hand-rolled on purpose: a spreadsheet export is
// a few lines of escaping, and pulling in a dependency for it isn't worth the
// bundle.

/**
 * Quotes a single cell if it needs it: contains a comma, quote, CR or LF, or
 * has leading/trailing whitespace that would otherwise be lost.
 */
function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = String(value);
  if (/[",\r\n]/.test(s) || s !== s.trim()) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/** Builds CSV text from a header row and body rows. */
export function toCsv(headers: string[], rows: unknown[][]): string {
  const lines = [headers.map(cell).join(",")];
  for (const row of rows) lines.push(row.map(cell).join(","));
  // CRLF + trailing newline: what Excel expects, and it keeps the last row intact.
  return lines.join("\r\n") + "\r\n";
}

/**
 * Triggers a browser download of `content`. The object URL is revoked on the
 * next tick -- revoking synchronously can cancel the download in some browsers.
 */
export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}