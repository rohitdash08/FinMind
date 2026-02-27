import { validateTransaction, validateImportBatch, type ValidationWarning } from '@/lib/import-validation';
import type { ImportTransaction } from '@/api/expenses';

function makeTx(overrides: Partial<ImportTransaction> = {}): ImportTransaction {
  return {
    date: '2025-06-15',
    amount: 42.5,
    description: 'Groceries',
    category_id: null,
    currency: 'USD',
    ...overrides,
  };
}

describe('validateTransaction', () => {
  it('returns no warnings for a valid transaction', () => {
    expect(validateTransaction(makeTx(), 0)).toEqual([]);
  });

  it('returns error when date is missing', () => {
    const result = validateTransaction(makeTx({ date: '' }), 0);
    expect(result).toEqual([
      expect.objectContaining({ field: 'date', severity: 'error', message: 'Date is missing' }),
    ]);
  });

  it('returns error for invalid date format', () => {
    const result = validateTransaction(makeTx({ date: '15/06/2025' }), 0);
    expect(result).toEqual([
      expect.objectContaining({ field: 'date', severity: 'error', message: expect.stringContaining('Invalid date') }),
    ]);
  });

  it('returns error for negative amount', () => {
    const result = validateTransaction(makeTx({ amount: -10 }), 0);
    expect(result).toEqual([
      expect.objectContaining({ field: 'amount', severity: 'error', message: 'Amount is negative' }),
    ]);
  });

  it('returns error for zero amount', () => {
    const result = validateTransaction(makeTx({ amount: 0 }), 0);
    expect(result).toEqual([
      expect.objectContaining({ field: 'amount', severity: 'error', message: 'Amount is zero' }),
    ]);
  });

  it('returns warning for empty description', () => {
    const result = validateTransaction(makeTx({ description: '' }), 0);
    expect(result).toEqual([
      expect.objectContaining({ field: 'description', severity: 'warning', message: 'Description is empty' }),
    ]);
  });

  it('returns warning for future date', () => {
    const future = new Date();
    future.setFullYear(future.getFullYear() + 1);
    const dateStr = future.toISOString().slice(0, 10);
    const result = validateTransaction(makeTx({ date: dateStr }), 0);
    expect(result).toEqual([
      expect.objectContaining({ field: 'date', severity: 'warning', message: 'Date is in the future' }),
    ]);
  });

  it('returns warning for large amount', () => {
    const result = validateTransaction(makeTx({ amount: 15000 }), 0);
    expect(result).toEqual([
      expect.objectContaining({ field: 'amount', severity: 'warning', message: expect.stringContaining('exceeds') }),
    ]);
  });

  it('uses 1-based row numbers', () => {
    const result = validateTransaction(makeTx({ amount: -1 }), 4);
    expect(result[0].row).toBe(5);
  });
});

describe('validateImportBatch', () => {
  it('aggregates errors and warnings correctly', () => {
    const txs: ImportTransaction[] = [
      makeTx(),                          // valid
      makeTx({ amount: -5 }),            // error
      makeTx({ description: '' }),       // warning
      makeTx({ date: 'bad', amount: 0 }),// 2 errors
    ];
    const result = validateImportBatch(txs);
    expect(result.errors.length).toBe(3);
    expect(result.warnings.length).toBe(1);
    expect(result.hasBlockingErrors).toBe(true);
  });

  it('returns hasBlockingErrors false when only warnings exist', () => {
    const txs: ImportTransaction[] = [
      makeTx({ description: '' }),
    ];
    const result = validateImportBatch(txs);
    expect(result.errors).toHaveLength(0);
    expect(result.warnings).toHaveLength(1);
    expect(result.hasBlockingErrors).toBe(false);
  });

  it('handles empty array', () => {
    const result = validateImportBatch([]);
    expect(result.errors).toHaveLength(0);
    expect(result.warnings).toHaveLength(0);
    expect(result.hasBlockingErrors).toBe(false);
  });
});
