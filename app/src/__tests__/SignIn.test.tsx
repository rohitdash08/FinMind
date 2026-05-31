import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SignIn } from '@/pages/SignIn';
import { MemoryRouter } from 'react-router-dom';

// Mock toast
const toastMock = jest.fn();
jest.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

// Mock heavy UI components used inside SignIn to avoid jsdom layout APIs
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children }: React.PropsWithChildren) => <div data-testid="FinancialCard">{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
jest.mock('@/components/ui/separator', () => ({
  Separator: () => <hr />,
}));
jest.mock('lucide-react', () => new Proxy({}, {
  get: () => (props: Record<string, unknown>) => <span {...props} />,
}));
jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));
jest.mock('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));
jest.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.PropsWithChildren & React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label>,
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

// Mock auth API
jest.mock('@/api/auth', () => ({
  login: jest.fn(),
  me: jest.fn(),
}));

// Mock token setters to avoid touching localStorage in this test
jest.mock('@/lib/auth', () => ({
  setToken: jest.fn(),
  setRefreshToken: jest.fn(),
  setCurrency: jest.fn(),
}));

import { login, me } from '@/api/auth';

describe('SignIn page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (me as jest.Mock).mockResolvedValue({
      id: 1,
      email: 'demo@finmind.local',
      preferred_currency: 'USD',
    });
  });

  it('shows success toast and navigates on successful login', async () => {
    (login as jest.Mock).mockResolvedValue({ access_token: 'a', refresh_token: 'r' });

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
      expect.objectContaining({ title: expect.stringMatching(/welcome/i) })
    );
    expect(navigateMock).toHaveBeenCalled();
  });

  it('shows error toast on failed login', async () => {
    (login as jest.Mock).mockRejectedValue(new Error('invalid credentials'));

    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>
    );

    await userEvent.type(screen.getByLabelText(/email/i), 'demo@finmind.local');
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: /sign in to your account/i }));

    await waitFor(() => expect(toastMock).toHaveBeenCalled());
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: 'destructive',
        title: expect.stringMatching(/failed/i),
      })
    );
  });
});
