/** Client-side CSV export in the same column layout as the import templates (export → edit in Excel → re-import). */
export function toCsv(columns: string[], rows: object[]): string {
  const esc = (v: unknown) => {
    if (v === null || v === undefined) return "";
    const s = Array.isArray(v) ? v.join(";") : String(v);
    return /[",;\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  // BOM so Excel opens Cyrillic/Kazakh text correctly; the ARGUS importer strips it
  return "﻿" + [columns.join(","), ...rows.map((r) => columns.map((c) => esc((r as Record<string, unknown>)[c])).join(","))].join("\r\n") + "\r\n";
}

export function downloadCsv(filename: string, columns: string[], rows: object[]): void {
  const url = URL.createObjectURL(new Blob([toCsv(columns, rows)], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
