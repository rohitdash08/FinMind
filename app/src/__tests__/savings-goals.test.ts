import {
  listSavingsGoals,
  getSavingsGoal,
  createSavingsGoal,
  updateSavingsGoal,
  deleteSavingsGoal,
  addToSavingsGoal,
  withdrawFromSavingsGoal,
  listMilestones,
  createMilestone,
  deleteMilestone,
  getGoalProgress,
  type SavingsGoal,
  type GoalMilestone,
} from '../api/savings-goals';
import * as client from '../api/client';

// Mock the API client
jest.mock('../api/client', () => ({
  api: jest.fn(),
  baseURL: 'http://localhost:3000/api',
}));

const mockGoal: SavingsGoal = {
  id: 1,
  name: 'Emergency Fund',
  description: 'Save for 6 months of expenses',
  target_amount: 10000,
  current_amount: 5000,
  currency: 'USD',
  deadline: '2026-12-31',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
};

const mockMilestone: GoalMilestone = {
  id: 1,
  goal_id: 1,
  name: '25% Milestone',
  target_percentage: 25,
  achieved: true,
  achieved_at: '2026-02-15T00:00:00Z',
};

describe('savings-goals API', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('listSavingsGoals', () => {
    it('fetches all savings goals', async () => {
      const mockGoals = [mockGoal];
      (client.api as jest.Mock).mockResolvedValueOnce(mockGoals);

      const result = await listSavingsGoals();

      expect(client.api).toHaveBeenCalledWith('/savings-goals');
      expect(result).toEqual(mockGoals);
    });

    it('filters by active status', async () => {
      const mockGoals = [mockGoal];
      (client.api as jest.Mock).mockResolvedValueOnce(mockGoals);

      const result = await listSavingsGoals({ active: true });

      expect(client.api).toHaveBeenCalledWith('/savings-goals?active=true');
      expect(result).toEqual(mockGoals);
    });

    it('searches by name', async () => {
      const mockGoals = [mockGoal];
      (client.api as jest.Mock).mockResolvedValueOnce(mockGoals);

      const result = await listSavingsGoals({ search: 'emergency' });

      expect(client.api).toHaveBeenCalledWith('/savings-goals?search=emergency');
      expect(result).toEqual(mockGoals);
    });
  });

  describe('getSavingsGoal', () => {
    it('fetches a single goal by ID', async () => {
      (client.api as jest.Mock).mockResolvedValueOnce(mockGoal);

      const result = await getSavingsGoal(1);

      expect(client.api).toHaveBeenCalledWith('/savings-goals/1');
      expect(result).toEqual(mockGoal);
    });
  });

  describe('createSavingsGoal', () => {
    it('creates a new savings goal', async () => {
      const payload = {
        name: 'Vacation Fund',
        target_amount: 3000,
        deadline: '2026-06-30',
      };
      const created = { ...mockGoal, ...payload, id: 2 };
      (client.api as jest.Mock).mockResolvedValueOnce(created);

      const result = await createSavingsGoal(payload);

      expect(client.api).toHaveBeenCalledWith('/savings-goals', {
        method: 'POST',
        body: payload,
      });
      expect(result).toEqual(created);
    });

    it('creates a goal with optional fields', async () => {
      const payload = {
        name: 'New Car',
        description: 'Down payment',
        target_amount: 15000,
        current_amount: 2000,
        currency: 'USD',
        deadline: '2027-01-01',
      };
      (client.api as jest.Mock).mockResolvedValueOnce({ ...mockGoal, ...payload });

      const result = await createSavingsGoal(payload);

      expect(client.api).toHaveBeenCalledWith('/savings-goals', {
        method: 'POST',
        body: payload,
      });
    });
  });

  describe('updateSavingsGoal', () => {
    it('updates an existing goal', async () => {
      const update = { target_amount: 12000 };
      const updated = { ...mockGoal, ...update };
      (client.api as jest.Mock).mockResolvedValueOnce(updated);

      const result = await updateSavingsGoal(1, update);

      expect(client.api).toHaveBeenCalledWith('/savings-goals/1', {
        method: 'PATCH',
        body: update,
      });
      expect(result.target_amount).toBe(12000);
    });
  });

  describe('deleteSavingsGoal', () => {
    it('deletes a goal', async () => {
      const response = { message: 'Goal deleted' };
      (client.api as jest.Mock).mockResolvedValueOnce(response);

      const result = await deleteSavingsGoal(1);

      expect(client.api).toHaveBeenCalledWith('/savings-goals/1', {
        method: 'DELETE',
      });
      expect(result).toEqual(response);
    });
  });

  describe('addToSavingsGoal', () => {
    it('adds funds to a goal', async () => {
      const updated = { ...mockGoal, current_amount: 5500 };
      (client.api as jest.Mock).mockResolvedValueOnce(updated);

      const result = await addToSavingsGoal(1, 500);

      expect(client.api).toHaveBeenCalledWith('/savings-goals/1/add', {
        method: 'POST',
        body: { amount: 500 },
      });
      expect(result.current_amount).toBe(5500);
    });
  });

  describe('withdrawFromSavingsGoal', () => {
    it('withdraws funds from a goal', async () => {
      const updated = { ...mockGoal, current_amount: 4500 };
      (client.api as jest.Mock).mockResolvedValueOnce(updated);

      const result = await withdrawFromSavingsGoal(1, 500);

      expect(client.api).toHaveBeenCalledWith('/savings-goals/1/withdraw', {
        method: 'POST',
        body: { amount: 500 },
      });
      expect(result.current_amount).toBe(4500);
    });
  });

  describe('Milestones', () => {
    describe('listMilestones', () => {
      it('lists milestones for a goal', async () => {
        const mockMilestones = [mockMilestone];
        (client.api as jest.Mock).mockResolvedValueOnce(mockMilestones);

        const result = await listMilestones(1);

        expect(client.api).toHaveBeenCalledWith('/savings-goals/1/milestones');
        expect(result).toEqual(mockMilestones);
      });
    });

    describe('createMilestone', () => {
      it('creates a milestone', async () => {
        const payload = {
          goal_id: 1,
          name: '50% Milestone',
          target_percentage: 50,
        };
        const created = { ...mockMilestone, ...payload, id: 2 };
        (client.api as jest.Mock).mockResolvedValueOnce(created);

        const result = await createMilestone(payload);

        expect(client.api).toHaveBeenCalledWith('/savings-goals/milestones', {
          method: 'POST',
          body: payload,
        });
        expect(result).toEqual(created);
      });
    });

    describe('deleteMilestone', () => {
      it('deletes a milestone', async () => {
        const response = { message: 'Milestone deleted' };
        (client.api as jest.Mock).mockResolvedValueOnce(response);

        const result = await deleteMilestone(1);

        expect(client.api).toHaveBeenCalledWith('/savings-goals/milestones/1', {
          method: 'DELETE',
        });
        expect(result).toEqual(response);
      });
    });
  });

  describe('getGoalProgress', () => {
    it('calculates goal progress metrics', async () => {
      const progress = {
        percentage: 50,
        remaining: 5000,
        days_left: 300,
        on_track: true,
        required_daily_saving: 16.67,
      };
      (client.api as jest.Mock).mockResolvedValueOnce(progress);

      const result = await getGoalProgress(1);

      expect(client.api).toHaveBeenCalledWith('/savings-goals/1/progress');
      expect(result).toEqual(progress);
      expect(result.percentage).toBe(50);
      expect(result.on_track).toBe(true);
    });

    it('handles goals without deadlines', async () => {
      const progress = {
        percentage: 50,
        remaining: 5000,
        on_track: true,
      };
      (client.api as jest.Mock).mockResolvedValueOnce(progress);

      const result = await getGoalProgress(2);

      expect(result.days_left).toBeUndefined();
      expect(result.required_daily_saving).toBeUndefined();
    });
  });

  describe('Edge Cases', () => {
    it('handles zero target amount', async () => {
      const zeroGoal = { ...mockGoal, target_amount: 0 };
      (client.api as jest.Mock).mockResolvedValueOnce(zeroGoal);

      const result = await getSavingsGoal(99);

      expect(result.target_amount).toBe(0);
    });

    it('handles completed goals', async () => {
      const completedGoal = { ...mockGoal, current_amount: 10000 };
      (client.api as jest.Mock).mockResolvedValueOnce(completedGoal);

      const result = await getSavingsGoal(1);

      expect(result.current_amount).toBe(result.target_amount);
    });

    it('handles overdue goals', async () => {
      const overdueGoal = { ...mockGoal, deadline: '2020-01-01' };
      (client.api as jest.Mock).mockResolvedValueOnce(overdueGoal);

      const result = await getSavingsGoal(1);

      expect(new Date(result.deadline!).getTime()).toBeLessThan(Date.now());
    });
  });
});
