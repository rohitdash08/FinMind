import { checkUnusualLogin } from './login-detection';

describe('checkUnusualLogin SSR safety', () => {
  const originalWindow = (global as any).window;
  beforeEach(() => {
    // reset history in localStorage when available
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.clear();
    }
  });
  afterAll(() => {
    (global as any).window = originalWindow;
  });

  test('returns false when window is undefined (SSR)', () => {
    (global as any).window = undefined;
    const res = checkUnusualLogin(999, { userAgent: 'UA-SS', ip: '0.0.0.0' });
    expect(res).toBe(false);
  });
});
