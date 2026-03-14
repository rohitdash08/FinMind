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
  Badge: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLSpanElement>) => (
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
  FinancialCardContent: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  FinancialCardDescription: ({ children, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
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
  formatMoney: (amount: number) => `$${Number(amount || 0).toFixed(2)}`,
}));

const listSavingsGoalsMock = jest.fn();
const createSavingsGoalMock = jest.fn();
const updateSavingsGoalMock = jest.fn();
const deleteSavingsGoalMock = jest.fn();
const addContributionMock = jest.fn();
const withdrawFromGoalMock = jest.fn();
jest.mock('@/api/savings-goals', () => ({
  listSavingsGoals: (...args: unknown[]) => listSavingsGoalsMock(...args),
  createSavingsGoal: (...args: unknown[]) => createSavingsGoalMock(...args),
  updateSavingsGoal: (...args: unknown[]) => updateSavingsGoalMock(...args),
  deleteSavingsGoal: (...args: unknown[]) => deleteSavingsGoalMock(...args),
  addContribution: (...args: unknown[]) => addContributionMock(...args),
  withdrawFromGoal: (...args: unknown[]) => withdrawFromGoalMock(...args),
}));

const sampleGoal = {
  id: 1,
  name: 'Emergency Fund',
  target_amount: 5000,
  current_amount: 1250,
  currency: 'USD',
  target_date: '2025-12-31',
  icon: 'piggy-bank',
  active: true,
  progress_pct: 25,
  milestones_achieved: [25],
  created_at: '2025-01-01T00:00:00',
};

describe('SavingsGoals integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    listSavingsGoalsMock.mockResolvedValue([sampleGoal]);
    createSavingsGoalMock.mockResolvedValue({ ...sampleGoal, id: 2, name: 'Vacation' });
    deleteSavingsGoalMock.mockResolvedValue({ message: 'deleted' });
  });

  it('renders goals list with progress and milestones', async () => {
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalled());

    expect(await screen.findByText('Emergency Fund')).toBeInTheDocument();
    expect(screen.getByText('$1250.00')).toBeInTheDocument();

    // Milestone badge
    expect(screen.getByText('25%')).toBeInTheDocument();

    // Progress bar
    const progressBars = screen.getAllByRole('progressbar');
    expect(progressBars.length).toBeGreaterThan(0);
  });

  it('shows empty state when no goals', async () => {
    listSavingsGoalsMock.mockResolvedValue([]);
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalled());

    expect(await screen.findByText(/no savings goals yet/i)).toBeInTheDocument();
    expect(screen.getByText(/create your first goal/i)).toBeInTheDocument();
  });

  it('shows summary stats', async () => {
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalled());

    // Total saved
    expect(await screen.findByText('$1250.00')).toBeInTheDocument();
    // Total target
    expect(screen.getByText('$5000.00')).toBeInTheDocument();
  });

  it('deletes a goal when confirmed', async () => {
    render(<SavingsGoals />);
    await waitFor(() => expect(listSavingsGoalsMock).toHaveBeenCalled());
    await screen.findByText('Emergency Fund');

    // Click the delete confirmation button
    const deleteButtons = screen.getAllByText('Delete');
    await userEvent.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => expect(deleteSavingsGoalMock).toHaveBeenCalledWith(1));
    expect(toastMock).toHaveBeenCalledWith({ title: 'Goal deleted' });
  });
});
