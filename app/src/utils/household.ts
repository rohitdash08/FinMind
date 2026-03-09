// Lightweight household collaboration utilities (in-browser MVP)
// Stores households in localStorage per browser.
type Member = string; // could be user email or id in MVP
type Household = {
  id: string;
  name: string;
  owner?: string;
  members: Member[];
  createdAt?: number;
};

function storageKey(id: string): string {
  return `finmind_household_${id}`;
}

function uid(): string {
  return Math.random().toString(36).slice(2, 9) + Date.now().toString(36);
}

// Create a new household and persist it
export function createHousehold(name: string, owner?: string): Household {
  const id = uid();
  const h: Household = {
    id,
    name,
    owner,
    members: owner ? [owner] : [],
    createdAt: Date.now(),
  };
  localStorage.setItem(storageKey(id), JSON.stringify(h));
  return h;
}

export function getHousehold(id: string): Household | null {
  try {
    const raw = localStorage.getItem(storageKey(id));
    if (!raw) return null;
    return JSON.parse(raw) as Household;
  } catch {
    return null;
  }
}

export function addMember(id: string, member: string): boolean {
  const h = getHousehold(id);
  if (!h) return false;
  if (!h.members.includes(member)) {
    h.members.push(member);
    localStorage.setItem(storageKey(id), JSON.stringify(h));
  }
  return true;
}

export function removeMember(id: string, member: string): boolean {
  const h = getHousehold(id);
  if (!h) return false;
  h.members = h.members.filter((m) => m !== member);
  localStorage.setItem(storageKey(id), JSON.stringify(h));
  return true;
}

export function listHouseholds(): Household[] {
  // Not efficient: scan all keys in localStorage. For MVP, we assume keys start with finmind_household_
  const out: Household[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith('finmind_household_')) {
      const h = getHousehold(key.replace('finmind_household_', ''));
      if (h) out.push(h);
    }
  }
  return out;
}

export default {
  createHousehold,
  getHousehold,
  addMember,
  removeMember,
  listHouseholds,
};
