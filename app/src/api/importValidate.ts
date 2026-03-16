import api from "./index";

export type RowStatus = "valid" | "warning" | "invalid";

export interface ImportCorrection {
  field: string;
  original: string;
  corrected: string;
}

export interface ValidatedRow {
  row_index: number;
  status: RowStatus;
  warnings: string[];
  corrections: ImportCorrection[];
  normalized: {
    date: string;
    amount: number;
    description: string;
    category_id: number | null;
    expense_type: string;
    currency: string;
  } | null;
  raw: Record<string, unknown>;
}

export interface ValidationSummary {
  total: number;
  valid: number;
  warnings: number;
  invalid: number;
  duplicates: number;
}

export interface ImportValidationResult {
  rows: ValidatedRow[];
  summary: ValidationSummary;
}

export async function validateImport(
  file: File
): Promise<ImportValidationResult> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<ImportValidationResult>(
    "/expenses/import/validate",
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}

export async function commitImport(
  transactions: ValidatedRow["normalized"][]
): Promise<{ inserted: number; duplicates: number }> {
  const { data } = await api.post<{ inserted: number; duplicates: number }>(
    "/expenses/import/commit",
    { transactions }
  );
  return data;
}
