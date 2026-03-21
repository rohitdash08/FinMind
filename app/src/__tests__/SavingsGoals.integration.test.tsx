import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SavingsGoals from '@/pages/SavingsGoals';

const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
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
  Dialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
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
jest.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

const listGoalsMock = jest.fn();
const createGoalMock = jest.fn();
const depositMock = jest.fn();
const deleteGoalMock = jest.fn();
const updateGoalMock = jest.fn();

jest.mock('@/api/savingsGoals', () => ({
  listSavingsGoals: (...args: unknown[]) => listGoalsMock(...args),
  createSavingsGoal: (...args: unknown[]) => createGoalMock(...args),
  depositToGoal: (...args: unknown[]) => depositMock(...args),
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
    listGoalsMock.mockResolvedValue([
      {
        id: 1,
        name: 'Emergency Fund',
        target_amount: 5000,
        current_amount: 2500,
        currency: 'USD',
        deadline: '2026-12-31',
        status: 'ACTIVE',
        progress: 50,
        milestones: [
          { percentage: 25, reached: true },
          { percentage: 50, reached: true },
          { percentage: 75, reached: false },
          { percentage: 100, reached: false },
        ],
      },
    ]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
    });
    expect(screen.getByText(/50%/)).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders summary cards with totals', async () => {
    listGoalsMock.mockResolvedValue([
      {
        id: 1,
        name: 'Goal A',
        target_amount: 1000,
        current_amount: 400,
        currency: 'USD',
        deadline: null,
        status: 'ACTIVE',
        progress: 40,
        milestones: [
          { percentage: 25, reached: true },
          { percentage: 50, reached: false },
          { percentage: 75, reached: false },
          { percentage: 100, reached: false },
        ],
      },
    ]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText('$400.00')).toBeInTheDocument();
      expect(screen.getByText('$1,000.00')).toBeInTheDocument();
    });
  });

  it('shows New Goal button', async () => {
    listGoalsMock.mockResolvedValue([]);
    renderWithProviders(<SavingsGoals />);

    await waitFor(() => {
      expect(screen.getByText(/new goal/i)).toBeInTheDocument();
    });
  });
});
