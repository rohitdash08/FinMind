export type Household = {
  id: string;
  name: string;
  members: string[];
  createdAt: string;
};

const STORAGE_KEY_HOUSEHOLDS = 'finmind.households';

function getStorage(): Storage | null {
  // SSR-safe: avoid touching window when not available
  if (typeof window !== 'undefined' && (window as any).localStorage) {
    return (window as any).localStorage;
  }
  return null;
}

function readAll(): Record<string, Household> {
  const storage = getStorage();
  if (!storage) return {};
  try {
    const raw = storage.getItem(STORAGE_KEY_HOUSEHOLDS);
    return raw ? (JSON.parse(raw) as Record<string, Household>) : {};
  } catch {
    return {};
  }
}

function writeAll(all: Record<string, Household>) {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.setItem(STORAGE_KEY_HOUSEHOLDS, JSON.stringify(all));
  } catch {
    // ignore write failures in non-critical environments
  }
}

export function createHousehold(userId: string, name: string): string {
  const id = `hh_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const hh: Household = { id, name, members: [userId], createdAt: new Date().toISOString() };
  const all = readAll();
  all[id] = hh;
  writeAll(all);
  return id;
}

export function addMember(householdId: string, userId: string): void {
  const all = readAll();
  const hh = all[householdId];
  if (!hh) return;
  if (!hh.members.includes(userId)) {
    hh.members.push(userId);
  }
  all[householdId] = hh;
  writeAll(all);
}

export function getHousehold(householdId: string): Household | null {
  const all = readAll();
  return all[householdId] || null;
}

export function listHouseholds(): Household[] {
  const all = readAll();
  return Object.values(all);
}

export default {
  createHousehold,
  addMember,
  getHousehold,
  listHouseholds,
};
