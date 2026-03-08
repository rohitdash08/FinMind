import { createHousehold, getHousehold, addMember, listHouseholds, removeMember } from './household';

describe('FinMind household (minimal scaffold for EASY #134)', () => {
  const originalWindow = (global as any).window;
  beforeEach(() => {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.clear();
    }
  });
  afterAll(() => {
    (global as any).window = originalWindow;
  });

  test('SSR-safe: does not crash when window undefined', () => {
    (global as any).window = undefined;
    const id = createHousehold('u1', 'Test');
    expect(typeof id).toBe('string');
  });

  test('basic create and fetch', () => {
    const id = createHousehold('u1','TestHousehold');
    const hh = getHousehold(id);
    expect(hh).toBeTruthy();
    expect(hh!.name).toBe('TestHousehold');
    expect(hh!.members).toContain('u1');
  });

  test('addMember updates members', () => {
    const id = createHousehold('u1','Group');
    addMember(id, 'u2');
    const hh = getHousehold(id);
    expect(hh?.members).toContain('u2');
  });

  test('removeMember updates members', () => {
    const id = createHousehold('u1','Group2');
    addMember(id, 'u2');
    removeMember(id, 'u2');
    const hh = getHousehold(id);
    expect(hh?.members).not.toContain('u2');
  });

  test('listHouseholds returns at least one', () => {
    const id = createHousehold('u1','ListTest');
    const list = listHouseholds();
    expect(list.find(h => h.id === id)).toBeTruthy();
  });
});
