import { checkUnusualLogin } from '../utils/login-detection';

describe('checkUnusualLogin', () => {
  beforeEach(() => {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.clear();
    }
  });

  test('returns false on first login', () => {
    const isUnusual = checkUnusualLogin(1, { userAgent: 'UA1', ip: '1.2.3.4' });
    expect(isUnusual).toBe(false);
  });

  test('returns true only when context is unseen in history', () => {
    // first login
    expect(checkUnusualLogin(2, { userAgent: 'UA1', ip: '1.2.3.4' })).toBe(false);
    // same IP, different UA – should not be unusual because IP has been seen
    expect(checkUnusualLogin(2, { userAgent: 'UA2', ip: '1.2.3.4' })).toBe(false);
    // new context: both UA and IP unseen should be flagged
    const isUnusual = checkUnusualLogin(2, { userAgent: 'UA3', ip: '9.9.9.9' });
    expect(isUnusual).toBe(true);
  });
});
