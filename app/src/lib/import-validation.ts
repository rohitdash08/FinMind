import type { ImportTransaction } from '@/api/expenses';

export type ValidationWarning = {
  row: number;
  field: string;
  severity: 'error' | 'warning';
  message: string;
};

export type BatchValidationResult = {
  warnings: ValidationWarning[];
  errors: ValidationWarning[];
  hasBlockingErrors: boolean;
};

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function isValidDate(dateStr: string): boolean {
  if (!ISO_DATE_RE.test(dateStr)) return false;
  const d = new Date(dateStr + 'T00:00:00');
  return !isNaN(d.getTime());
}

function isFutureDate(dateStr: string): boolean {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(dateStr + 'T00:00:00');
  return d.getTime() > today.getTime();
}

const LARGE_AMOUNT_THRESHOLD = 10_000;

export function validateTransaction(
  tx: ImportTransaction,
  index: number,
): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];
  const row = index + 1;

  // Date checks
  if (!tx.date || tx.date.trim() === '') {
    warnings.push({ row, field: 'date', severity: 'error', message: 'Date is missing' });
  } else if (!isValidDate(tx.date)) {
    warnings.push({ row, field: 'date', severity: 'error', message: 'Invalid date format (expected YYYY-MM-DD)' });
  } else if (isFutureDate(tx.date)) {
    warnings.push({ row, field: 'date', severity: 'warning', message: 'Date is in the future' });
  }

  // Amount checks
  if (tx.amount < 0) {
    warnings.push({ row, field: 'amount', severity: 'error', message: 'Amount is negative' });
  } else if (tx.amount === 0) {
    warnings.push({ row, field: 'amount', severity: 'error', message: 'Amount is zero' });
  } else if (tx.amount > LARGE_AMOUNT_THRESHOLD) {
    warnings.push({ row, field: 'amount', severity: 'warning', message: `Amount exceeds ${LARGE_AMOUNT_THRESHOLD.toLocaleString()}` });
  }

  // Description checks
  if (!tx.description || tx.description.trim() === '') {
    warnings.push({ row, field: 'description', severity: 'warning', message: 'Description is empty' });
  }

  return warnings;
}

export function validateImportBatch(
  transactions: ImportTransaction[],
): BatchValidationResult {
  const all: ValidationWarning[] = [];

  for (let i = 0; i < transactions.length; i++) {
    all.push(...validateTransaction(transactions[i], i));
  }

  const errors = all.filter((w) => w.severity === 'error');
  const warnings = all.filter((w) => w.severity === 'warning');

  return {
    errors,
    warnings,
    hasBlockingErrors: errors.length > 0,
  };
}
