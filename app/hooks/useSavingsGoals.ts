import { useState, useEffect, useCallback } from 'react';

export interface SavingsGoal {
  id: string;
  name: string;
  targetAmount: number;
  currentAmount: number;
  targetDate: string;
  category: string;
  description?: string;
  milestones: Milestone[];
  createdAt: string;
  updatedAt: string;
}

export interface Milestone {
  id: string;
  percentage: number;
  amount: number;
  description: string;
  achieved: boolean;
  achievedAt?: string;
}

const STORAGE_KEY = 'savings_goals';

const generateId = () => Math.random().toString(36).substr(2, 9);

const createDefaultMilestones = (targetAmount: number): Milestone[] => [
  { id: generateId(), percentage: 25, amount: targetAmount * 0.25, description: '25% Complete', achieved: false },
  { id: generateId(), percentage: 50, amount: targetAmount * 0.50, description: '50% Complete', achieved: false },
  { id: generateId(), percentage: 75, amount: targetAmount * 0.75, description: '75% Complete', achieved: false },
  { id: generateId(), percentage: 100, amount: targetAmount, description: 'Goal Achieved!', achieved: false }
];

export const useSavingsGoals = () => {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);

  // Load goals from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsedGoals = JSON.parse(stored);
        setGoals(parsedGoals);
      } catch (error) {
        console.error('Error parsing stored goals:', error);
      }
    }
    setLoading(false);
  }, []);

  // Save goals to localStorage whenever goals change
  useEffect(() => {
    if (!loading) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(goals));
    }
  }, [goals, loading]);

  const calculateProgress = useCallback((currentAmount: number, targetAmount: number) => {
    if (targetAmount === 0) return 0;
    return Math.min((currentAmount / targetAmount) * 100, 100);
  }, []);

  const updateMilestones = useCallback((currentAmount: number, milestones: Milestone[]) => {
    return milestones.map(milestone => {
      const shouldBeAchieved = currentAmount >= milestone.amount;
      if (shouldBeAchieved && !milestone.achieved) {
        return {
          ...milestone,
          achieved: true,
          achievedAt: new Date().toISOString()
        };
      }
      if (!shouldBeAchieved && milestone.achieved) {
        return {
          ...milestone,
          achieved: false,
          achievedAt: undefined
        };
      }
      return milestone;
    });
  }, []);

  const createGoal = useCallback((goalData: Omit<SavingsGoal, 'id' | 'milestones' | 'createdAt' | 'updatedAt'>) => {
    const newGoal: SavingsGoal = {
      ...goalData,
      id: generateId(),
      milestones: createDefaultMilestones(goalData.targetAmount),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    // Update milestones based on current amount
    newGoal.milestones = updateMilestones(newGoal.currentAmount, newGoal.milestones);

    setGoals(prev => [...prev, newGoal]);
    return newGoal;
  }, [updateMilestones]);

  const updateGoal = useCallback((id: string, updates: Partial<Omit<SavingsGoal, 'id' | 'createdAt'>>) => {
    setGoals(prev => prev.map(goal => {
      if (goal.id !== id) return goal;

      const updatedGoal = {
        ...goal,
        ...updates,
        updatedAt: new Date().toISOString()
      };

      // Regenerate milestones if target amount changed
      if (updates.targetAmount && updates.targetAmount !== goal.targetAmount) {
        updatedGoal.milestones = createDefaultMilestones(updates.targetAmount);
      }

      // Update milestone achievements based on current amount
      if (updates.currentAmount !== undefined || updates.targetAmount) {
        updatedGoal.milestones = updateMilestones(
          updates.currentAmount ?? goal.currentAmount,
          updatedGoal.milestones
        );
      }

      return updatedGoal;
    }));
  }, [updateMilestones]);

  const deleteGoal = useCallback((id: string) => {
    setGoals(prev => prev.filter(goal => goal.id !== id));
  }, []);

  const addToGoal = useCallback((id: string, amount: number) => {
    updateGoal(id, {
      currentAmount: goals.find(g => g.id === id)?.currentAmount + amount || amount
    });
  }, [goals, updateGoal]);

  const getGoalById = useCallback((id: string) => {
    return goals.find(goal => goal.id === id);
  }, [goals]);

  const getGoalsByCategory = useCallback((category: string) => {
    return goals.filter(goal => goal.category === category);
  }, [goals]);

  const getCompletedGoals = useCallback(() => {
    return goals.filter(goal => goal.currentAmount >= goal.targetAmount);
  }, [goals]);

  const getActiveGoals = useCallback(() => {
    return goals.filter(goal => goal.currentAmount < goal.targetAmount);
  }, [goals]);

  const getOverdueGoals = useCallback(() => {
    const now = new Date();
    return goals.filter(goal => 
      new Date(goal.targetDate) < now && goal.currentAmount < goal.targetAmount
    );
  }, [goals]);

  const getTotalSaved = useCallback(() => {
    return goals.reduce((total, goal) => total + goal.currentAmount, 0);
  }, [goals]);

  const getTotalTarget = useCallback(() => {
    return goals.reduce((total, goal) => total + goal.targetAmount, 0);
  }, [goals]);

  const getOverallProgress = useCallback(() => {
    const totalTarget = getTotalTarget();
    if (totalTarget === 0) return 0;
    return (getTotalSaved() / totalTarget) * 100;
  }, [getTotalSaved, getTotalTarget]);

  const getNextMilestone = useCallback((goalId: string) => {
    const goal = getGoalById(goalId);
    if (!goal) return null;
    
    return goal.milestones.find(milestone => !milestone.achieved);
  }, [getGoalById]);

  const getAchievedMilestones = useCallback((goalId: string) => {
    const goal = getGoalById(goalId);
    if (!goal) return [];
    
    return goal.milestones.filter(milestone => milestone.achieved);
  }, [getGoalById]);

  return {
    goals,
    loading,
    createGoal,
    updateGoal,
    deleteGoal,
    addToGoal,
    getGoalById,
    getGoalsByCategory,
    getCompletedGoals,
    getActiveGoals,
    getOverdueGoals,
    getTotalSaved,
    getTotalTarget,
    getOverallProgress,
    getNextMilestone,
    getAchievedMilestones,
    calculateProgress
  };
};