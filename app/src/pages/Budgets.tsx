import { useState } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardFooter, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Calendar, DollarSign, Plus, PieChart, TrendingDown, TrendingUp, Target, AlertCircle, Settings } from 'lucide-react';

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

const budgetGoals = [
  {
    id: 1,
    title: 'Emergency Fund',
    target: 10000,
    current: 7250,
    deadline: 'Dec 2025',
    monthlyTarget: 458,
    status: 'on-track'
  },
  {
    id: 2,
    title: 'Vacation Fund',
    target: 3000,
    current: 1850,
    deadline: 'Jun 2025',
    monthlyTarget: 383,
    status: 'behind'
  },
  {
    id: 3,
    title: 'New Car',
    target: 25000,
    current: 15600,
    deadline: 'Mar 2026',
    monthlyTarget: 625,
    status: 'ahead'
  }
];

export function Budgets() {
  const [selectedPeriod] = useState('monthly');
  
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
                  <Button variant="ghost" size="sm">
                    <Plus className="w-4 h-4" />
                  </Button>
                </div>
                <FinancialCardDescription>
                  Your financial objectives
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-4">
                  {budgetGoals.map((goal) => {
                    const percentage = (goal.current / goal.target) * 100;
                    
                    return (
                      <div key={goal.id} className="interactive-row p-3 rounded-lg border border-border">
                        <div className="flex items-center justify-between mb-2">
                          <div className="font-medium text-foreground text-sm">
                            {goal.title}
                          </div>
                          <Badge 
                            variant={
                              goal.status === 'on-track' ? 'default' :
                              goal.status === 'ahead' ? 'secondary' : 'destructive'
                            }
                            className="text-xs"
                          >
                            {goal.status === 'on-track' ? 'On Track' :
                             goal.status === 'ahead' ? 'Ahead' : 'Behind'}
                          </Badge>
                        </div>
                        <div className="space-y-2">
                          <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">
                              ${goal.current.toLocaleString()} / ${goal.target.toLocaleString()}
                            </span>
                            <span className="text-foreground font-medium">
                              {percentage.toFixed(0)}%
                            </span>
                          </div>
                          <div className="chart-track">
                            <div className="chart-fill-success" style={{ width: `${Math.min(percentage, 100)}%` }} />
                          </div>
                          <div className="flex justify-between text-xs text-muted-foreground">
                            <span>Target: {goal.deadline}</span>
                            <span>${goal.monthlyTarget}/mo</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </FinancialCardContent>
              <FinancialCardFooter>
                <Button variant="financial" size="sm" className="w-full">
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
