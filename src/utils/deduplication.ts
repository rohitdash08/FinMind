// PATCH: 此為 AI 生成的修復建議，請人工審查後合併
import stringSimilarity from 'string-similarity';

interface Transaction {
  id?: string;
  date: string;
  amount: number;
  description: string;
  category?: string;
  accountId?: string;
}

interface DeduplicationConfig {
  threshold: number;
  fields: string[];
}

const DEFAULT_CONFIG: DeduplicationConfig = {
  threshold: 0.9,
  fields: ['date', 'amount', 'description', 'category'],
};

function buildFingerprint(transaction: Transaction, fields: string[]): string {
  const parts = fields.map(field => {
    const value = transaction[field as keyof Transaction];
    if (value === undefined || value === null) return '';
    return String(value).trim().toLowerCase();
  });
  return parts.join('|');
}

export function deduplicateTransactions(
  incoming: Transaction[],
  existing: Transaction[],
  config: Partial<DeduplicationConfig> = {}
): { unique: Transaction[]; duplicates: Transaction[] } {
  const effectiveConfig = { ...DEFAULT_CONFIG, ...config };
  const unique: Transaction[] = [];
  const duplicates: Transaction[] = [];

  for (const candidate of incoming) {
    if (existing.length === 0) {
      unique.push(candidate);
      continue;
    }

    const candidateFingerprint = buildFingerprint(candidate, effectiveConfig.fields);
    const similarities = existing.map(existingTx => {
      const existingFingerprint = buildFingerprint(existingTx, effectiveConfig.fields);
      return stringSimilarity.compareTwoStrings(candidateFingerprint, existingFingerprint);
    });

    const maxSimilarity = Math.max(...similarities);
    if (maxSimilarity >= effectiveConfig.threshold) {
      duplicates.push(candidate);
    } else {
      unique.push(candidate);
    }
  }

  return { unique, duplicates };
}
