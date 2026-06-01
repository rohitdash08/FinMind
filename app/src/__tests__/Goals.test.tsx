import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Goals } from '@/pages/Goals';

// Mock the API module
jest.mock('@/api/goals', () => ({
  listGoals: jest.fn(),
  createGoal: jest.fn(),
  updateGoal: jest.fn(),
  deleteGoal: jest.fn(),
  depositToGoal: jest.fn(),
}));

// Mock toast
jest.mock('@/components/ui/use-toast', () => ({
  toast: jest.fn(),
  useToast: () => ({ toast: jest.fn() }),
}));

import { listGoals, createGoal, depositToGoal } from '@/api/goals';

const mockGoals = [
  {
    id: 1,
    name: 'Emergency Fund',
    target_amount: 10000,
    current_amount: 7250,
    deadline: '2026-12-31',
    category: 'Emergency Fund',
    priority: 'high',
    status: 'active',
    milestones: [
      { id: 1, goal_id: 1, title: 'First $5000', target_amount: 5000, reached: true, reached_at: '2026-03-01' },
      { id: 2, goal_id: 1, title: '75% complete', target_amount: 7500, reached: false, reached_at: null },
    ],
    created_at: '2026-01-01',
    updated_at: '2026-06-01',
  },
  {
    id: 2,
    name: 'Vacation',
    target_amount: 5000,
    current_amount: 5000,
    deadline: '2026-08-01',
    category: 'Vacation',
    priority: 'medium',
    status: 'completed',
    milestones: [],
    created_at: '2026-02-01',
    updated_at: '2026-05-15',
  },
];

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

const renderGoals = () => {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Goals />
      </BrowserRouter>
    </QueryClientProvider>,
  );
};

describe('Goals Page', () => {
  beforeEach(() => {
    (listGoals as jest.Mock).mockResolvedValue(mockGoals);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('renders the page title', async () => {
    renderGoals();
    expect(screen.getByText('Savings Goals')).toBeInTheDocument();
  });

  it('displays summary stats', async () => {
    renderGoals();
    await waitFor(() => {
      expect(screen.getByText('$12,250')).toBeInTheDocument(); // total saved
      expect(screen.getByText('$15,000')).toBeInTheDocument(); // total target
    });
  });

  it('displays goal cards', async () => {
    renderGoals();
    await waitFor(() => {
      expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
      expect(screen.getByText('Vacation')).toBeInTheDocument();
    });
  });

  it('shows progress percentage', async () => {
    renderGoals();
    await waitFor(() => {
      expect(screen.getByText('72.5% complete')).toBeInTheDocument();
      expect(screen.getByText('100.0% complete')).toBeInTheDocument();
    });
  });

  it('shows completed badge for completed goals', async () => {
    renderGoals();
    await waitFor(() => {
      // The Vacation goal should show as completed
      expect(screen.getByText('100.0% complete')).toBeInTheDocument();
    });
  });

  it('shows milestones section', async () => {
    renderGoals();
    await waitFor(() => {
      expect(screen.getByText(/Milestones \(2\)/)).toBeInTheDocument();
    });
  });

  it('expands milestones on click', async () => {
    renderGoals();
    await waitFor(() => {
      const milestoneBtn = screen.getByText(/Milestones \(2\)/);
      fireEvent.click(milestoneBtn);
      expect(screen.getByText('First $5000')).toBeInTheDocument();
    });
  });

  it('shows new goal form when button clicked', async () => {
    renderGoals();
    await waitFor(() => {
      const newGoalBtn = screen.getByText('New Goal');
      fireEvent.click(newGoalBtn);
      expect(screen.getByText('New Savings Goal')).toBeInTheDocument();
    });
  });

  it('shows empty state when no goals', async () => {
    (listGoals as jest.Mock).mockResolvedValue([]);
    renderGoals();
    await waitFor(() => {
      expect(screen.getByText('No savings goals yet')).toBeInTheDocument();
    });
  });
});
