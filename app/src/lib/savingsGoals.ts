export type SavingsGoalStatus = 'ahead' | 'on-track' | 'behind' | 'completed';

export type SavingsGoal = {
  id: string;
  title: string;
  target: number;
  current: number;
  targetDate: string;
  createdAt: string;
  updatedAt: string;
};

export type SavingsGoalMilestone = {
  label: string;
  targetAmount: number;
  reached: boolean;
  progress: number;
};

const STORAGE_KEY = 'finmind.savings-goals';
const DEFAULT_MILESTONE_STEPS = [0.25, 0.5, 0.75, 1] as const;

const DEFAULT_GOALS: SavingsGoal[] = [
  {
    id: 'emergency-fund',
    title: 'Emergency Fund',
    target: 10000,
    current: 7250,
    targetDate: '2026-12-31',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'vacation-fund',
    title: 'Vacation Fund',
    target: 3000,
    current: 1850,
    targetDate: '2026-06-30',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
  },
  {
    id: 'new-car',
    title: 'New Car',
    target: 25000,
    current: 15600,
    targetDate: '2027-03-31',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
  },
];

function clampCurrency(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.round(value * 100) / 100);
}

function monthDiff(from: Date, to: Date) {
  const yearDiff = to.getFullYear() - from.getFullYear();
  const monthDiff = to.getMonth() - from.getMonth();
  const raw = yearDiff * 12 + monthDiff;
  return Math.max(1, raw + (to.getDate() >= from.getDate() ? 1 : 0));
}

export function getGoalProgress(goal: SavingsGoal) {
  if (goal.target <= 0) return 0;
  return Math.max(0, Math.min(100, (goal.current / goal.target) * 100));
}

export function getGoalRemaining(goal: SavingsGoal) {
  return clampCurrency(goal.target - goal.current);
}

export function getRequiredMonthlyContribution(goal: SavingsGoal, asOf = new Date()) {
  const remaining = getGoalRemaining(goal);
  if (remaining <= 0) return 0;
  const targetDate = new Date(goal.targetDate);
  const monthsRemaining = monthDiff(asOf, targetDate);
  return clampCurrency(remaining / monthsRemaining);
}

export function getProjectedMonthlyContribution(goal: SavingsGoal, asOf = new Date()) {
  const monthsElapsed = monthDiff(new Date(goal.createdAt), asOf);
  if (monthsElapsed <= 0) {
    return clampCurrency(goal.current);
  }
  return clampCurrency(goal.current / monthsElapsed);
}

export function getGoalStatus(goal: SavingsGoal, asOf = new Date()): SavingsGoalStatus {
  if (goal.current >= goal.target) return 'completed';
  const required = getRequiredMonthlyContribution(goal, asOf);
  const actual = getProjectedMonthlyContribution(goal, asOf);
  if (actual >= required * 1.1) return 'ahead';
  if (actual >= required * 0.9) return 'on-track';
  return 'behind';
}

export function getGoalMilestones(goal: SavingsGoal): SavingsGoalMilestone[] {
  return DEFAULT_MILESTONE_STEPS.map((step) => {
    const targetAmount = clampCurrency(goal.target * step);
    return {
      label: `${Math.round(step * 100)}%`,
      targetAmount,
      reached: goal.current >= targetAmount,
      progress: Math.max(0, Math.min(100, (goal.current / targetAmount) * 100)),
    };
  });
}

export function loadSavingsGoals(): SavingsGoal[] {
  if (typeof window === 'undefined') {
    return DEFAULT_GOALS;
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return DEFAULT_GOALS;
  }

  try {
    const parsed = JSON.parse(raw) as SavingsGoal[];
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return DEFAULT_GOALS;
    }
    return parsed.map((goal) => ({
      ...goal,
      target: clampCurrency(Number(goal.target)),
      current: clampCurrency(Number(goal.current)),
    }));
  } catch {
    return DEFAULT_GOALS;
  }
}

export function saveSavingsGoals(goals: SavingsGoal[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(goals));
}

export function createSavingsGoal(input: Pick<SavingsGoal, 'title' | 'target' | 'current' | 'targetDate'>): SavingsGoal {
  const now = new Date().toISOString();
  return {
    id: `${input.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${Date.now()}`,
    title: input.title.trim(),
    target: clampCurrency(input.target),
    current: clampCurrency(input.current),
    targetDate: input.targetDate,
    createdAt: now,
    updatedAt: now,
  };
}
