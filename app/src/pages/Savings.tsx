import { useState } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Target, Plus, Award, Clock } from 'lucide-react';
import { formatMoney } from '@/lib/currency';

const mockGoals = [
  {
    id: 1,
    title: 'Emergency Fund',
    target: 10000,
    current: 8500,
    deadline: 'Dec 2025',
  },
  {
    id: 2,
    title: 'New Laptop',
    target: 2000,
    current: 400,
    deadline: 'Aug 2025',
  },
  {
    id: 3,
    title: 'Travel Fund',
    target: 5000,
    current: 4200,
    deadline: 'Oct 2025',
  }
];

export function Savings() {
  const [goals] = useState(mockGoals);

  const getProgressClass = (percentage: number) => {
    return percentage >= 80 ? 'chart-fill-success' : 'chart-fill-primary';
  };

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">
              Plan your future and track your progress towards financial freedom
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="financial" size="sm">
              <Plus className="w-4 h-4 mr-2" />
              New Goal
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {goals.map((goal) => {
          const percentage = (goal.current / goal.target) * 100;
          const isHighProgress = percentage >= 80;

          return (
            <FinancialCard key={goal.id} variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="section-title flex items-center gap-2">
                    <Target className={`w-5 h-5 ${isHighProgress ? 'text-success' : 'text-primary'}`} />
                    {goal.title}
                  </FinancialCardTitle>
                  {isHighProgress && (
                    <Award className="w-5 h-5 text-warning animate-bounce" />
                  )}
                </div>
                <FinancialCardDescription>
                  Target date: {goal.deadline}
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-4">
                  <div className="flex justify-between items-end">
                    <div>
                      <div className="metric-value text-2xl">
                        {formatMoney(goal.current)}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        of {formatMoney(goal.target)}
                      </div>
                    </div>
                    <div className={`text-lg font-bold ${isHighProgress ? 'text-success' : 'text-primary'}`}>
                      {percentage.toFixed(0)}%
                    </div>
                  </div>

                  <div className="chart-track h-3">
                    <div
                      className={`${getProgressClass(percentage)} h-full transition-all duration-500`}
                      style={{ width: `${Math.min(percentage, 100)}%` }}
                    />
                  </div>

                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="w-3 h-3" />
                    <span>{isHighProgress ? 'Almost there!' : 'On your way'}</span>
                  </div>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          );
        })}
      </div>
    </div>
  );
}
