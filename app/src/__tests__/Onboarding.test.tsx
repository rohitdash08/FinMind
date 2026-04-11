import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { Onboarding } from '@/pages/Onboarding';

// ---- Mock toast ----
const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

// ---- Mock financial-card ----
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children }: React.PropsWithChildren) => <div data-testid="FinancialCard">{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

// ---- Mock lucide icons ----
jest.mock('lucide-react', () =>
  new Proxy(
    {},
    { get: () => (props: Record<string, unknown>) => <span {...props} /> },
  ),
);

// ---- Mock UI primitives ----
jest.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    ...props
  }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));
jest.mock('@/components/ui/label', () => ({
  Label: ({
    children,
    ...props
  }: React.PropsWithChildren & React.LabelHTMLAttributes<HTMLLabelElement>) => (
    <label {...props}>{children}</label>
  ),
}));

// ---- Mock navigate ----
const navigateMock = jest.fn();
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

// ---- Mock onboarding API ----
const completeOnboardingMock = jest.fn();
jest.mock('@/api/onboarding', () => {
  const actual = jest.requireActual<typeof import('@/api/onboarding')>('@/api/onboarding');
  return {
    ...actual,
    completeOnboarding: (...args: unknown[]) => completeOnboardingMock(...args),
    isOnboardingComplete: () => false,
    loadOnboardingDraft: () => null,
    saveOnboardingDraft: jest.fn(),
    markOnboardingComplete: jest.fn(),
  };
});

function renderOnboarding() {
  return render(
    <MemoryRouter>
      <Onboarding />
    </MemoryRouter>,
  );
}

describe('Onboarding wizard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
    completeOnboardingMock.mockResolvedValue({
      message: 'OK',
      onboarding_complete: true,
    });
  });

  it('renders the welcome step on mount', () => {
    renderOnboarding();
    expect(screen.getByText(/welcome to finmind/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /back/i })).toBeDisabled();
  });

  it('shows step indicator with correct number of steps', () => {
    renderOnboarding();
    // aria-label from StepIndicator
    expect(screen.getByLabelText(/step 1 of 6/i)).toBeInTheDocument();
  });

  it('advances to goals step when Next is clicked', async () => {
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText(/what are your financial goals/i)).toBeInTheDocument();
  });

  it('requires at least one goal before advancing past step 2', async () => {
    renderOnboarding();
    // Go to step 2
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText(/what are your financial goals/i)).toBeInTheDocument();
    // Next button should be disabled
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  });

  it('enables Next after selecting a goal on step 2', async () => {
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    // Select a goal
    await userEvent.click(screen.getByText(/track spending/i));
    expect(screen.getByRole('button', { name: /next/i })).not.toBeDisabled();
  });

  it('requires lifestyle selection before advancing past step 3', async () => {
    renderOnboarding();
    // step 1 → 2
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await userEvent.click(screen.getByText(/track spending/i));
    // step 2 → 3
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText(/which best describes you/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  });

  it('enables Next after selecting a lifestyle on step 3', async () => {
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await userEvent.click(screen.getByText(/track spending/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await userEvent.click(screen.getByText(/student/i));
    expect(screen.getByRole('button', { name: /next/i })).not.toBeDisabled();
  });

  it('renders income/expense step (step 4) with currency selector', async () => {
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await userEvent.click(screen.getByText(/track spending/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await userEvent.click(screen.getByText(/student/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText(/income & expense estimates/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/preferred currency/i)).toBeInTheDocument();
  });

  it('renders spending categories step (step 5)', async () => {
    renderOnboarding();
    // Navigate to step 5
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 2
    await userEvent.click(screen.getByText(/track spending/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 3
    await userEvent.click(screen.getByText(/student/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 4
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 5
    expect(screen.getByText(/spending categories/i)).toBeInTheDocument();
    expect(screen.getByText(/housing/i)).toBeInTheDocument();
  });

  it('renders notification preferences step (step 6)', async () => {
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 2
    await userEvent.click(screen.getByText(/track spending/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 3
    await userEvent.click(screen.getByText(/student/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 4
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 5
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 6
    expect(screen.getByText(/notification preferences/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /finish setup/i })).toBeInTheDocument();
  });

  it('calls completeOnboarding and navigates to dashboard on finish', async () => {
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 2
    await userEvent.click(screen.getByText(/track spending/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 3
    await userEvent.click(screen.getByText(/student/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 4
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 5
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 6
    await userEvent.click(screen.getByRole('button', { name: /finish setup/i }));
    await waitFor(() => expect(completeOnboardingMock).toHaveBeenCalledTimes(1));
    expect(completeOnboardingMock).toHaveBeenCalledWith(
      expect.objectContaining({
        financial_goals: ['track_spending'],
        lifestyle: 'student',
        preferred_currency: expect.any(String),
      }),
    );
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/dashboard', { replace: true }),
    );
  });

  it('shows success toast after completing setup', async () => {
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 2
    await userEvent.click(screen.getByText(/track spending/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 3
    await userEvent.click(screen.getByText(/student/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 4
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 5
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 6
    await userEvent.click(screen.getByRole('button', { name: /finish setup/i }));
    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Setup complete!' }),
      ),
    );
  });

  it('still completes even when API call fails (graceful degradation)', async () => {
    completeOnboardingMock.mockRejectedValue(new Error('Network error'));
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 2
    await userEvent.click(screen.getByText(/track spending/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 3
    await userEvent.click(screen.getByText(/student/i));
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 4
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 5
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 6
    await userEvent.click(screen.getByRole('button', { name: /finish setup/i }));
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/dashboard', { replace: true }),
    );
  });

  it('navigates back with the Back button', async () => {
    renderOnboarding();
    await userEvent.click(screen.getByRole('button', { name: /next/i })); // → 2
    expect(screen.getByText(/financial goals/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /back/i }));
    expect(screen.getByText(/welcome to finmind/i)).toBeInTheDocument();
  });
});

describe('Onboarding API helpers', () => {
  beforeEach(() => localStorage.clear());

  it('onboarding module exports ONBOARDING_STORAGE_KEY constant', async () => {
    const mod = await import('@/api/onboarding');
    expect(mod.ONBOARDING_STORAGE_KEY).toBeDefined();
  });

  it('DEFAULT_SPENDING_CATEGORIES has at least 5 entries', async () => {
    const mod = await import('@/api/onboarding');
    expect(mod.DEFAULT_SPENDING_CATEGORIES.length).toBeGreaterThanOrEqual(5);
  });
});
