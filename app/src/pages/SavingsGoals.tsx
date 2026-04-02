import { useState } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardFooter, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Target, Plus, TrendingUp, Calendar, DollarSign, CheckCircle, Bell } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

interface SavingsGoal {
  id: number;
  name: string;
  targetAmount: number;
  currentAmount: number;
  targetDate: string;
  category: string;
  color: string;
  milestones: number[]; // percentages already notified
}

const MILESTONE_THRESHOLDS = [25, 50, 75, 100];

const CATEGORY_COLORS: Record<string, string> = {
  'Emergency Fund': 'bg-destructive',
  'Vacation': 'bg-accent',
  'Home': 'bg-primary',
  'Car': 'bg-warning',
  'Education': 'bg-success',
  'Retirement': 'bg-secondary',
  'Other': 'bg-muted',
};

const initialGoals: SavingsGoal[] = [
  {
    id: 1,
    name: 'Emergency Fund',
    targetAmount: 10000,
    currentAmount: 4250,
    targetDate: '2026-12-31',
    category: 'Emergency Fund',
    color: 'bg-destructive',
    milestones: [25],
  },
  {
    id: 2,
    name: 'Europe Vacation',
    targetAmount: 5000,
    currentAmount: 2750,
    targetDate: '2026-08-01',
    category: 'Vacation',
    color: 'bg-accent',
    milestones: [25, 50],
  },
  {
    id: 3,
    name: 'New Laptop',
    targetAmount: 2500,
    currentAmount: 500,
    targetDate: '2026-06-15',
    category: 'Other',
    color: 'bg-muted',
    milestones: [],
  },
];

function getProgress(current: number, target: number): number {
  return Math.min(Math.round((current / target) * 100), 100);
}

function getDaysLeft(targetDate: string): number {
  const today = new Date();
  const target = new Date(targetDate);
  const diff = target.getTime() - today.getTime();
  return Math.max(Math.ceil(diff / (1000 * 60 * 60 * 24)), 0);
}

function getMilestoneLabel(pct: number): string {
  if (pct >= 100) return '🎉 Goal Reached!';
  if (pct >= 75) return '🔥 75% — Almost there!';
  if (pct >= 50) return '⚡ Halfway there!';
  if (pct >= 25) return '✅ 25% — Great start!';
  return '';
}

export function SavingsGoals() {
  const [goals, setGoals] = useState<SavingsGoal[]>(initialGoals);
  const [open, setOpen] = useState(false);
  const [depositGoalId, setDepositGoalId] = useState<number | null>(null);
  const [depositAmount, setDepositAmount] = useState('');
  const { toast } = useToast();

  const [newGoal, setNewGoal] = useState({
    name: '',
    targetAmount: '',
    currentAmount: '',
    targetDate: '',
    category: 'Other',
  });

  const totalSaved = goals.reduce((sum, g) => sum + g.currentAmount, 0);
  const totalTarget = goals.reduce((sum, g) => sum + g.targetAmount, 0);
  const completedGoals = goals.filter(g => g.currentAmount >= g.targetAmount).length;

  function handleAddGoal() {
    if (!newGoal.name || !newGoal.targetAmount || !newGoal.targetDate) return;
    const goal: SavingsGoal = {
      id: Date.now(),
      name: newGoal.name,
      targetAmount: parseFloat(newGoal.targetAmount),
      currentAmount: parseFloat(newGoal.currentAmount || '0'),
      targetDate: newGoal.targetDate,
      category: newGoal.category,
      color: CATEGORY_COLORS[newGoal.category] || 'bg-muted',
      milestones: [],
    };
    setGoals(prev => [...prev, goal]);
    setNewGoal({ name: '', targetAmount: '', currentAmount: '', targetDate: '', category: 'Other' });
    setOpen(false);
    toast({ title: 'Goal created!', description: `"${goal.name}" added to your savings goals.` });
  }

  function handleDeposit(goalId: number) {
    const amount = parseFloat(depositAmount);
    if (!amount || amount <= 0) return;

    setGoals(prev => prev.map(g => {
      if (g.id !== goalId) return g;
      const newAmount = Math.min(g.currentAmount + amount, g.targetAmount);
      const newPct = getProgress(newAmount, g.targetAmount);
      const newMilestones = [...g.milestones];

      // Check milestones
      for (const threshold of MILESTONE_THRESHOLDS) {
        if (newPct >= threshold && !newMilestones.includes(threshold)) {
          newMilestones.push(threshold);
          toast({
            title: getMilestoneLabel(threshold),
            description: `You've reached ${threshold}% of your "${g.name}" goal!`,
          });
        }
      }

      return { ...g, currentAmount: newAmount, milestones: newMilestones };
    }));

    setDepositGoalId(null);
    setDepositAmount('');
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Savings Goals</h1>
          <p className="text-muted-foreground">Track your progress toward financial milestones</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              New Goal
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Savings Goal</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-2">
              <div>
                <Label>Goal Name</Label>
                <Input placeholder="e.g. Emergency Fund" value={newGoal.name}
                  onChange={e => setNewGoal(p => ({ ...p, name: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Target Amount ($)</Label>
                  <Input type="number" placeholder="10000" value={newGoal.targetAmount}
                    onChange={e => setNewGoal(p => ({ ...p, targetAmount: e.target.value }))} />
                </div>
                <div>
                  <Label>Already Saved ($)</Label>
                  <Input type="number" placeholder="0" value={newGoal.currentAmount}
                    onChange={e => setNewGoal(p => ({ ...p, currentAmount: e.target.value }))} />
                </div>
              </div>
              <div>
                <Label>Target Date</Label>
                <Input type="date" value={newGoal.targetDate}
                  onChange={e => setNewGoal(p => ({ ...p, targetDate: e.target.value }))} />
              </div>
              <div>
                <Label>Category</Label>
                <select className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={newGoal.category}
                  onChange={e => setNewGoal(p => ({ ...p, category: e.target.value }))}>
                  {Object.keys(CATEGORY_COLORS).map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <Button className="w-full" onClick={handleAddGoal}>Create Goal</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between pb-2">
            <FinancialCardTitle className="text-sm font-medium">Total Saved</FinancialCardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">${totalSaved.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">of ${totalTarget.toLocaleString()} total target</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between pb-2">
            <FinancialCardTitle className="text-sm font-medium">Active Goals</FinancialCardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{goals.length}</div>
            <p className="text-xs text-muted-foreground">{completedGoals} completed</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between pb-2">
            <FinancialCardTitle className="text-sm font-medium">Overall Progress</FinancialCardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{getProgress(totalSaved, totalTarget)}%</div>
            <Progress value={getProgress(totalSaved, totalTarget)} className="mt-2" />
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals list */}
      <div className="grid gap-4 md:grid-cols-2">
        {goals.map(goal => {
          const pct = getProgress(goal.currentAmount, goal.targetAmount);
          const daysLeft = getDaysLeft(goal.targetDate);
          const isComplete = pct >= 100;
          const nextMilestone = MILESTONE_THRESHOLDS.find(t => !goal.milestones.includes(t) && t > pct);

          return (
            <FinancialCard key={goal.id} className={isComplete ? 'border-success' : ''}>
              <FinancialCardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div>
                    <FinancialCardTitle className="flex items-center gap-2">
                      {isComplete && <CheckCircle className="h-4 w-4 text-success" />}
                      {goal.name}
                    </FinancialCardTitle>
                    <FinancialCardDescription>{goal.category}</FinancialCardDescription>
                  </div>
                  <Badge variant={isComplete ? 'default' : 'outline'}>{pct}%</Badge>
                </div>
              </FinancialCardHeader>

              <FinancialCardContent className="space-y-3">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-muted-foreground">
                      ${goal.currentAmount.toLocaleString()} saved
                    </span>
                    <span className="font-medium">${goal.targetAmount.toLocaleString()}</span>
                  </div>
                  <Progress value={pct} className={isComplete ? '[&>div]:bg-success' : ''} />
                </div>

                <div className="flex justify-between text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    {isComplete ? 'Completed!' : `${daysLeft} days left`}
                  </span>
                  {nextMilestone && (
                    <span className="flex items-center gap-1 text-primary">
                      <Bell className="h-3 w-3" />
                      Next: {nextMilestone}% milestone
                    </span>
                  )}
                </div>

                {/* Milestones achieved */}
                {goal.milestones.length > 0 && (
                  <div className="flex gap-1 flex-wrap">
                    {goal.milestones.map(m => (
                      <Badge key={m} variant="secondary" className="text-xs">
                        {m}% ✓
                      </Badge>
                    ))}
                  </div>
                )}
              </FinancialCardContent>

              <FinancialCardFooter>
                {depositGoalId === goal.id ? (
                  <div className="flex gap-2 w-full">
                    <Input
                      type="number"
                      placeholder="Amount to add"
                      value={depositAmount}
                      onChange={e => setDepositAmount(e.target.value)}
                      className="h-8"
                    />
                    <Button size="sm" onClick={() => handleDeposit(goal.id)}>Add</Button>
                    <Button size="sm" variant="outline" onClick={() => setDepositGoalId(null)}>Cancel</Button>
                  </div>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    disabled={isComplete}
                    onClick={() => setDepositGoalId(goal.id)}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    Add Funds
                  </Button>
                )}
              </FinancialCardFooter>
            </FinancialCard>
          );
        })}
      </div>
    </div>
  );
}

export default SavingsGoals;
