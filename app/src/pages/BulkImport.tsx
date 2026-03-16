import { useRef, useState } from "react";
import {
  validateImport,
  commitImport,
  ValidatedRow,
  ValidationSummary,
  ImportValidationResult,
} from "../api/importValidate";

const STATUS_COLOR: Record<string, string> = {
  valid: "bg-green-50 border-green-200 text-green-800",
  warning: "bg-yellow-50 border-yellow-200 text-yellow-800",
  invalid: "bg-red-50 border-red-200 text-red-800",
};

const STATUS_BADGE: Record<string, string> = {
  valid: "bg-green-100 text-green-700",
  warning: "bg-yellow-100 text-yellow-700",
  invalid: "bg-red-100 text-red-700",
};

function SummaryBar({ s }: { s: ValidationSummary }) {
  return (
    <div className="grid grid-cols-5 gap-2 mb-4">
      {[
        { label: "Total", value: s.total, color: "bg-gray-50 border-gray-200" },
        { label: "Valid", value: s.valid, color: "bg-green-50 border-green-200 text-green-700" },
        { label: "Warnings", value: s.warnings, color: "bg-yellow-50 border-yellow-200 text-yellow-700" },
        { label: "Invalid", value: s.invalid, color: "bg-red-50 border-red-200 text-red-700" },
        { label: "Duplicates", value: s.duplicates, color: "bg-orange-50 border-orange-200 text-orange-700" },
      ].map(({ label, value, color }) => (
        <div key={label} className={`rounded-lg border p-3 text-center ${color}`}>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-xs">{label}</p>
        </div>
      ))}
    </div>
  );
}

function RowCard({ row }: { row: ValidatedRow }) {
  const [open, setOpen] = useState(false);
  const n = row.normalized;
  return (
    <div className={`rounded-lg border p-3 text-sm ${STATUS_COLOR[row.status]}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className={`shrink-0 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[row.status]}`}>
            {row.status}
          </span>
          {n ? (
            <span className="truncate font-medium">{n.description}</span>
          ) : (
            <span className="truncate text-gray-500 italic">
              {String((row.raw as Record<string, unknown>).description ?? "(empty)")}
            </span>
          )}
          {n && (
            <span className="shrink-0 text-gray-500">
              {n.date} · {n.amount} {n.currency}
            </span>
          )}
        </div>
        {(row.warnings.length > 0 || row.corrections.length > 0) && (
          <button
            onClick={() => setOpen((v) => !v)}
            className="shrink-0 text-xs underline opacity-70 hover:opacity-100"
          >
            {open ? "hide" : "details"}
          </button>
        )}
      </div>

      {open && (
        <div className="mt-2 space-y-1.5">
          {row.warnings.map((w, i) => (
            <p key={i} className="text-xs flex gap-1">
              <span className="font-semibold shrink-0">⚠</span> {w}
            </p>
          ))}
          {row.corrections.map((c, i) => (
            <p key={i} className="text-xs flex gap-1">
              <span className="font-semibold shrink-0">✏</span>
              <span className="font-medium">{c.field}:</span>
              <span className="line-through opacity-60">{c.original}</span>
              <span>→ {c.corrected}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

type FilterType = "all" | "valid" | "warning" | "invalid";

export default function BulkImport() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<ImportValidationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [committed, setCommitted] = useState<{ inserted: number; duplicates: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterType>("all");

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setCommitted(null);
    try {
      const res = await validateImport(file);
      setResult(res);
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!result) return;
    const validRows = result.rows
      .filter((r) => r.status !== "invalid" && r.normalized)
      .map((r) => r.normalized!);
    if (!validRows.length) return;
    setCommitting(true);
    try {
      const res = await commitImport(validRows);
      setCommitted(res);
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setCommitting(false);
    }
  };

  const displayRows =
    result?.rows.filter((r) => filter === "all" || r.status === filter) ?? [];

  const commitableCount =
    result?.rows.filter((r) => r.status !== "invalid" && r.normalized).length ?? 0;

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Bulk Import</h1>
        <p className="text-gray-500 mt-1">
          Upload a CSV bank statement to validate, preview corrections, and import
          transactions.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 p-3 text-red-700 text-sm">
          {error}
          <button className="ml-2 underline" onClick={() => setError(null)}>
            dismiss
          </button>
        </div>
      )}

      {committed && (
        <div className="mb-4 rounded-lg bg-green-50 border border-green-200 p-4 text-green-700">
          <p className="font-semibold">Import complete!</p>
          <p className="text-sm mt-1">
            {committed.inserted} transaction(s) inserted · {committed.duplicates} duplicate(s) skipped
          </p>
        </div>
      )}

      {/* Upload zone */}
      <div
        className="mb-6 rounded-xl border-2 border-dashed border-gray-300 p-8 text-center hover:border-indigo-400 transition-colors cursor-pointer"
        onClick={() => fileRef.current?.click()}
      >
        <p className="text-gray-500 text-sm">Click to select a CSV file</p>
        <p className="text-gray-400 text-xs mt-1">Supported: .csv</p>
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFile}
        />
      </div>

      {loading && (
        <div className="flex h-32 items-center justify-center text-gray-500">
          Validating…
        </div>
      )}

      {result && !loading && (
        <>
          <SummaryBar s={result.summary} />

          {/* Filter tabs */}
          <div className="flex gap-2 mb-4">
            {(["all", "valid", "warning", "invalid"] as FilterType[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded-full text-sm font-medium border transition-colors capitalize ${
                  filter === f
                    ? "bg-indigo-600 text-white border-indigo-600"
                    : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"
                }`}
              >
                {f === "all" ? `All (${result.rows.length})` : `${f} (${result.rows.filter((r) => r.status === f).length})`}
              </button>
            ))}
          </div>

          {/* Row list */}
          <div className="space-y-2 mb-6">
            {displayRows.length === 0 ? (
              <p className="text-center text-gray-400 py-8 text-sm">No rows to show.</p>
            ) : (
              displayRows.map((r) => <RowCard key={r.row_index} row={r} />)
            )}
          </div>

          {/* Commit button */}
          {commitableCount > 0 && !committed && (
            <div className="sticky bottom-4 flex justify-end">
              <button
                onClick={handleCommit}
                disabled={committing}
                className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg font-medium shadow hover:bg-indigo-700 disabled:opacity-50"
              >
                {committing ? "Importing…" : `Import ${commitableCount} valid transaction(s)`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
