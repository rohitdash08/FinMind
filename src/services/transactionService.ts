// PATCH: 此為 AI 生成的修復建議，請人工審查後合併
import { deduplicateTransactions } from '../utils/deduplication';
import deduplicationConfig from '../config/deduplicationConfig';
import * as transactionRepo from '../repositories/transactionRepository';

interface Transaction {
  id?: string;
  date: string;
  amount: number;
  description: string;
  category?: string;
  accountId?: string;
}

export async function importTransactions(incoming: Transaction[]): Promise<{
  imported: number;
  duplicates: number;
}> {
  const existing = await transactionRepo.getAll();
  const { unique, duplicates } = deduplicateTransactions(
    incoming,
    existing,
    deduplicationConfig
  );

  if (unique.length > 0) {
    await transactionRepo.bulkCreate(unique);
  }

  return { imported: unique.length, duplicates: duplicates.length };
}

export async function syncTransactions(incoming: Transaction[]): Promise<{
  synced: number;
  duplicates: number;
}> {
  const existing = await transactionRepo.getAll();
  const { unique, duplicates } = deduplicateTransactions(
    incoming,
    existing,
    deduplicationConfig
  );

  for (const tx of unique) {
    if (tx.id) {
      await transactionRepo.update(tx.id, tx);
    } else {
      await transactionRepo.create(tx);
    }
  }

  return { synced: unique.length, duplicates: duplicates.length };
}
