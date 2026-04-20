import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Savings } from '../pages/Savings';

// Mock the savings API
vi.mock('../api/savings', () => ({
  listSavingsGoals: vi.fn(),
  createSavingsGoal: vi.fn(),
  updateSavingsGoal: vi.fn(),
  deleteSavingsGoal: vi.fn(),
  addSavingsContribution: vi.fn(),
  listSavingsMilestones: vi.fn(),
  createSavingsMilestone: vi.fn(),
  updateSavingsMilestone: vi.fn(),
}));

const mockGoals = [
  {
    id: 1,
    title: 'Emergency Fund',
    target_amount: 10000,
    current_amount: 7250,
    deadline: '2025-12-31',
    monthly_target: 458,
    status: 'on-track' as const,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-04-15T00:00:00Z',
  },
  {
    id: 2,
    title: 'Vacation Fund',
    target_amount: 3000,
    current_amount: 1850,
    deadline: '2025-06-30',
    monthly_target: 383,
    status: 'behind' as const,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-04-15T00:00:00Z',
  },
];

const mockMilestones: Record<number, any[]> = {
  1: [
    { id: 1, goal_id: 1, title: '$2,500 saved', target_amount: 2500, achieved: true, achieved_at: '2025-02-15T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
    { id: 2, goal_id: 1, title: '$5,000 saved', target_amount: 5000, achieved: true, achieved_at: '2025-03-20T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
  ],
  2: [
    { id: 3, goal_id: 2, title: '$1,000 saved', target_amount: 1000, achieved: true, achieved_at: '2025-02-28T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
  ],
};

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{ui}</BrowserRouter>
    </QueryClientProvider>
  );
}

describe('Savings page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the savings page title', async () => {
    const { listSavingsGoals, listSavingsMilestones } = await import('../api/savings');
    vi.mocked(listSavingsGoals).mockRejectedValueOnce(new Error('API not available'));
    vi.mocked(listSavingsMilestones).mockRejectedValue(new Error('API not available'));

    renderWithProviders(<Savings />);
    expect(screen.getByText('Savings Goals')).toBeTruthy();
  });

  it('displays overview cards with correct totals', async () => {
    const { listSavingsGoals, listSavingsMilestones } = await import('../api/savings');
    vi.mocked(listSavingsGoals).mockRejectedValueOnce(new Error('API not available'));
    vi.mocked(listSavingsMilestones).mockRejectedValue(new Error('API not available'));

    renderWithProviders(<Savings />);
    
    await waitFor(() => {
      expect(screen.getByText(/\$9,100/)).toBeTruthy(); // Total saved
    });
    expect(screen.getByText(/\$13,000/)).toBeTruthy(); // Total target
  });

  it('renders goal cards with progress bars', async () => {
    const { listSavingsGoals, listSavingsMilestones } = await import('../api/savings');
    vi.mocked(listSavingsGoals).mockRejectedValueOnce(new Error('API not available'));
    vi.mocked(listSavingsMilestones).mockRejectedValue(new Error('API not available'));

    renderWithProviders(<Savings />);

    await waitFor(() => {
      expect(screen.getByText('Emergency Fund')).toBeTruthy();
      expect(screen.getByText('Vacation Fund')).toBeTruthy();
    });
  });

  it('shows milestones section when goals have milestones', async () => {
    const { listSavingsGoals, listSavingsMilestones } = await import('../api/savings');
    vi.mocked(listSavingsGoals).mockRejectedValueOnce(new Error('API not available'));
    vi.mocked(listSavingsMilestones).mockRejectedValue(new Error('API not available'));

    renderWithProviders(<Savings />);

    await waitFor(() => {
      expect(screen.getByText('Milestones')).toBeTruthy();
    });
  });

  it('opens create goal dialog when clicking New Goal button', async () => {
    const { listSavingsGoals, listSavingsMilestones } = await import('../api/savings');
    vi.mocked(listSavingsGoals).mockRejectedValueOnce(new Error('API not available'));
    vi.mocked(listSavingsMilestones).mockRejectedValue(new Error('API not available'));

    renderWithProviders(<Savings />);

    const newGoalButton = screen.getByRole('button', { name: /New Goal/i });
    fireEvent.click(newGoalButton);

    await waitFor(() => {
      expect(screen.getByText('Create Savings Goal')).toBeTruthy();
    });
  });

  it('displays empty state when no goals exist', async () => {
    const { listSavingsGoals, listSavingsMilestones } = await import('../api/savings');
    vi.mocked(listSavingsGoals).mockResolvedValue([]);
    vi.mocked(listSavingsMilestones).mockResolvedValue([]);

    renderWithProviders(<Savings />);

    await waitFor(() => {
      expect(screen.getByText('No savings goals yet')).toBeTruthy();
    });
  });

  it('displays goal status badges correctly', async () => {
    const { listSavingsGoals, listSavingsMilestones } = await import('../api/savings');
    vi.mocked(listSavingsGoals).mockRejectedValueOnce(new Error('API not available'));
    vi.mocked(listSavingsMilestones).mockRejectedValue(new Error('API not available'));

    renderWithProviders(<Savings />);

    await waitFor(() => {
      expect(screen.getByText('On Track')).toBeTruthy();
      expect(screen.getByText('Behind')).toBeTruthy();
    });
  });
});
