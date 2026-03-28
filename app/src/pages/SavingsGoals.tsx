import { useState, useEffect, useMemo } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardFooter,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dailog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Target,
  Plus,
  TrendingUp,
  TrendingDown,
  Calendar,
  DollarSign,
  Trash2,
  Edit,
  PiggyBank,
  Trophy,
  CheckCircle2,
  AlertCircle,
  Clock,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import type { SavingsGoal, CreateSavingsGoalRequest } from '@/api/savings-goals';

const GOAL_COLORS = [
  'bg-primary',
  'bg-success',
  'bg-accent',
  'bg-warning',
  'bg-destructive',
  'bg-secondary',
];

const GOAL_CATEGORIES = [
  'Emergency Fund',
  'Vacation',
  'Education',
  'Home Purchase',
  'Vehicle',
  'Retirement',
  'Wedding',
  'Healthcare',
  'Investment',
  'Other',
];

// Mock data for initial rendering (would be replaced by API calls)
const mockGoals: SavingsGoal[] = [
  {
    id: '1',
    name: 'Emergency Fund',
    targetAmount: 10000,
    currentAmount: 7250,
    deadline: '2026-12-31',
    monthlyContribution: 500,
    category: 'Emergency Fund',
    color: 'bg-success',
    createdAt: '2025-01-01',
    updatedAt: '2026-03-28',
  },
  {
    id: '2',
    name: 'Vacation to Japan',
    targetAmount: 5000,
    currentAmount: 1800,
    deadline: '2026-09-01',
    monthlyContribution: 400,
    category: 'Vacation',
    color: 'bg-primary',
    createdAt: '2025-06-01',
    updatedAt: '2026-03-28',
  },
  {
    id: '3',
    name: 'New Car Down Payment',
    targetAmount: 15000,
    currentAmount: 3200,
    deadline: '2027-06-01',
    monthlyContribution: 600,
    category: 'Vehicle',
    color: 'bg-accent',
    createdAt: '2025-09-01',
    updatedAt: '2026-03-28',
  },
];

interface Milestone {
  percentage: number;
  label: string;
  icon: typeof Trophy;
}

const MILESTONES: Milestone[] = [
  { percentage: 25, label: 'Quarter Way', icon: TrendingUp },
  { percentage: 50, label: 'Halfway There', icon: Target },
  { percentage: 75, label: 'Almost There', icon: Trophy },
  { percentage: 100, label: 'Goal Reached!', icon: CheckCircle2 },
];

function getProgressStatus(current: number, target: number, deadline: string, monthly: number) {
  const progress = (current / target) * 100;
  const deadlineDate = new Date(deadline);
  const now = new Date();
  const monthsRemaining = Math.max(
    1,
    Math.ceil((deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24 * 30))
  );
  const projectedTotal = current + monthly * monthsRemaining;
  const isOnTrack = projectedTotal >= target;

  if (progress >= 100) return { status: 'completed', label: 'Completed', variant: 'default' as const };
  if (isOnTrack) return { status: 'on-track', label: 'On Track', variant: 'default' as const };
  return { status: 'behind', label: 'Behind', variant: 'destructive' as const };
}

function getMonthsRemaining(deadline: string): number {
  const deadlineDate = new Date(deadline);
  const now = new Date();
  return Math.max(0, Math.ceil((deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24 * 30)));
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function SavingsGoals() {
  const [goals, setGoals] = useState<SavingsGoal[]>(mockGoals);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isContributeOpen, setIsContributeOpen] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<SavingsGoal | null>(null);
  const [contributeAmount, setContributeAmount] = useState('');
  const [formData, setFormData] = useState<CreateSavingsGoalRequest>({
    name: '',
    targetAmount: 0,
    currentAmount: 0,
    deadline: '',
    monthlyContribution: 0,
    category: 'Other',
    color: 'bg-primary',
  });
  const { toast } = useToast();

  const summary = useMemo(() => {
    const totalSaved = goals.reduce((sum, g) => sum + g.currentAmount, 0);
    const totalTarget = goals.reduce((sum, g) => sum + g.targetAmount, 0);
    const monthlyTotal = goals.reduce((sum, g) => sum + g.monthlyContribution, 0);
    const goalsOnTrack = goals.filter((g) => {
      const { status } = getProgressStatus(g.currentAmount, g.targetAmount, g.deadline, g.monthlyContribution);
      return status === 'on-track' || status === 'completed';
    }).length;
    const goalsBehind = goals.length - goalsOnTrack;
    return { totalSaved, totalTarget, goalsOnTrack, goalsBehind, monthlyTotal };
  }, [goals]);

  const handleCreateGoal = () => {
    if (!formData.name || formData.targetAmount <= 0 || !formData.deadline) {
      toast({
        title: 'Validation Error',
        description: 'Please fill in all required fields.',
        variant: 'destructive',
      });
      return;
    }

    const newGoal: SavingsGoal = {
      id: Date.now().toString(),
      ...formData,
      color: formData.color || GOAL_COLORS[goals.length % GOAL_COLORS.length],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    setGoals((prev) => [...prev, newGoal]);
    setIsCreateOpen(false);
    resetForm();
    toast({
      title: 'Goal Created',
      description: `"${newGoal.name}" has been added to your savings goals.`,
    });
  };

  const handleContribute = () => {
    if (!selectedGoal || !contributeAmount || parseFloat(contributeAmount) <= 0) {
      toast({
        title: 'Invalid Amount',
        description: 'Please enter a valid contribution amount.',
        variant: 'destructive',
      });
      return;
    }

    const amount = parseFloat(contributeAmount);
    const prevAmount = selectedGoal.currentAmount;
    const newAmount = Math.min(prevAmount + amount, selectedGoal.targetAmount);

    setGoals((prev) =>
      prev.map((g) =>
        g.id === selectedGoal.id
          ? { ...g, currentAmount: newAmount, updatedAt: new Date().toISOString() }
          : g
      )
    );

    // Check for milestone achievements
    const prevProgress = (prevAmount / selectedGoal.targetAmount) * 100;
    const newProgress = (newAmount / selectedGoal.targetAmount) * 100;

    for (const milestone of MILESTONES) {
      if (prevProgress < milestone.percentage && newProgress >= milestone.percentage) {
        setTimeout(() => {
          toast({
            title: `🎉 ${milestone.label}!`,
            description: `You've reached ${milestone.percentage}% of your "${selectedGoal.name}" goal!`,
          });
        }, 300);
        break;
      }
    }

    if (newAmount >= selectedGoal.targetAmount) {
      toast({
        title: '🏆 Goal Completed!',
        description: `Congratulations! You've reached your "${selectedGoal.name}" goal!`,
      });
    }

    setIsContributeOpen(false);
    setSelectedGoal(null);
    setContributeAmount('');
  };

  const handleDeleteGoal = (goal: SavingsGoal) => {
    setGoals((prev) => prev.filter((g) => g.id !== goal.id));
    toast({
      title: 'Goal Deleted',
      description: `"${goal.name}" has been removed.`,
    });
  };

  const resetForm = () => {
    setFormData({
      name: '',
      targetAmount: 0,
      currentAmount: 0,
      deadline: '',
      monthlyContribution: 0,
      category: 'Other',
      color: 'bg-primary',
    });
  };

  const openContributeDialog = (goal: SavingsGoal) => {
    setSelectedGoal(goal);
    setContributeAmount('');
    setIsContributeOpen(true);
  };

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Savings Goals</h1>
          <p className="text-muted-foreground">Track your progress towards financial milestones.</p>
        </div>
        <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              New Goal
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle>Create Savings Goal</DialogTitle>
              <DialogDescription>Set a new savings target and track your progress.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">Goal Name</Label>
                <Input
                  id="name"
                  placeholder="e.g., Emergency Fund"
                  value={formData.name}
                  onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="targetAmount">Target Amount ($)</Label>
                  <Input
                    id="targetAmount"
                    type="number"
                    min="0"
                    step="100"
                    placeholder="10000"
                    value={formData.targetAmount || ''}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, targetAmount: parseFloat(e.target.value) || 0 }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="currentAmount">Current Amount ($)</Label>
                  <Input
                    id="currentAmount"
                    type="number"
                    min="0"
                    step="100"
                    placeholder="0"
                    value={formData.currentAmount || ''}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, currentAmount: parseFloat(e.target.value) || 0 }))
                    }
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="deadline">Target Date</Label>
                  <Input
                    id="deadline"
                    type="date"
                    value={formData.deadline}
                    onChange={(e) => setFormData((prev) => ({ ...prev, deadline: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="monthlyContribution">Monthly ($)</Label>
                  <Input
                    id="monthlyContribution"
                    type="number"
                    min="0"
                    step="50"
                    placeholder="500"
                    value={formData.monthlyContribution || ''}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, monthlyContribution: parseFloat(e.target.value) || 0 }))
                    }
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="category">Category</Label>
                <Select
                  value={formData.category}
                  onValueChange={(value) => setFormData((prev) => ({ ...prev, category: value }))}
                >
                  <SelectTrigger id="category">
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {GOAL_CATEGORIES.map((cat) => (
                      <SelectItem key={cat} value={cat}>
                        {cat}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateGoal}>Create Goal</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Total Saved</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-success">
              {formatCurrency(summary.totalSaved)}
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xs text-muted-foreground">
              of {formatCurrency(summary.totalTarget)} target
            </p>
            <div className="mt-2 h-2 rounded-full bg-muted">
              <div
                className="h-2 rounded-full bg-success transition-all"
                style={{ width: `${Math.min(100, (summary.totalSaved / summary.totalTarget) * 100)}%` }}
              />
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Monthly Savings</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">{formatCurrency(summary.monthlyTotal)}</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xs text-muted-foreground">Total monthly contributions</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>On Track</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-success">{summary.goalsOnTrack}</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xs text-muted-foreground">Goals progressing well</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Needs Attention</FinancialCardDescription>
            <FinancialCardTitle className={summary.goalsBehind > 0 ? 'text-2xl text-destructive' : 'text-2xl'}>
              {summary.goalsBehind}
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xs text-muted-foreground">Goals behind schedule</p>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals List */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {goals.map((goal) => {
          const progress = (goal.currentAmount / goal.targetAmount) * 100;
          const { status, label, variant } = getProgressStatus(
            goal.currentAmount,
            goal.targetAmount,
            goal.deadline,
            goal.monthlyContribution
          );
          const monthsLeft = getMonthsRemaining(goal.deadline);
          const remaining = goal.targetAmount - goal.currentAmount;

          return (
            <FinancialCard key={goal.id} className="relative overflow-hidden">
              {/* Progress bar at top */}
              <div className="absolute top-0 left-0 right-0 h-1 bg-muted">
                <div
                  className={`h-1 transition-all ${goal.color}`}
                  style={{ width: `${Math.min(100, progress)}%` }}
                />
              </div>

              <FinancialCardHeader className="pt-4">
                <div className="flex items-start justify-between">
                  <div>
                    <FinancialCardTitle className="text-lg">{goal.name}</FinancialCardTitle>
                    <FinancialCardDescription className="flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      {monthsLeft} months remaining
                    </FinancialCardDescription>
                  </div>
                  <Badge variant={variant}>{label}</Badge>
                </div>
              </FinancialCardHeader>

              <FinancialCardContent className="space-y-4">
                {/* Progress */}
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium">{formatCurrency(goal.currentAmount)}</span>
                    <span className="text-muted-foreground">{formatCurrency(goal.targetAmount)}</span>
                  </div>
                  <div className="h-3 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-3 rounded-full transition-all ${goal.color}`}
                      style={{ width: `${Math.min(100, progress)}%` }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{progress.toFixed(1)}% complete</p>
                </div>

                {/* Details */}
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="flex items-center gap-2">
                    <DollarSign className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Remaining</p>
                      <p className="font-medium">{formatCurrency(Math.max(0, remaining))}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Monthly</p>
                      <p className="font-medium">{formatCurrency(goal.monthlyContribution)}</p>
                    </div>
                  </div>
                </div>

                {/* Milestones */}
                <div className="flex gap-2">
                  {MILESTONES.map((milestone) => {
                    const reached = progress >= milestone.percentage;
                    const MilestoneIcon = milestone.icon;
                    return (
                      <div
                        key={milestone.percentage}
                        className={`flex-1 rounded-lg p-2 text-center text-xs ${
                          reached ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground'
                        }`}
                      >
                        <MilestoneIcon className="h-4 w-4 mx-auto mb-1" />
                        <span>{milestone.percentage}%</span>
                      </div>
                    );
                  })}
                </div>
              </FinancialCardContent>

              <FinancialCardFooter className="gap-2">
                <Button
                  size="sm"
                  className="flex-1 gap-1"
                  onClick={() => openContributeDialog(goal)}
                  disabled={status === 'completed'}
                >
                  <PiggyBank className="h-4 w-4" />
                  Contribute
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button size="sm" variant="outline" className="gap-1">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete Goal</AlertDialogTitle>
                      <AlertDialogDescription>
                        Are you sure you want to delete "{goal.name}"? This action cannot be undone.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={() => handleDeleteGoal(goal)}>Delete</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </FinancialCardFooter>
            </FinancialCard>
          );
        })}

        {/* Empty state / Add card */}
        {goals.length === 0 && (
          <FinancialCard className="flex flex-col items-center justify-center py-12">
            <Target className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No Goals Yet</h3>
            <p className="text-muted-foreground text-center mb-4">
              Start by creating your first savings goal to track your progress.
            </p>
            <Button onClick={() => setIsCreateOpen(true)} className="gap-2">
              <Plus className="h-4 w-4" />
              Create Your First Goal
            </Button>
          </FinancialCard>
        )}
      </div>

      {/* Contribute Dialog */}
      <Dialog open={isContributeOpen} onOpenChange={setIsContributeOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Contribute to "{selectedGoal?.name}"</DialogTitle>
            <DialogDescription>
              {selectedGoal && (
                <>
                  Current: {formatCurrency(selectedGoal.currentAmount)} /{' '}
                  {formatCurrency(selectedGoal.targetAmount)}
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="contributeAmount">Amount ($)</Label>
              <Input
                id="contributeAmount"
                type="number"
                min="0"
                step="10"
                placeholder="100"
                value={contributeAmount}
                onChange={(e) => setContributeAmount(e.target.value)}
                autoFocus
              />
            </div>
            {selectedGoal && (
              <div className="rounded-lg bg-muted p-3 text-sm">
                <p className="text-muted-foreground">
                  After this contribution:{' '}
                  <span className="font-medium text-foreground">
                    {formatCurrency(
                      Math.min(
                        selectedGoal.currentAmount + (parseFloat(contributeAmount) || 0),
                        selectedGoal.targetAmount
                      )
                    )}
                  </span>
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsContributeOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleContribute}>Contribute</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
