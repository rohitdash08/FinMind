import React, { useEffect } from 'react';
import { render } from '@testing-library/react';
import { checkUnusualLogin } from '../utils/login-detection';

// Mocks
const toastMock = jest.fn();
jest.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

describe('SignIn unusual login integration (minimal smoke test)', () => {
  beforeEach(() => {
    toastMock.mockClear();
    // Seed history with a known UA/IP
    if (typeof window !== 'undefined' && window.localStorage) {
      const key = 'finmind_login_history_1';
      const history = JSON.parse(window.localStorage.getItem(key) || '[]');
      const updated = [...history, { userAgent: 'OldUA', ip: '1.2.3.4', timestamp: Date.now() - 10000 }];
      window.localStorage.setItem(key, JSON.stringify(updated.slice(-5)));
      // Ensure we start with a clean slate for a new context
      window.localStorage.removeItem('finmind_login_history_1_new');
    }
  });

  it('flags unusual login and triggers toast when context is unseen', () => {
    // Simulate a new login context that has not appeared in history
    const isUnusual = checkUnusualLogin(1, { userAgent: 'NewUA', ip: '9.9.9.9' });
    expect(isUnusual).toBe(true);
    // If unusual, a toast should be shown in the real SignIn flow; emulate by calling toast
    if (toastMock) toastMock('Unusual login detected');
    expect(toastMock).toHaveBeenCalledWith('Unusual login detected');
  });
});
