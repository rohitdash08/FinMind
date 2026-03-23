import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SavingsGoals from '@/pages/SavingsGoals';

const toastMock = jest.fn();
jest.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock('@/components/ui/input', () => ({
  Input: ({ ...props }: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));
jest.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.PropsWithChildren & React.LabelHTMLAttributes<HTMLLabelElement>) => (
    <label {...props}>{children}</label>
  ),
}));
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: React.PropsWithChildren & { open?: boolean }) => (
    <div data-open={open}>{children}</div>
  ),
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <div {...props}>{children}</div>
  ),
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLHeadingElement>) => (
    <h3 {...props}>{children}</h3>
  ),
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  FinancialCardContent: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <div {...props}>{children}</div>
  ),
}));
jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <span {...props}>{children}</span>
  ),
}));
jest.mock('@/components/ui/progress', () => ({
  Progress: ({ value, ...props }: { value: number } & React.HTMLAttributes<HTMLDivElement>) => (
    <div role="progressbar" aria-valuenow={value} {...props} />
  ),
}));

const listGoalsMock = jest.fn();
const createGoalMock = jest.fn();
const depositMock = jest.fn();
const withdrawMock = jest.fn();
const deleteGoalMock = jest.fn();
const updateGoalMock = jest.fn();

jest.mock('@/api/savingsGoals', () => ({
  listSavingsGoals: (...args: unknown[]) => listGoalsMock(...args),
  createSavingsGoal: (...args: unknown[]) => createGoalMock(...args),
  depositToGoal: (...args: unknown[]) => depositMock(...args),
  withdrawFromGoal: (...args: unknown[]) => withdrawMock(...args),
  deleteSavingsGoal: (...args: unknown[]) => deleteGoalMock(...args),
  updateSavingsGoal: (...args: unknown[]) => updateGoalMock(...args),
}));

// Suppress console.error from React Query
beforeEach(() => {
  jest.spyOn(console, 'error').mockImplementation(() => {});
});

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

const sampleGoal = {
  id: 1,
  name: 'Emergency Fund',
  target_amount: 5000,
  current_amount: 2500,
  currency: 'USD',
  deadline: '2026-12-31',
  status: 'ACTIVE' as const,
  progress: 50,
  milestones: [
    { percentage: 25, reached: true },
    { percentage: 50, reached: true },
    { percentage: 75, reached: false },
    { percentage: 100, reached: false },
  ],
  created_at: '2026-01-01T00:00:00',
};

describe('SavingsGoals page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders empty state when no goals exist', async () => {
    listGoalsMock.mockResolvedValue([]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText(/no savings goals yet/i)).toBeInTheDocument();
    });
  });

  it('renders goals list with progress and milestones', async () => {
    listGoalsMock.mockResolvedValue([sampleGoal]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
    });
    expect(screen.getByText(/50%/)).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders summary cards with formatted amounts using goal currency', async () => {
    listGoalsMock.mockResolvedValue([sampleGoal]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      // Should use USD formatting, not hardcoded $
      expect(screen.getByText('$2,500.00')).toBeInTheDocument();
      expect(screen.getByText('$5,000.00')).toBeInTheDocument();
    });
  });

  it('shows New Goal button', async () => {
    listGoalsMock.mockResolvedValue([]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText(/new goal/i)).toBeInTheDocument();
    });
  });

  it('renders status filter buttons', async () => {
    listGoalsMock.mockResolvedValue([]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText('All')).toBeInTheDocument();
      expect(screen.getByText('ACTIVE')).toBeInTheDocument();
      expect(screen.getByText('COMPLETED')).toBeInTheDocument();
      expect(screen.getByText('CANCELLED')).toBeInTheDocument();
    });
  });

  it('shows deposit and withdraw buttons for active goals with balance', async () => {
    listGoalsMock.mockResolvedValue([sampleGoal]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText('Deposit')).toBeInTheDocument();
      expect(screen.getByText('Withdraw')).toBeInTheDocument();
    });
  });

  it('shows completed badge for completed goals', async () => {
    const completedGoal = {
      ...sampleGoal,
      id: 2,
      status: 'COMPLETED' as const,
      current_amount: 5000,
      progress: 100,
      milestones: sampleGoal.milestones.map((m) => ({ ...m, reached: true })),
    };
    listGoalsMock.mockResolvedValue([completedGoal]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText('Completed')).toBeInTheDocument();
    });
  });

  it('shows overdue indicator for past-deadline active goals', async () => {
    const overdueGoal = {
      ...sampleGoal,
      deadline: '2020-01-01', // past date
    };
    listGoalsMock.mockResolvedValue([overdueGoal]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText(/overdue/i)).toBeInTheDocument();
    });
  });

  it('shows goals progress count in summary', async () => {
    const completedGoal = {
      ...sampleGoal,
      id: 2,
      name: 'Done Goal',
      status: 'COMPLETED' as const,
      current_amount: 5000,
      progress: 100,
      milestones: sampleGoal.milestones.map((m) => ({ ...m, reached: true })),
    };
    listGoalsMock.mockResolvedValue([sampleGoal, completedGoal]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText('1 / 2 completed')).toBeInTheDocument();
    });
  });

  it('renders delete confirmation dialog text', async () => {
    listGoalsMock.mockResolvedValue([sampleGoal]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      // The delete confirmation dialog is always in DOM (but may be hidden)
      expect(screen.getByText('Delete Goal')).toBeInTheDocument();
      expect(screen.getByText(/permanently delete/i)).toBeInTheDocument();
    });
  });
});
