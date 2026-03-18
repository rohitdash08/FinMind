export interface SavingsGoal {
  id: string;
  name: string;
  targetAmount: number;
  currentAmount: number;
  deadline: Date;
  milestones: SavingsMilestone[];
  status: 'active' | 'completed' | 'paused' | 'cancelled';
}

export interface SavingsMilestone {
  id: string;
  amount: number;
  description: string;
  targetDate: Date;
  isCompleted: boolean;
  completedDate?: Date;
}

export interface SavingsProgress {
  percentage: number;
  remainingAmount: number;
  daysRemaining: number;
  averageDailySavingsNeeded: number;
}