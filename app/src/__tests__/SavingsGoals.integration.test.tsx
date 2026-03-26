import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SavingsGoals from '@/pages/SavingsGoals';

// Mock UI components
jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}));
jest.mock('@/components/ui/progress', () => ({
  Progress: ({ value }: { value: number }) => (
    <div role="progressbar" aria-valuenow={value} />
  ),
}));
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));
jest.mock('@/components/ui/alert-dailog', () => ({
  AlertDialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

const listSavingsGoalsMock = jest.fn();
const getSavingsSummaryMock = jest.fn();
const createSavingsGoalMock = jest.fn();
const deleteSavingsGoalMock = jest.fn();

jest.mock('@/api/savings', () => ({
  listSavingsGoals: (...args: unknown[]) => listSavingsGoalsMock(...args),
  getSavingsSummary: (...args: unknown[]) => getSavingsSummaryMock(...args),
  createSavingsGoal: (...args: unknown[]) => createSavingsGoalMock(...args),
  updateSavingsGoal: jest.fn(),
  deleteSavingsGoal: (...args: unknown[]) => deleteSavingsGoalMock(...args),
  addContribution: jest.fn(),
  withdrawFromGoal: jest.fn(),
  getSavingsGoal: jest.fn(),
}));

jest.mock('@/lib/currency', () => ({
  formatMoney: (amount: number) => `$${amount.toFixed(2)}`,
}));

const mockSummary = {
  total_goals: 2,
  active_goals: 2,
  completed_goals: 0,
  total_saved: 2500,
  total_target: 15000,
  overall_progress_pct: 16.7,
};

const mockGoals = [
  {
    id: 1,
    name: 'Emergency Fund',
    description: '6 months of expenses',
    target_amount: 10000,
    current_amount: 2000,
    currency: 'USD',
    target_date: '2027-01-01',
    icon: 'shield',
    color: '#22c55e',
    status: 'ACTIVE',
    progress_pct: 20,
    remaining: 8000,
    days_remaining: 280,
    monthly_needed: 857.14,
  },
  {
    id: 2,
    name: 'Vacation',
    description: 'Summer trip',
    target_amount: 5000,
    current_amount: 500,
    currency: 'USD',
    target_date: null,
    icon: 'piggy-bank',
    color: '#6366f1',
    status: 'ACTIVE',
    progress_pct: 10,
    remaining: 4500,
  },
];

describe('SavingsGoals integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    listSavingsGoalsMock.mockResolvedValue(mockGoals);
    getSavingsSummaryMock.mockResolvedValue(mockSummary);
  });

  it('loads and renders savings goals and summary', async () => {
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalled());
    expect(screen.getByText('Savings Goals')).toBeInTheDocument();
    expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
    expect(screen.getByText('Vacation')).toBeInTheDocument();
    expect(screen.getByText('Total Saved')).toBeInTheDocument();
  });

  it('shows empty state when no goals exist', async () => {
    listSavingsGoalsMock.mockResolvedValue([]);
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalled());
    expect(screen.getByText('No savings goals yet')).toBeInTheDocument();
  });

  it('renders progress percentages', async () => {
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalled());
    expect(screen.getByText('20% complete')).toBeInTheDocument();
    expect(screen.getByText('10% complete')).toBeInTheDocument();
  });

  it('renders target date and monthly needed', async () => {
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalled());
    expect(screen.getByText(/280 days left/)).toBeInTheDocument();
    expect(screen.getByText(/\$857\.14/)).toBeInTheDocument();
  });

  it('filters goals by status', async () => {
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalledWith('ACTIVE'));

    const allButton = screen.getByRole('button', { name: /all goals/i });
    await userEvent.click(allButton);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalledWith('ALL'));
  });
});
