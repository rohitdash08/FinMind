import { api } from './client';

export type Snapshot = {
  snapshot_id: number;
  total_expenses: number;
  total_income: number;
  total_bills: number;
  net_worth: number;
  created_at: string;
};

export type SimulationResult = {
  snapshot_id: number;
  total_income: number;
  total_expenses: number;
  total_bills: number;
  net_worth: number;
  adjustments: Record<string, number>;
};

export async function createSnapshot(): Promise<Snapshot> {
  return api<Snapshot>('/digital-twin/create', { method: 'POST' });
}

export async function listSnapshots(): Promise<Snapshot[]> {
  return api<Snapshot[]>('/digital-twin/snapshots');
}

export async function simulate(
  snapshotId: number,
  adjustments: Record<string, number>,
): Promise<SimulationResult> {
  return api<SimulationResult>('/digital-twin/simulate', {
    method: 'POST',
    body: { snapshot_id: snapshotId, adjustments },
  });
}
