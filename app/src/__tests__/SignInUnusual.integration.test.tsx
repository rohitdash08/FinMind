import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SignIn } from '@/pages/SignIn';
import { MemoryRouter } from 'react-router-dom';

// Mocks
const toastMock = jest.fn();
jest.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

// Mock API
jest.mock('@/api/auth', () => ({
  login: jest.fn(),
  me: jest.fn(),
}));
// Mock token setters
jest.mock('@/lib/auth', () => ({
  setToken: jest.fn(),
  setRefreshToken: jest.fn(),
  setCurrency: jest.fn(),
}));

// Mock router navigate
const navigateMock = jest.fn();
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useLocation: () => ({ state: undefined }),
  };
});

import { login, me } from '@/api/auth';

describe('SignIn unusual login integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Seed previous login history to trigger anomaly when UA changes
    localStorage.setItem('finmind_login_history_1', JSON.stringify({ lastUserAgent: 'OldUA', lastIp: '1.2.3.4', lastTimestamp: Date.now() - 10000 }));
  });

  it('shows unusual login toast when UA changes', async () => {
    // Mock API responses
    (login as jest.Mock).mockResolvedValue({ access_token: 'a', refresh_token: 'r' });
    (me as jest.Mock).mockResolvedValue({ id: 1, email: 'demo@finmind.local', preferred_currency: 'USD' });

    // Override navigator.userAgent in tests
    (global as any).navigator = { userAgent: 'NewUA' } as Navigator & { userAgent: string };

    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>
    );

    await userEvent.type(screen.getByLabelText(/email/i), 'demo@finmind.local');
    await userEvent.type(screen.getByLabelText(/password/i), 'DemoPass123!');
    await userEvent.click(screen.getByRole('button', { name: /sign in to your account/i }));

    await waitFor(() => expect(toastMock).toHaveBeenCalled());
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: expect.stringMatching(/Unusual login detected/i) })
    );
    expect(navigateMock).toHaveBeenCalled();
  });
});
