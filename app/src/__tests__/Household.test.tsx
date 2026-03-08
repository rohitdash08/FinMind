import { describe, it, expect } from 'vitest';
import { createHousehold, addMember, getHousehold, listHouseholds } from '@/utils/household';

describe('Household MVP', () => {
  it('creates and persists a household', () => {
    const h = createHousehold('TestHouse', 'owner@example.com');
    expect(h).toBeDefined();
    const loaded = getHousehold(h.id);
    expect(loaded).toBeTruthy();
    expect(loaded!.name).toBe('TestHouse');
  });

  it('adds and lists members', () => {
    const h = createHousehold('TestHouse2', 'owner2@example.com');
    addMember(h.id, 'member1@example.com');
    const loaded = getHousehold(h.id);
    expect(loaded?.members).toContain('member1@example.com');
  });
});
