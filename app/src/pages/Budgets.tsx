import { useState, useEffect, useCallback } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardFooter, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Calendar, DollarSign, Plus, PieChart, TrendingDown, TrendingUp, Target, AlertCircle, Settings, Loader2, Trash2 } from 'lucide-react';
import { listSavingsGoals, createSavingsGoal, deleteSavingsGoal, updateSavingsGoal } from '@/api/savings-goals';
import type { SavingsGoal as SavingsGoalType } from '@/api/savings-goals';

const budgetCategories = [
  {
    id: 1,
    name: 'Housing',
    allocated: 2000,
    spent: 1850,
    remaining: 150,
    color: 'bg-primary',
    trend: 'up',
    change: '+2.3%'
  },
  {
    id: 2,
    name: 'Food & Dining',
    allocated: 800,
    spent: 720,
    remaining: 80,
    color: 'bg-success',
    trend: 'down',
    change: '-5.1%'
  },
  {
    id: 3,
    name: 'Transportation',
    allocated: 400,
    spent: 445,
    remaining: -45,
    color: 'bg-destructive',
    trend: 'up',
    change: '+11.3%'
  },
  {
    id: 4,
    name: 'Entertainment',
    allocated: 300,
    spent: 185,
    remaining: 115,
    color: 'bg-accent',
    trend: 'down',
    change: '-8.2%'
  },
  {
    id: 5,
    name: 'Healthcare',
    allocated: 250,
    spent: 165,
    remaining: 85,
    color: 'bg-warning',
    trend: 'up',
    change: '+3.1%'
  },
  {
    id: 6,
    name: 'Shopping',
    allocated: 500,
    spent: 380,
    remaining: 120,
    color: 'bg-secondary',
    trend: 'down',
    change: '-12.4%'
  }
];

export function Budgets() {
  const [selectedPeriod] = useState('monthly');
  const [savingsGoals, setSavingsGoals] = useState<SavingsGoalType[]>([]);
  const [goalsLoading, setGoalsLoading] = useState(true);
  const [showGoalForm, setShowGoalForm] = useState(false);
  const [newGoal, setNewGoal] = useState({ title: '', target_amount: '', deadline: '' });

  const fetchGoals = useCallback(async () => {
    try {
      const goals = await listSavingsGoals();
      setSavingsGoals(goals);
    } catch {
      // silently handle - user may not be authenticated
    } finally {
      setGoalsLoading(false);
    }
  }, []);

  useEffect(() => { fetchGoals(); }, [fetchGoals]);

  const handleCreateGoal = async () => {
    if (!newGoal.title || !newGoal.target_amount) return;
    try {
      await createSavingsGoal({
        title: newGoal.title,
        target_amount: parseFloat(newGoal.target_amount),
        deadline: newGoal.deadline || undefined,
      });
      setNewGoal({ title: '', target_amount: '', deadline: '' });
      setShowGoalForm(false);
      fetchGoals();
    } catch {
      // handle error silently
    }
  };

  const handleDeleteGoal = async (id: number) => {
    try {
      await deleteSavingsGoal(id);
      fetchGoals();
    } catch {
      // handle error silently
    }
  };
  
  const totalAllocated = budgetCategories.reduce((sum, cat) => sum + cat.allocated, 0);
  const totalSpent = budgetCategories.reduce((sum, cat) => sum + cat.spent, 0);
  const totalRemaining = totalAllocated - totalSpent;

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Budget Management</h1>
            <p className="page-subtitle">
              Track your spending and stay on top of your financial goals
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

        {/* Budget Overview */}
        <div className="grid gap-4 md:grid-cols-3 mb-8">
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
              <div className="metric-value text-foreground mb-1">
                ${totalAllocated.toLocaleString()}
              </div>
              <div className="text-sm text-muted-foreground">
                This month's budget
              </div>
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
              <div className="metric-value text-foreground mb-1">
                ${totalSpent.toLocaleString()}
              </div>
              <div className="text-sm text-muted-foreground">
                {((totalSpent / totalAllocated) * 100).toFixed(1)}% of budget used
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant={totalRemaining < 0 ? "destructive" : "success"}>
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
              <div className="metric-value mb-1">
                ${Math.abs(totalRemaining).toLocaleString()}
              </div>
              <div className="text-sm opacity-80">
                {totalRemaining < 0 ? 'Overspent this month' : 'Available to spend'}
              </div>
            </FinancialCardContent>
          </FinancialCard>
        </div>

        {/* Budget Categories */}
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
                                ${category.spent} of ${category.allocated}
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className={`font-semibold ${
                              isOverBudget ? 'text-destructive' : 'text-foreground'
                            }`}>
                              {isOverBudget ? '-' : ''}${Math.abs(category.remaining)}
                            </div>
                            <div className="flex items-center text-sm">
                              {category.trend === 'up' ? (
                                <TrendingUp className="w-3 h-3 text-destructive mr-1" />
                              ) : (
                                <TrendingDown className="w-3 h-3 text-success mr-1" />
                              )}
                              <span className={
                                category.trend === 'up' ? 'text-destructive' : 'text-success'
                              }>
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

          {/* Savings Goals */}
          <div>
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="section-title">Savings Goals</FinancialCardTitle>
                  <Button variant="ghost" size="sm" onClick={() => setShowGoalForm(!showGoalForm)}>
                    <Plus className="w-4 h-4" />
                  </Button>
                </div>
                <FinancialCardDescription>
                  Your financial objectives
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                {showGoalForm && (
                  <div className="mb-4 p-3 rounded-lg border border-border space-y-2">
                    <input
                      className="w-full px-2 py-1 text-sm border border-border rounded bg-background text-foreground"
                      placeholder="Goal title"
                      value={newGoal.title}
                      onChange={(e) => setNewGoal({ ...newGoal, title: e.target.value })}
                    />
                    <input
                      className="w-full px-2 py-1 text-sm border border-border rounded bg-background text-foreground"
                      placeholder="Target amount"
                      type="number"
                      value={newGoal.target_amount}
                      onChange={(e) => setNewGoal({ ...newGoal, target_amount: e.target.value })}
                    />
                    <input
                      className="w-full px-2 py-1 text-sm border border-border rounded bg-background text-foreground"
                      placeholder="Deadline (YYYY-MM-DD)"
                      type="date"
                      value={newGoal.deadline}
                      onChange={(e) => setNewGoal({ ...newGoal, deadline: e.target.value })}
                    />
                    <div className="flex gap-2">
                      <Button variant="financial" size="sm" onClick={handleCreateGoal}>Save</Button>
                      <Button variant="outline" size="sm" onClick={() => setShowGoalForm(false)}>Cancel</Button>
                    </div>
                  </div>
                )}
                <div className="space-y-4">
                  {goalsLoading ? (
                    <div className="flex justify-center py-4">
                      <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : savingsGoals.length === 0 ? (
                    <div className="text-center text-sm text-muted-foreground py-4">
                      No savings goals yet. Create one to get started!
                    </div>
                  ) : (
                    savingsGoals.map((goal) => {
                      const percentage = (goal.current_amount / goal.target_amount) * 100;
                      const statusLabel = goal.status === 'ON_TRACK' ? 'On Track' :
                        goal.status === 'AHEAD' ? 'Ahead' :
                        goal.status === 'COMPLETED' ? 'Completed' : 'Behind';
                      const statusVariant = goal.status === 'ON_TRACK' ? 'default' as const :
                        goal.status === 'AHEAD' ? 'secondary' as const :
                        goal.status === 'COMPLETED' ? 'secondary' as const : 'destructive' as const;

                      return (
                        <div key={goal.id} className="interactive-row p-3 rounded-lg border border-border">
                          <div className="flex items-center justify-between mb-2">
                            <div className="font-medium text-foreground text-sm">
                              {goal.title}
                            </div>
                            <div className="flex items-center gap-1">
                              <Badge variant={statusVariant} className="text-xs">
                                {statusLabel}
                              </Badge>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 w-6 p-0"
                                onClick={() => handleDeleteGoal(goal.id)}
                              >
                                <Trash2 className="w-3 h-3 text-muted-foreground" />
                              </Button>
                            </div>
                          </div>
                          <div className="space-y-2">
                            <div className="flex justify-between text-sm">
                              <span className="text-muted-foreground">
                                ${goal.current_amount.toLocaleString()} / ${goal.target_amount.toLocaleString()}
                              </span>
                              <span className="text-foreground font-medium">
                                {percentage.toFixed(0)}%
                              </span>
                            </div>
                            <div className="chart-track">
                              <div className="chart-fill-success" style={{ width: `${Math.min(percentage, 100)}%` }} />
                            </div>
                            <div className="flex justify-between text-xs text-muted-foreground">
                              {goal.deadline && <span>Target: {goal.deadline}</span>}
                              {goal.monthly_target !== null && <span>${goal.monthly_target}/mo</span>}
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </FinancialCardContent>
              <FinancialCardFooter>
                <Button variant="financial" size="sm" className="w-full" onClick={() => setShowGoalForm(true)}>
                  <Plus className="w-4 h-4" />
                  Add New Goal
                </Button>
              </FinancialCardFooter>
            </FinancialCard>
          </div>
        </div>
    </div>
  );
}
