import { checkUnusualLogin } from './login-detection';

describe('checkUnusualLogin', () => {
  beforeEach(() => {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.clear();
    }
  });

  test('returns false on first login (no history)', () => {
    const result = checkUnusualLogin(1, { userAgent: 'UA-1' });
    expect(result).toBe(false);
  });

  test('is not unusual if userAgent remains the same', () => {
    // First login
    expect(checkUnusualLogin(2, { userAgent: 'UA-TEST' })).toBe(false);
    // Second login with same UA for same user should not be unusual
    const second = checkUnusualLogin(2, { userAgent: 'UA-TEST' });
    expect(second).toBe(false);
  });

  test('flags unusual when userAgent changes', () => {
    // First login with UA-A
    expect(checkUnusualLogin(3, { userAgent: 'UA-A' })).toBe(false);
    // Second login with a different UA should be unusual
    const res = checkUnusualLogin(3, { userAgent: 'UA-B' });
    expect(res).toBe(true);
  });

  test('flags unusual when IP changes', () => {
    // First login with IP 1.1.1.1
    expect(checkUnusualLogin(4, { userAgent: 'UA', ip: '1.1.1.1' })).toBe(false);
    // Second login with a different IP but same UA triggers unusual
    const res = checkUnusualLogin(4, { userAgent: 'UA', ip: '2.2.2.2' });
    expect(res).toBe(true);
  });
});
