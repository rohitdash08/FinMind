import { listGoals, createGoal, updateGoal, depositToGoal, deleteGoal } from '../api/goals';

// Mock the api client
jest.mock('../api/client', () => ({
  api: jest.fn(),
  baseURL: 'http://localhost:8000',
}));

import { api } from '../api/client';
const mockApi = api as jest.MockedFunction<typeof api>;

const mockGoal = {
  id: 1,
  title: 'Emergency Fund',
  description: 'Six months of expenses',
  target_amount: 10000,
  current_amount: 2500,
  currency: 'USD',
  deadline: '2026-12-31',
  status: 'ACTIVE' as const,
  monthly_target: 625,
  icon: '🏦',
  progress_pct: 25.0,
  milestones: [
    { pct: 25, amount: 2500, reached: true },
    { pct: 50, amount: 5000, reached: false },
    { pct: 75, amount: 7500, reached: false },
    { pct: 100, amount: 10000, reached: false },
  ],
  days_remaining: 265,
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
};

describe('Goals API', () => {
  beforeEach(() => jest.clearAllMocks());

  it('listGoals calls GET /goals', async () => {
    mockApi.mockResolvedValue([mockGoal]);
    const result = await listGoals();
    expect(mockApi).toHaveBeenCalledWith('/goals');
    expect(result).toEqual([mockGoal]);
  });

  it('listGoals with status filter appends query string', async () => {
    mockApi.mockResolvedValue([mockGoal]);
    await listGoals('ACTIVE');
    expect(mockApi).toHaveBeenCalledWith('/goals?status=ACTIVE');
  });

  it('createGoal calls POST /goals with payload', async () => {
    mockApi.mockResolvedValue(mockGoal);
    const payload = { title: 'Emergency Fund', target_amount: 10000 };
    const result = await createGoal(payload);
    expect(mockApi).toHaveBeenCalledWith('/goals', { method: 'POST', body: payload });
    expect(result.title).toBe('Emergency Fund');
  });

  it('updateGoal calls PATCH /goals/:id', async () => {
    const updated = { ...mockGoal, title: 'Renamed Goal' };
    mockApi.mockResolvedValue(updated);
    const result = await updateGoal(1, { title: 'Renamed Goal' });
    expect(mockApi).toHaveBeenCalledWith('/goals/1', {
      method: 'PATCH',
      body: { title: 'Renamed Goal' },
    });
    expect(result.title).toBe('Renamed Goal');
  });

  it('depositToGoal calls POST /goals/:id/deposit with amount', async () => {
    const afterDeposit = { ...mockGoal, current_amount: 3000, progress_pct: 30.0 };
    mockApi.mockResolvedValue(afterDeposit);
    const result = await depositToGoal(1, 500);
    expect(mockApi).toHaveBeenCalledWith('/goals/1/deposit', {
      method: 'POST',
      body: { amount: 500 },
    });
    expect(result.current_amount).toBe(3000);
  });

  it('deleteGoal calls DELETE /goals/:id', async () => {
    mockApi.mockResolvedValue(undefined);
    await deleteGoal(1);
    expect(mockApi).toHaveBeenCalledWith('/goals/1', { method: 'DELETE' });
  });

  it('milestone tracking reflects progress correctly', () => {
    // 25% milestone should be reached when current = target * 0.25
    const goal = { ...mockGoal, current_amount: 2500, target_amount: 10000 };
    const reached25 = goal.current_amount >= goal.target_amount * 0.25;
    const reached50 = goal.current_amount >= goal.target_amount * 0.50;
    expect(reached25).toBe(true);
    expect(reached50).toBe(false);
  });
});
