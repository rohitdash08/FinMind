import { useEffect, useMemo, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  AlertCircle,
  Calendar,
  DollarSign,
  PieChart,
  Plus,
  Settings,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { formatMoney } from '@/lib/currency';
import {
  createSavingsGoal,
  getGoalMilestones,
  getGoalProgress,
  getGoalRemaining,
  getGoalStatus,
  getRequiredMonthlyContribution,
  loadSavingsGoals,
  saveSavingsGoals,
  type SavingsGoal,
} from '@/lib/savingsGoals';

const budgetCategories = [
  {
    id: 1,
    name: 'Housing',
    allocated: 2000,
    spent: 1850,
    remaining: 150,
    color: 'bg-primary',
    trend: 'up',
    change: '+2.3%',
  },
  {
    id: 2,
    name: 'Food & Dining',
    allocated: 800,
    spent: 720,
    remaining: 80,
    color: 'bg-success',
    trend: 'down',
    change: '-5.1%',
  },
  {
    id: 3,
    name: 'Transportation',
    allocated: 400,
    spent: 445,
    remaining: -45,
    color: 'bg-destructive',
    trend: 'up',
    change: '+11.3%',
  },
  {
    id: 4,
    name: 'Entertainment',
    allocated: 300,
    spent: 185,
    remaining: 115,
    color: 'bg-accent',
    trend: 'down',
    change: '-8.2%',
  },
  {
    id: 5,
    name: 'Healthcare',
    allocated: 250,
    spent: 165,
    remaining: 85,
    color: 'bg-warning',
    trend: 'up',
    change: '+3.1%',
  },
  {
    id: 6,
    name: 'Shopping',
    allocated: 500,
    spent: 380,
    remaining: 120,
    color: 'bg-secondary',
    trend: 'down',
    change: '-12.4%',
  },
];

function formatDeadline(date: string) {
  return new Date(date).toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
  });
}

function getGoalProgressBarClass(status: ReturnType<typeof getGoalStatus>) {
  switch (status) {
    case 'completed':
      return 'chart-fill-success';
    case 'ahead':
      return 'chart-fill-primary';
    case 'on-track':
      return 'chart-fill-success';
    case 'behind':
      return 'chart-fill-danger';
    default:
      return 'chart-fill-primary';
  }
}

export function Budgets() {
  const [selectedPeriod] = useState('monthly');
  const [goals, setGoals] = useState<SavingsGoal[]>(() => loadSavingsGoals());
  const [goalTitle, setGoalTitle] = useState('');
  const [goalTarget, setGoalTarget] = useState('');
  const [goalCurrent, setGoalCurrent] = useState('0');
  const [goalTargetDate, setGoalTargetDate] = useState(() => new Date().toISOString().slice(0, 10));

  useEffect(() => {
    saveSavingsGoals(goals);
  }, [goals]);

  const totalAllocated = budgetCategories.reduce((sum, cat) => sum + cat.allocated, 0);
  const totalSpent = budgetCategories.reduce((sum, cat) => sum + cat.spent, 0);
  const totalRemaining = totalAllocated - totalSpent;

  const goalSummary = useMemo(() => {
    const totalTarget = goals.reduce((sum, goal) => sum + goal.target, 0);
    const totalSaved = goals.reduce((sum, goal) => sum + goal.current, 0);
    const totalMonthlyTarget = goals.reduce(
      (sum, goal) => sum + getRequiredMonthlyContribution(goal),
      0,
    );

    return {
      totalTarget,
      totalSaved,
      totalMonthlyTarget,
      completedGoals: goals.filter((goal) => getGoalStatus(goal) === 'completed').length,
    };
  }, [goals]);

  const goalCards = useMemo(
    () =>
      goals.map((goal) => {
        const status = getGoalStatus(goal);
        const progress = getGoalProgress(goal);
        const remaining = getGoalRemaining(goal);
        const monthlyTarget = getRequiredMonthlyContribution(goal);
        const milestones = getGoalMilestones(goal);
        const nextMilestone = milestones.find((milestone) => !milestone.reached);

        return {
          ...goal,
          status,
          progress,
          remaining,
          monthlyTarget,
          milestones,
          nextMilestone,
        };
      }),
    [goals],
  );

  function onAddGoal() {
    if (!goalTitle.trim() || !goalTarget || !goalTargetDate) {
      return;
    }

    const nextGoal = createSavingsGoal({
      title: goalTitle,
      target: Number(goalTarget),
      current: Number(goalCurrent || 0),
      targetDate: goalTargetDate,
    });

    setGoals((currentGoals) => [nextGoal, ...currentGoals]);
    setGoalTitle('');
    setGoalTarget('');
    setGoalCurrent('0');
    setGoalTargetDate(new Date().toISOString().slice(0, 10));
  }

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Budget Management</h1>
            <p className="page-subtitle">
              Track spending, savings goals, and milestone progress from one place
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" size="sm">
              <Calendar className="w-4 h-4" />
              {selectedPeriod === 'monthly' ? 'Monthly' : 'Weekly'}
            </Button>
            <Button variant="financial" size="sm">
              <Plus className="w-4 h-4" />
              New Category
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4 mb-8">
        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Allocated
              </FinancialCardTitle>
              <Target className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{formatMoney(totalAllocated)}</div>
            <div className="text-sm text-muted-foreground">This month's budget</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Spent
              </FinancialCardTitle>
              <DollarSign className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{formatMoney(totalSpent)}</div>
            <div className="text-sm text-muted-foreground">
              {((totalSpent / totalAllocated) * 100).toFixed(1)}% of budget used
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={totalRemaining < 0 ? 'destructive' : 'success'}>
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium">
                {totalRemaining < 0 ? 'Over Budget' : 'Remaining'}
              </FinancialCardTitle>
              {totalRemaining < 0 ? (
                <AlertCircle className="w-5 h-5" />
              ) : (
                <PieChart className="w-5 h-5" />
              )}
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value mb-1">{formatMoney(Math.abs(totalRemaining))}</div>
            <div className="text-sm opacity-80">
              {totalRemaining < 0 ? 'Overspent this month' : 'Available to spend'}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Saved Toward Goals
              </FinancialCardTitle>
              <Target className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{formatMoney(goalSummary.totalSaved)}</div>
            <div className="text-sm text-muted-foreground">
              {goalSummary.completedGoals} completed, {formatMoney(goalSummary.totalMonthlyTarget)}/mo target
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-3 mb-8">
        <div className="lg:col-span-2">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="section-title">Budget Categories</FinancialCardTitle>
                <Button variant="ghost" size="sm">
                  <Settings className="w-4 h-4" />
                </Button>
              </div>
              <FinancialCardDescription>
                Track spending across different categories
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="space-y-6">
                {budgetCategories.map((category) => {
                  const percentage = (category.spent / category.allocated) * 100;
                  const isOverBudget = category.remaining < 0;

                  return (
                    <div key={category.id} className="space-y-3 interactive-row">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <div className={`w-4 h-4 rounded-full ${category.color}`}></div>
                          <div>
                            <div className="font-medium text-foreground">{category.name}</div>
                            <div className="text-sm text-muted-foreground">
                              {formatMoney(category.spent)} of {formatMoney(category.allocated)}
                            </div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className={`font-semibold ${isOverBudget ? 'text-destructive' : 'text-foreground'}`}>
                            {isOverBudget ? '-' : ''}
                            {formatMoney(Math.abs(category.remaining))}
                          </div>
                          <div className="flex items-center text-sm">
                            {category.trend === 'up' ? (
                              <TrendingUp className="w-3 h-3 text-destructive mr-1" />
                            ) : (
                              <TrendingDown className="w-3 h-3 text-success mr-1" />
                            )}
                            <span className={category.trend === 'up' ? 'text-destructive' : 'text-success'}>
                              {category.change}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className={`chart-track ${isOverBudget ? 'bg-destructive-light' : ''}`}>
                        <div
                          className={isOverBudget ? 'chart-fill-danger' : 'chart-fill-primary'}
                          style={{ width: `${Math.min(percentage, 100)}%` }}
                        />
                      </div>
                      {isOverBudget && (
                        <Badge variant="destructive" className="text-xs">
                          Over Budget
                        </Badge>
                      )}
                    </div>
                  );
                })}
              </div>
            </FinancialCardContent>
          </FinancialCard>
        </div>

        <div>
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="section-title">Savings Goals</FinancialCardTitle>
                <Badge variant="secondary">{goals.length} active</Badge>
              </div>
              <FinancialCardDescription>
                Track progress, monthly targets, and milestone completion
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="space-y-4">
                {goalCards.length === 0 ? (
                  <div className="text-sm text-muted-foreground">No savings goals yet. Add your first one below.</div>
                ) : (
                  goalCards.map((goal) => (
                    <div key={goal.id} className="interactive-row p-3 sm:p-4 rounded-lg border border-border space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                        <div className="min-w-0">
                          <div className="font-medium text-foreground text-sm">{goal.title}</div>
                          <div className="text-xs text-muted-foreground mt-1">
                            {formatMoney(goal.current)} saved of {formatMoney(goal.target)} target
                          </div>
                        </div>
                        <Badge
                          variant={
                            goal.status === 'completed'
                              ? 'secondary'
                              : goal.status === 'on-track'
                                ? 'default'
                                : goal.status === 'ahead'
                                  ? 'secondary'
                                  : 'destructive'
                          }
                          className="text-xs w-fit"
                        >
                          {goal.status === 'on-track'
                            ? 'On Track'
                            : goal.status === 'ahead'
                              ? 'Ahead'
                              : goal.status === 'completed'
                                ? 'Completed'
                                : 'Behind'}
                        </Badge>
                      </div>

                      <div className="space-y-3">
                        <div className="flex items-center justify-between gap-3 text-sm">
                          <span className="text-muted-foreground">Progress</span>
                          <span className="text-foreground font-semibold" aria-label={`${goal.title} progress percentage`}>
                            {goal.progress.toFixed(0)}%
                          </span>
                        </div>
                        <div className="space-y-2">
                          <div
                            className="chart-track h-3"
                            role="progressbar"
                            aria-label={`${goal.title} progress`}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={Math.round(goal.progress)}
                          >
                            <div
                              className={getGoalProgressBarClass(goal.status)}
                              style={{ width: `${Math.min(goal.progress, 100)}%` }}
                            />
                          </div>
                          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                            <span>0%</span>
                            <span>{goal.nextMilestone ? `Next milestone ${goal.nextMilestone.label}` : 'Goal complete'}</span>
                            <span>100%</span>
                          </div>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-muted-foreground">
                          <span>Target: {formatDeadline(goal.targetDate)}</span>
                          <span className="sm:text-right">{formatMoney(goal.monthlyTarget)}/mo needed</span>
                          <span>Remaining: {formatMoney(goal.remaining)}</span>
                          <span className="sm:text-right">
                            {goal.nextMilestone
                              ? `Next ${goal.nextMilestone.label}: ${formatMoney(goal.nextMilestone.targetAmount)}`
                              : 'All milestones hit'}
                          </span>
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {goal.milestones.map((milestone) => (
                          <Badge
                            key={`${goal.id}-${milestone.label}`}
                            variant={milestone.reached ? 'default' : 'outline'}
                            className="text-[11px]"
                          >
                            {milestone.label}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </FinancialCardContent>
            <FinancialCardFooter>
              <div className="w-full space-y-3">
                <div>
                  <div className="text-sm font-medium text-foreground">Add savings goal</div>
                  <div className="text-xs text-muted-foreground">
                    Goals are saved in-browser so progress and milestones persist locally.
                  </div>
                </div>
                <div className="space-y-3">
                  <div>
                    <label htmlFor="goal-title" className="block text-sm mb-1">Goal name</label>
                    <input
                      id="goal-title"
                      className="input w-full"
                      value={goalTitle}
                      onChange={(event) => setGoalTitle(event.target.value)}
                      placeholder="Emergency fund"
                    />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label htmlFor="goal-target" className="block text-sm mb-1">Target amount</label>
                      <input
                        id="goal-target"
                        className="input w-full"
                        type="number"
                        min="0"
                        step="0.01"
                        value={goalTarget}
                        onChange={(event) => setGoalTarget(event.target.value)}
                        placeholder="10000"
                      />
                    </div>
                    <div>
                      <label htmlFor="goal-current" className="block text-sm mb-1">Saved so far</label>
                      <input
                        id="goal-current"
                        className="input w-full"
                        type="number"
                        min="0"
                        step="0.01"
                        value={goalCurrent}
                        onChange={(event) => setGoalCurrent(event.target.value)}
                        placeholder="0"
                      />
                    </div>
                  </div>
                  <div>
                    <label htmlFor="goal-target-date" className="block text-sm mb-1">Target date</label>
                    <input
                      id="goal-target-date"
                      className="input w-full"
                      type="date"
                      value={goalTargetDate}
                      onChange={(event) => setGoalTargetDate(event.target.value)}
                    />
                  </div>
                </div>
                <Button
                  variant="financial"
                  size="sm"
                  className="w-full"
                  onClick={onAddGoal}
                  disabled={!goalTitle.trim() || !goalTarget || !goalTargetDate}
                >
                  <Plus className="w-4 h-4" />
                  Add New Goal
                </Button>
                <div className="text-xs text-muted-foreground">
                  Total target across goals: {formatMoney(goalSummary.totalTarget)}
                </div>
              </div>
            </FinancialCardFooter>
          </FinancialCard>
        </div>
      </div>
    </div>
  );
}
