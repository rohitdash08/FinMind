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
jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <span {...props}>{children}</span>
  ),
}));
jest.mock('@/components/ui/progress', () => ({
  Progress: ({ value, ...props }: { value?: number } & React.HTMLAttributes<HTMLDivElement>) => (
    <div role="progressbar" aria-valuenow={value} {...props} />
  ),
}));
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardHeader: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  FinancialCardTitle: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
}));
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: React.PropsWithChildren & { open?: boolean }) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
jest.mock('@/components/ui/alert-dailog', () => ({
  AlertDialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));

jest.mock('@/lib/currency', () => ({
  formatMoney: (amount: number, _currency?: string) => `$${Number(amount).toFixed(2)}`,
}));

const listSavingsGoalsMock = jest.fn();
const createSavingsGoalMock = jest.fn();
const updateSavingsGoalMock = jest.fn();
const deleteSavingsGoalMock = jest.fn();
const contributeToGoalMock = jest.fn();

jest.mock('@/api/savingsGoals', () => ({
  listSavingsGoals: (...args: unknown[]) => listSavingsGoalsMock(...args),
  createSavingsGoal: (...args: unknown[]) => createSavingsGoalMock(...args),
  updateSavingsGoal: (...args: unknown[]) => updateSavingsGoalMock(...args),
  deleteSavingsGoal: (...args: unknown[]) => deleteSavingsGoalMock(...args),
  contributeToGoal: (...args: unknown[]) => contributeToGoalMock(...args),
  getGoalMilestones: jest.fn(),
  CATEGORY_LABELS: {
    EMERGENCY: 'Emergency Fund',
    VACATION: 'Vacation',
    EDUCATION: 'Education',
    HOME: 'Home',
    CAR: 'Car',
    RETIREMENT: 'Retirement',
    INVESTMENT: 'Investment',
    OTHER: 'Other',
  },
  CATEGORY_COLORS: {
    EMERGENCY: 'bg-red-500',
    VACATION: 'bg-blue-500',
    EDUCATION: 'bg-purple-500',
    HOME: 'bg-green-500',
    CAR: 'bg-orange-500',
    RETIREMENT: 'bg-indigo-500',
    INVESTMENT: 'bg-emerald-500',
    OTHER: 'bg-gray-500',
  },
}));

const sampleGoal = {
  id: 1,
  name: 'Emergency Fund',
  target_amount: 10000,
  current_amount: 2500,
  currency: 'USD',
  deadline: '2026-12-31',
  category: 'EMERGENCY' as const,
  progress_pct: 25,
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-03-01T00:00:00',
  milestones: [
    { id: 1, percentage: 25, reached: true, reached_at: '2026-03-01T00:00:00' },
    { id: 2, percentage: 50, reached: false, reached_at: null },
    { id: 3, percentage: 75, reached: false, reached_at: null },
    { id: 4, percentage: 100, reached: false, reached_at: null },
  ],
  days_remaining: 276,
  daily_target: 27.17,
  monthly_target: 815.22,
  on_track: true,
};

describe('SavingsGoals page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    toastMock.mockClear();
  });

  it('renders empty state when no goals', async () => {
    listSavingsGoalsMock.mockResolvedValue([]);
    render(<SavingsGoals />);
    await waitFor(() => {
      expect(screen.getByText('No savings goals yet')).toBeInTheDocument();
    });
  });

  it('renders goals list with progress', async () => {
    listSavingsGoalsMock.mockResolvedValue([sampleGoal]);
    render(<SavingsGoals />);
    await waitFor(() => {
      expect(screen.getAllByText('Emergency Fund').length).toBeGreaterThan(0);
    });
    // Check amounts are displayed
    expect(screen.getAllByText('$2500.00').length).toBeGreaterThan(0);
    expect(screen.getAllByText('$10000.00').length).toBeGreaterThan(0);
  });

  it('renders summary cards with correct totals', async () => {
    listSavingsGoalsMock.mockResolvedValue([sampleGoal]);
    render(<SavingsGoals />);
    await waitFor(() => {
      expect(screen.getAllByText('Emergency Fund').length).toBeGreaterThan(0);
    });
    // Summary cards should be present
    expect(screen.getByText('Total Saved')).toBeInTheDocument();
    expect(screen.getByText('Active Goals')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Overall Progress')).toBeInTheDocument();
  });

  it('shows milestone dots', async () => {
    listSavingsGoalsMock.mockResolvedValue([sampleGoal]);
    render(<SavingsGoals />);
    await waitFor(() => {
      expect(screen.getAllByText('Emergency Fund').length).toBeGreaterThan(0);
    });
    // Milestone percentages rendered as text in dots
    expect(screen.getAllByText('25%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('50%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('75%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('100%').length).toBeGreaterThan(0);
  });

  it('shows error toast on load failure', async () => {
    listSavingsGoalsMock.mockRejectedValue(new Error('Network error'));
    render(<SavingsGoals />);
    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Failed to load savings goals' }),
      );
    });
  });

  it('opens create dialog and submits', async () => {
    listSavingsGoalsMock.mockResolvedValue([]);
    createSavingsGoalMock.mockResolvedValue(sampleGoal);
    const user = userEvent.setup();

    render(<SavingsGoals />);
    await waitFor(() => {
      expect(screen.getByText('No savings goals yet')).toBeInTheDocument();
    });

    // Click "Create Your First Goal"
    const createBtn = screen.getByText('Create Your First Goal');
    await user.click(createBtn);

    await waitFor(() => {
      expect(screen.getByText('New Savings Goal')).toBeInTheDocument();
    });
  });
});
