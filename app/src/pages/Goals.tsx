import { useState } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus, Target, CheckCircle2, Circle, Trophy, Calendar, ArrowRight, Wallet } from 'lucide-react';

const savingsGoals = [
  {
    id: 1,
    title: 'Emergency Fund',
    target: 10000,
    current: 7250,
    deadline: '2025-12-31',
    category: 'Security',
    milestones: [
      { name: '1 Month Expenses', amount: 3000, completed: true },
      { name: '3 Months Expenses', amount: 6000, completed: true },
      { name: 'Full Safety Net', amount: 10000, completed: false },
    ],
    status: 'on-track'
  },
  {
    id: 2,
    title: 'New Loft Deposit',
    target: 50000,
    current: 12000,
    deadline: '2026-08-15',
    category: 'Housing',
    milestones: [
      { name: 'Initial Research', amount: 1000, completed: true },
      { name: 'First 20%', amount: 10000, completed: true },
      { name: 'Halfway Mark', amount: 25000, completed: false },
      { name: 'Full Deposit', amount: 50000, completed: false },
    ],
    status: 'ahead'
  },
  {
    id: 3,
    title: 'Japan Summer Trip',
    target: 4500,
    current: 1200,
    deadline: '2025-06-01',
    category: 'Travel',
    milestones: [
      { name: 'Flights Booked', amount: 1500, completed: false },
      { name: 'Accommodation', amount: 3000, completed: false },
      { name: 'Spending Money', amount: 4500, completed: false },
    ],
    status: 'behind'
  }
];

export function Goals() {
  const [activeTab, setActiveTab] = useState('active');

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">
              Plan, track, and achieve your financial milestones
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="financial" size="sm">
              <Plus className="w-4 h-4" />
              New Goal
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3 mb-8">
        <div className="lg:col-span-2 space-y-6">
          {savingsGoals.map((goal) => {
            const percentage = (goal.current / goal.target) * 100;
            return (
              <FinancialCard key={goal.id} variant="financial" className="overflow-hidden">
                <FinancialCardHeader className="border-b border-border/50">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-lg bg-primary/10 text-primary">
                        <Target className="w-5 h-5" />
                      </div>
                      <div>
                        <FinancialCardTitle>{goal.title}</FinancialCardTitle>
                        <FinancialCardDescription>{goal.category} • Target: ${goal.target.toLocaleString()}</FinancialCardDescription>
                      </div>
                    </div>
                    <Badge variant={goal.status === 'behind' ? 'destructive' : 'default'}>
                      {goal.status.replace('-', ' ')}
                    </Badge>
                  </div>
                </FinancialCardHeader>
                <FinancialCardContent className="pt-6">
                  <div className="space-y-6">
                    {/* Progress Bar */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium text-foreground">${goal.current.toLocaleString()} saved</span>
                        <span className="text-muted-foreground">{percentage.toFixed(0)}% Complete</span>
                      </div>
                      <div className="chart-track h-3">
                        <div 
                          className="chart-fill-success h-full transition-all duration-1000" 
                          style={{ width: `${percentage}%` }} 
                        />
                      </div>
                    </div>

                    {/* Milestones */}
                    <div>
                      <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                        <Trophy className="w-4 h-4 text-warning" />
                        Milestones
                      </h4>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {goal.milestones.map((m, idx) => (
                          <div 
                            key={idx} 
                            className={`p-3 rounded-xl border flex flex-col gap-1 ${
                              m.completed 
                                ? 'bg-success/5 border-success/20' 
                                : 'bg-surface-2 border-border-subtle opacity-70'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                                ${m.amount.toLocaleString()}
                              </span>
                              {m.completed ? (
                                <CheckCircle2 className="w-4 h-4 text-success" />
                              ) : (
                                <Circle className="w-4 h-4 text-muted-foreground" />
                              )}
                            </div>
                            <span className="text-sm font-medium text-foreground truncate">
                              {m.name}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </FinancialCardContent>
                <div className="bg-surface-2 px-6 py-3 flex items-center justify-between border-t border-border/50">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Calendar className="w-3 h-3" />
                    Deadline: {new Date(goal.deadline).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </div>
                  <Button variant="ghost" size="sm" className="text-xs gap-1">
                    Add Funds <ArrowRight className="w-3 h-3" />
                  </Button>
                </div>
              </FinancialCard>
            );
          })}
        </div>

        {/* Sidebar Summary */}
        <div className="space-y-6">
          <FinancialCard variant="financial">
            <FinancialCardHeader>
              <FinancialCardTitle className="text-lg">Total Savings</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="flex flex-col gap-4">
                <div className="p-4 rounded-2xl bg-surface-2 border border-border-subtle flex items-center gap-4">
                  <div className="p-3 rounded-full bg-success/10 text-success">
                    <Wallet className="w-6 h-6" />
                  </div>
                  <div>
                    <div className="text-2xl font-display text-foreground">$20,450</div>
                    <div className="text-xs text-muted-foreground">Across 3 active goals</div>
                  </div>
                </div>
                
                <div className="space-y-3 pt-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Monthly Contribution</span>
                    <span className="text-foreground font-medium">$1,450.00</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Remaining for Goals</span>
                    <span className="text-foreground font-medium">$44,050.00</span>
                  </div>
                </div>
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="bg-primary/5 border-primary/20">
            <FinancialCardHeader>
              <FinancialCardTitle className="text-sm">Smart Insights</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-sm text-text-secondary leading-relaxed">
                Based on your current savings rate, you'll reach your **New Loft Deposit** goal by **October 2026** (2 months later than planned). 
              </p>
              <Button variant="outline" size="sm" className="mt-4 w-full">
                Optimize Savings
              </Button>
            </FinancialCardContent>
          </FinancialCard>
        </div>
      </div>
    </div>
  );
}
