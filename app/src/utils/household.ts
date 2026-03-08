export interface HouseholdMember {
  email: string;
  name?: string;
  role?: string;
  joinedAt: string; // ISO timestamp
}

const STORAGE_KEY = 'finmind_household_members';

export function getMembers(): HouseholdMember[] {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage.getItem(STORAGE_KEY) : null;
    if (!raw) return [];
    const parsed = JSON.parse(raw) as HouseholdMember[];
    if (Array.isArray(parsed)) return parsed;
    return [];
  } catch {
    return [];
  }
}

function saveMembers(members: HouseholdMember[]) {
  try {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(members));
  } catch {
    // ignore storage errors
  }
}

export function addMember(email: string, name?: string, role?: string): void {
  const existing = getMembers();
  const member: HouseholdMember = {
    email,
    name,
    role,
    joinedAt: new Date().toISOString(),
  };
  existing.push(member);
  saveMembers(existing);
}

export function removeMember(email: string): void {
  const existing = getMembers();
  const next = existing.filter(m => m.email !== email);
  saveMembers(next);
}
