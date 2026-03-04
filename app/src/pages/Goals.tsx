import { useState } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardFooter, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  Target, 
  Plus, 
  TrendingUp, 
  Calendar, 
  DollarSign, 
  Award, 
  Zap,
  Edit2,
  Trash2,
  CheckCircle2,
  Clock,
  AlertCircle
} from 'lucide-react';

interface SavingsGoal {
  id: number;
  name: string;
  targetAmount: number;
  currentAmount: number;
  deadline: string;
  category: string;
  priority: 'high' | 'medium' | 'low';
  status: 'on-track' | 'ahead' | 'behind';
  milestone?: {
    percentage: number;
    reward?: string;
  };
}

const initialGoals: SavingsGoal[] = [
  {
    id: 1,
    name: 'Emergency Fund',
    targetAmount: 10000,
    currentAmount: 7250,
    deadline: '2025-12-31',
    category: 'Emergency',
    priority: 'high',
    status: 'on-track',
    milestone: {
      percentage: 50,
      reward: 'Emergency Ready Badge'
    }
  },
  {
    id: 2,
    name: 'Vacation Fund',
    targetAmount: 3000,
    currentAmount: 1850,
    deadline: '2025-06-30',
    category: 'Travel',
    priority: 'medium',
    status: 'behind',
    milestone: {
      percentage: 75,
      reward: 'Travel Explorer Badge'
    }
  },
  {
    id: 3,
    name: 'New Car',
    targetAmount: 25000,
    currentAmount: 15600,
    deadline: '2026-03-31',
    category: 'Vehicle',
    priority: 'high',
    status: 'ahead',
    milestone: {
      percentage: 25,
      reward: 'Saver Starter Badge'
    }
  },
  {
    id: 4,
    name: 'Home Down Payment',
    targetAmount: 50000,
    currentAmount: 12500,
    deadline: '2027-12-31',
    category: 'Housing',
    priority: 'high',
    status: 'on-track',
    milestone: {
      percentage: 50,
      reward: 'Homeowner Badge'
    }
  }
];

export function Goals() {
  const [goals, setGoals] = useState<SavingsGoal[]>(initialGoals);
  const [showAddModal, setShowAddModal] = useState(false);

  const calculateProgress = (current: number, target: number) => {
    return Math.min((current / target) * 100, 100);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ahead':
        return 'text-green-600 bg-green-50';
      case 'on-track':
        return 'text-blue-600 bg-blue-50';
      case 'behind':
        return 'text-red-600 bg-red-50';
      default:
        return 'text-gray-600 bg-gray-50';
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'bg-red-500';
      case 'medium':
        return 'bg-yellow-500';
      case 'low':
        return 'bg-green-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'ahead':
        return <TrendingUp className="w-4 h-4" />;
      case 'on-track':
        return <CheckCircle2 className="w-4 h-4" />;
      case 'behind':
        return <Clock className="w-4 h-4" />;
      default:
        return <AlertCircle className="w-4 h-4" />;
    }
  };

  const totalTarget = goals.reduce((sum, goal) => sum + goal.targetAmount, 0);
  const totalCurrent = goals.reduce((sum, goal) => sum + goal.currentAmount, 0);
  const overallProgress = calculateProgress(totalCurrent, totalTarget);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Savings Goals</h1>
          <p className="text-muted-foreground">Track your savings milestones and achievements</p>
        </div>
        <Button onClick={() => setShowAddModal(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Add Goal
        </Button>
      </div>

      {/* Overall Progress */}
      <FinancialCard>
        <FinancialCardContent className="pt-6">
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2">
                <Target className="w-5 h-5 text-primary" />
                <span className="font-semibold">Overall Progress</span>
              </div>
              <span className="text-2xl font-bold">{overallProgress.toFixed(1)}%</span>
            </div>
            <Progress value={overallProgress} className="h-3" />
            <div className="grid grid-cols-3 gap-4 pt-4">
              <div className="text-center">
                <div className="text-sm text-muted-foreground">Total Target</div>
                <div className="text-xl font-bold">${totalTarget.toLocaleString()}</div>
              </div>
              <div className="text-center">
                <div className="text-sm text-muted-foreground">Total Saved</div>
                <div className="text-xl font-bold text-green-600">${totalCurrent.toLocaleString()}</div>
              </div>
              <div className="text-center">
                <div className="text-sm text-muted-foreground">Remaining</div>
                <div className="text-xl font-bold text-red-600">${(totalTarget - totalCurrent).toLocaleString()}</div>
              </div>
            </div>
          </div>
        </FinancialCardContent>
      </FinancialCard>

      {/* Milestone Achievements */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {goals.filter(g => g.milestone && calculateProgress(g.currentAmount, g.targetAmount) >= g.milestone!.percentage).map(goal => (
          <FinancialCard key={`milestone-${goal.id}`} className="bg-gradient-to-br from-yellow-50 to-orange-50 border-yellow-200">
            <FinancialCardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Award className="w-8 h-8 text-yellow-600" />
                <div>
                  <div className="font-semibold text-yellow-800">{goal.milestone?.reward}</div>
                  <div className="text-sm text-yellow-700">{goal.name}</div>
                </div>
              </div>
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>

      {/* Goals Grid */}
      <div className="grid gap-6 md:grid-cols-2">
        {goals.map(goal => {
          const progress = calculateProgress(goal.currentAmount, goal.targetAmount);
          const remaining = goal.targetAmount - goal.currentAmount;
          const daysLeft = Math.ceil((new Date(goal.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24));

          return (
            <FinancialCard key={goal.id}>
              <FinancialCardHeader>
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${getPriorityColor(goal.priority)}`} />
                    <FinancialCardTitle>{goal.name}</FinancialCardTitle>
                  </div>
                  <Badge className={getStatusColor(goal.status)}>
                    {getStatusIcon(goal.status)}
                    <span className="ml-1">{goal.status.replace('-', ' ')}</span>
                  </Badge>
                </div>
                <FinancialCardDescription>{goal.category}</FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent className="pt-6">
                <div className="space-y-4">
                  {/* Progress Bar */}
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Progress</span>
                      <span className="font-medium">{progress.toFixed(1)}%</span>
                    </div>
                    <Progress value={progress} className="h-3" />
                  </div>

                  {/* Amount Details */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-sm text-muted-foreground">Target</div>
                      <div className="text-lg font-bold">${goal.targetAmount.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">Saved</div>
                      <div className="text-lg font-bold text-green-600">${goal.currentAmount.toLocaleString()}</div>
                    </div>
                  </div>

                  {/* Timeline */}
                  <div className="flex items-center gap-4 text-sm">
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Calendar className="w-4 h-4" />
                      <span>{daysLeft > 0 ? `${daysLeft} days left` : 'Deadline passed'}</span>
                    </div>
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <DollarSign className="w-4 h-4" />
                      <span>${remaining.toLocaleString()} remaining</span>
                    </div>
                  </div>

                  {/* Milestone */}
                  {goal.milestone && (
                    <div className="flex items-center gap-2 p-3 bg-yellow-50 rounded-lg">
                      <Zap className="w-4 h-4 text-yellow-600" />
                      <span className="text-sm text-yellow-800">
                        Milestone: {goal.milestone.percentage}% - {goal.milestone.reward || 'Achievement unlocked!'}
                      </span>
                    </div>
                  )}
                </div>
              </FinancialCardContent>
              <FinancialCardFooter>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" className="flex-1">
                    <Edit2 className="w-3 h-3 mr-1" />
                    Edit
                  </Button>
                  <Button variant="outline" size="sm" className="flex-1">
                    <DollarSign className="w-3 h-3 mr-1" />
                    Add Funds
                  </Button>
                  <Button variant="outline" size="sm" className="text-red-600 hover:text-red-700">
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              </FinancialCardFooter>
            </FinancialCard>
          );
        })}
      </div>

      {/* Add Goal Modal Placeholder */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background rounded-lg p-6 w-full max-w-md">
            <h2 className="text-2xl font-bold mb-4">Add New Goal</h2>
            <p className="text-muted-foreground mb-4">Goal creation form would go here...</p>
            <Button onClick={() => setShowAddModal(false)} className="w-full">
              Close
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
