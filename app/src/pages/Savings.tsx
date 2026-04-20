import { useState, useEffect } from 'react';
import {
  listSavingsGoals,
  createSavingsGoal,
  updateSavingsGoal,
  deleteSavingsGoal,
  addSavingsContribution,
  listSavingsMilestones,
  createSavingsMilestone,
  updateSavingsMilestone,
  deleteSavingsMilestone,
  SavingsGoal,
  SavingsGoalCreate,
  SavingsMilestone,
  SavingsMilestoneCreate,
} from '@/api/savings';
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
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { Calendar, Plus, Target, TrendingUp, TrendingDown, CheckCircle2, Flag, Trash2, Edit, ChevronRight } from 'lucide-react';

const statusConfig = {
  'on-track': { label: 'On Track', variant: 'default' as const, color: 'text-success' },
  'ahead': { label: 'Ahead', variant: 'secondary' as const, color: 'text-primary' },
  'behind': { label: 'Behind', variant: 'destructive' as const, color: 'text-destructive' },
  'completed': { label: 'Completed', variant: 'default' as const, color: 'text-success' },
};

function calculateGoalStatus(goal: SavingsGoal): 'on-track' | 'ahead' | 'behind' | 'completed' {
  if (goal.current_amount >= goal.target_amount) return 'completed';
  
  const now = new Date();
  const deadline = new Date(goal.deadline);
  const created = new Date(goal.created_at);
  
  const totalDays = (deadline.getTime() - created.getTime()) / (1000 * 60 * 60 * 24);
  const elapsedDays = (now.getTime() - created.getTime()) / (1000 * 60 * 60 * 24);
  
  if (totalDays <= 0) return 'behind';
  
  const expectedProgress = (elapsedDays / totalDays) * goal.target_amount;
  const actualProgress = goal.current_amount;
  
  const variance = (actualProgress - expectedProgress) / goal.target_amount;
  
  if (variance > 0.05) return 'ahead';
  if (variance < -0.05) return 'behind';
  return 'on-track';
}

function getProgressColor(percentage: number): string {
  if (percentage >= 100) return 'bg-success';
  if (percentage >= 75) return 'bg-primary';
  if (percentage >= 50) return 'bg-accent';
  if (percentage >= 25) return 'bg-warning';
  return 'bg-destructive';
}

function GoalDialog({
  open,
  onOpenChange,
  onSubmit,
  initialGoal,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (goal: SavingsGoalCreate) => void;
  initialGoal?: SavingsGoal;
}) {
  const [title, setTitle] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [deadline, setDeadline] = useState('');
  const [currentAmount, setCurrentAmount] = useState('0');

  useEffect(() => {
    if (initialGoal) {
      setTitle(initialGoal.title);
      setTargetAmount(String(initialGoal.target_amount));
      setDeadline(initialGoal.deadline.split('T')[0]);
      setCurrentAmount(String(initialGoal.current_amount));
    } else {
      setTitle('');
      setTargetAmount('');
      setDeadline('');
      setCurrentAmount('0');
    }
  }, [initialGoal, open]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      title,
      target_amount: parseFloat(targetAmount),
      deadline,
      current_amount: parseFloat(currentAmount) || 0,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{initialGoal ? 'Edit Savings Goal' : 'Create Savings Goal'}</DialogTitle>
            <DialogDescription>
              {initialGoal ? 'Update your savings goal details.' : 'Set a new savings goal to track your progress.'}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <label htmlFor="title" className="text-sm font-medium">Goal Title</label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g., Emergency Fund, Vacation"
                required
              />
            </div>
            <div className="grid gap-2">
              <label htmlFor="target" className="text-sm font-medium">Target Amount ($)</label>
              <Input
                id="target"
                type="number"
                min="0"
                step="0.01"
                value={targetAmount}
                onChange={(e) => setTargetAmount(e.target.value)}
                placeholder="10000"
                required
              />
            </div>
            <div className="grid gap-2">
              <label htmlFor="current" className="text-sm font-medium">Current Amount ($)</label>
              <Input
                id="current"
                type="number"
                min="0"
                step="0.01"
                value={currentAmount}
                onChange={(e) => setCurrentAmount(e.target.value)}
                placeholder="0"
              />
            </div>
            <div className="grid gap-2">
              <label htmlFor="deadline" className="text-sm font-medium">Target Date</label>
              <Input
                id="deadline"
                type="date"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                required
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="financial">
              {initialGoal ? 'Save Changes' : 'Create Goal'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MilestoneDialog({
  open,
  onOpenChange,
  onSubmit,
  goalId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (milestone: SavingsMilestoneCreate) => void;
  goalId: number;
}) {
  const [title, setTitle] = useState('');
  const [targetAmount, setTargetAmount] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      goal_id: goalId,
      title,
      target_amount: parseFloat(targetAmount),
    });
    onOpenChange(false);
    setTitle('');
    setTargetAmount('');
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add Milestone</DialogTitle>
            <DialogDescription>
              Create a milestone to track progress toward your goal.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <label htmlFor="milestone-title" className="text-sm font-medium">Milestone Title</label>
              <Input
                id="milestone-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g., $1,000 saved"
                required
              />
            </div>
            <div className="grid gap-2">
              <label htmlFor="milestone-target" className="text-sm font-medium">Target Amount ($)</label>
              <Input
                id="milestone-target"
                type="number"
                min="0"
                step="0.01"
                value={targetAmount}
                onChange={(e) => setTargetAmount(e.target.value)}
                placeholder="1000"
                required
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="financial">Add Milestone</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ContributionDialog({
  open,
  onOpenChange,
  onSubmit,
  goalTitle,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (amount: number, note: string) => void;
  goalTitle: string;
}) {
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(parseFloat(amount), note);
    onOpenChange(false);
    setAmount('');
    setNote('');
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add Contribution</DialogTitle>
            <DialogDescription>
              Record a contribution to your "{goalTitle}" goal.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <label htmlFor="contribution-amount" className="text-sm font-medium">Amount ($)</label>
              <Input
                id="contribution-amount"
                type="number"
                min="0"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="100"
                required
              />
            </div>
            <div className="grid gap-2">
              <label htmlFor="contribution-note" className="text-sm font-medium">Note (optional)</label>
              <Textarea
                id="contribution-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Monthly deposit, bonus, etc."
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="financial">Add Contribution</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function GoalCard({
  goal,
  onEdit,
  onDelete,
  onAddContribution,
  onAddMilestone,
  onToggleMilestone,
  milestones,
}: {
  goal: SavingsGoal;
  onEdit: (goal: SavingsGoal) => void;
  onDelete: (goal: SavingsGoal) => void;
  onAddContribution: (goal: SavingsGoal) => void;
  onAddMilestone: (goal: SavingsGoal) => void;
  onToggleMilestone: (milestone: SavingsMilestone) => void;
  milestones: SavingsMilestone[];
}) {
  const percentage = Math.min((goal.current_amount / goal.target_amount) * 100, 100);
  const remaining = Math.max(goal.target_amount - goal.current_amount, 0);
  const status = calculateGoalStatus(goal);
  const statusInfo = statusConfig[status];
  const isCompleted = status === 'completed';

  const achievedMilestones = milestones.filter(m => m.achieved);
  const pendingMilestones = milestones.filter(m => !m.achieved);

  return (
    <FinancialCard variant="financial" className="fade-in-up">
      <FinancialCardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-primary" />
            <FinancialCardTitle className="text-lg">{goal.title}</FinancialCardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={statusInfo.variant} className={statusInfo.color}>
              {statusInfo.label}
            </Badge>
            <Button variant="ghost" size="sm" onClick={() => onEdit(goal)}>
              <Edit className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => onDelete(goal)}>
              <Trash2 className="w-4 h-4 text-destructive" />
            </Button>
          </div>
        </div>
        <FinancialCardDescription>
          Target: {new Date(goal.deadline).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
        </FinancialCardDescription>
      </FinancialCardHeader>
      <FinancialCardContent className="space-y-6">
        {/* Progress Section */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">
              ${goal.current_amount.toLocaleString()} of ${goal.target_amount.toLocaleString()}
            </span>
            <span className="text-lg font-semibold text-foreground">
              {percentage.toFixed(1)}%
            </span>
          </div>
          <div className="chart-track">
            <div
              className={`chart-fill ${getProgressColor(percentage)}`}
              style={{ width: `${percentage}%` }}
            />
          </div>
          {!isCompleted && (
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>${remaining.toLocaleString()} remaining</span>
              <span>${goal.monthly_target.toLocaleString()}/mo needed</span>
            </div>
          )}
          {isCompleted && (
            <div className="flex items-center gap-2 text-success">
              <CheckCircle2 className="w-4 h-4" />
              <span className="text-sm font-medium">Goal Achieved!</span>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => onAddContribution(goal)}
            disabled={isCompleted}
          >
            <Plus className="w-4 h-4 mr-1" />
            Add Contribution
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => onAddMilestone(goal)}
          >
            <Flag className="w-4 h-4 mr-1" />
            Add Milestone
          </Button>
        </div>

        {/* Milestones Section */}
        {milestones.length > 0 && (
          <div className="space-y-3 pt-4 border-t border-border">
            <div className="flex items-center gap-2">
              <Flag className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium text-muted-foreground">Milestones</span>
            </div>
            
            {/* Achieved Milestones */}
            {achievedMilestones.length > 0 && (
              <div className="space-y-2">
                <span className="text-xs text-muted-foreground uppercase tracking-wide">Achieved</span>
                {achievedMilestones.map((milestone) => (
                  <div
                    key={milestone.id}
                    className="flex items-center justify-between p-2 rounded-md bg-success/10 border border-success/20 cursor-pointer hover:bg-success/20 transition-colors"
                    onClick={() => onToggleMilestone(milestone)}
                  >
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-success" />
                      <span className="text-sm text-foreground">{milestone.title}</span>
                    </div>
                    <span className="text-xs text-success font-medium">
                      ${milestone.target_amount.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Pending Milestones */}
            {pendingMilestones.length > 0 && (
              <div className="space-y-2">
                <span className="text-xs text-muted-foreground uppercase tracking-wide">Pending</span>
                {pendingMilestones.map((milestone) => (
                  <div
                    key={milestone.id}
                    className="flex items-center justify-between p-2 rounded-md bg-muted/50 border border-border cursor-pointer hover:bg-muted transition-colors"
                    onClick={() => onToggleMilestone(milestone)}
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded-full border-2 border-muted-foreground" />
                      <span className="text-sm text-foreground">{milestone.title}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        ${milestone.target_amount.toLocaleString()}
                      </span>
                      <ChevronRight className="w-3 h-3 text-muted-foreground" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </FinancialCardContent>
    </FinancialCard>
  );
}

export function Savings() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [milestones, setMilestones] = useState<Record<number, SavingsMilestone[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showGoalDialog, setShowGoalDialog] = useState(false);
  const [showMilestoneDialog, setShowMilestoneDialog] = useState(false);
  const [showContributionDialog, setShowContributionDialog] = useState(false);
  const [editingGoal, setEditingGoal] = useState<SavingsGoal | undefined>();
  const [selectedGoal, setSelectedGoal] = useState<SavingsGoal | null>(null);

  useEffect(() => {
    loadGoals();
  }, []);

  const loadGoals = async () => {
    try {
      setLoading(true);
      const data = await listSavingsGoals();
      setGoals(data);
      
      // Load milestones for each goal
      const milestoneData: Record<number, SavingsMilestone[]> = {};
      for (const goal of data) {
        try {
          milestoneData[goal.id] = await listSavingsMilestones(goal.id);
        } catch {
          milestoneData[goal.id] = [];
        }
      }
      setMilestones(milestoneData);
      setError(null);
    } catch (err) {
      // If API not available, use demo data
      setGoals(demoGoals);
      setMilestones(demoMilestones);
      setError(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateGoal = async (payload: SavingsGoalCreate) => {
    try {
      const newGoal = await createSavingsGoal(payload);
      setGoals([...goals, newGoal]);
      setMilestones({ ...milestones, [newGoal.id]: [] });
    } catch {
      // Demo mode: add locally
      const newGoal: SavingsGoal = {
        id: Date.now(),
        ...payload,
        monthly_target: payload.target_amount / 12,
        status: 'on-track',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setGoals([...goals, newGoal]);
      setMilestones({ ...milestones, [newGoal.id]: [] });
    }
  };

  const handleUpdateGoal = async (payload: SavingsGoalCreate) => {
    if (!editingGoal) return;
    try {
      const updated = await updateSavingsGoal(editingGoal.id, payload);
      setGoals(goals.map(g => g.id === editingGoal.id ? updated : g));
    } catch {
      setGoals(goals.map(g =>
        g.id === editingGoal.id
          ? { ...g, ...payload, updated_at: new Date().toISOString() }
          : g
      ));
    }
    setEditingGoal(undefined);
  };

  const handleDeleteGoal = async (goal: SavingsGoal) => {
    try {
      await deleteSavingsGoal(goal.id);
      setGoals(goals.filter(g => g.id !== goal.id));
    } catch {
      setGoals(goals.filter(g => g.id !== goal.id));
    }
  };

  const handleAddContribution = async (goal: SavingsGoal) => {
    setSelectedGoal(goal);
    setShowContributionDialog(true);
  };

  const handleContributionSubmit = async (amount: number, note: string) => {
    if (!selectedGoal) return;
    try {
      await addSavingsContribution({
        goal_id: selectedGoal.id,
        amount,
        date: new Date().toISOString(),
        note,
      });
      const updatedGoal = {
        ...selectedGoal,
        current_amount: selectedGoal.current_amount + amount,
        updated_at: new Date().toISOString(),
      };
      setGoals(goals.map(g => g.id === selectedGoal.id ? updatedGoal : g));
    } catch {
      const updatedGoal = {
        ...selectedGoal,
        current_amount: selectedGoal.current_amount + amount,
        updated_at: new Date().toISOString(),
      };
      setGoals(goals.map(g => g.id === selectedGoal.id ? updatedGoal : g));
    }
    setSelectedGoal(null);
  };

  const handleAddMilestone = async (goal: SavingsGoal) => {
    setSelectedGoal(goal);
    setShowMilestoneDialog(true);
  };

  const handleMilestoneSubmit = async (payload: SavingsMilestoneCreate) => {
    if (!selectedGoal) return;
    try {
      const newMilestone = await createSavingsMilestone(payload);
      setMilestones({
        ...milestones,
        [selectedGoal.id]: [...(milestones[selectedGoal.id] || []), newMilestone],
      });
    } catch {
      const newMilestone: SavingsMilestone = {
        id: Date.now(),
        ...payload,
        achieved: false,
        created_at: new Date().toISOString(),
      };
      setMilestones({
        ...milestones,
        [selectedGoal.id]: [...(milestones[selectedGoal.id] || []), newMilestone],
      });
    }
    setSelectedGoal(null);
  };

  const handleToggleMilestone = async (milestone: SavingsMilestone) => {
    try {
      const updated = await updateSavingsMilestone(milestone.id, { achieved: !milestone.achieved });
      const goalId = milestone.goal_id;
      setMilestones({
        ...milestones,
        [goalId]: milestones[goalId].map(m => m.id === milestone.id ? updated : m),
      });
    } catch {
      const goalId = milestone.goal_id;
      setMilestones({
        ...milestones,
        [goalId]: milestones[goalId].map(m =>
          m.id === milestone.id
            ? { ...m, achieved: !m.achieved, achieved_at: !m.achieved ? new Date().toISOString() : undefined }
            : m
        ),
      });
    }
  };

  const totalSaved = goals.reduce((sum, g) => sum + g.current_amount, 0);
  const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0);
  const completedGoals = goals.filter(g => g.current_amount >= g.target_amount).length;

  // Demo data fallback
  const demoGoals: SavingsGoal[] = [
    {
      id: 1,
      title: 'Emergency Fund',
      target_amount: 10000,
      current_amount: 7250,
      deadline: '2025-12-31',
      monthly_target: 458,
      status: 'on-track',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-04-15T00:00:00Z',
    },
    {
      id: 2,
      title: 'Vacation Fund',
      target_amount: 3000,
      current_amount: 1850,
      deadline: '2025-06-30',
      monthly_target: 383,
      status: 'behind',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-04-15T00:00:00Z',
    },
    {
      id: 3,
      title: 'New Car',
      target_amount: 25000,
      current_amount: 15600,
      deadline: '2026-03-31',
      monthly_target: 625,
      status: 'ahead',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-04-15T00:00:00Z',
    },
  ];

  const demoMilestones: Record<number, SavingsMilestone[]> = {
    1: [
      { id: 1, goal_id: 1, title: '$2,500 saved', target_amount: 2500, achieved: true, achieved_at: '2025-02-15T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
      { id: 2, goal_id: 1, title: '$5,000 saved', target_amount: 5000, achieved: true, achieved_at: '2025-03-20T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
      { id: 3, goal_id: 1, title: '$7,500 saved', target_amount: 7500, achieved: false, created_at: '2025-01-01T00:00:00Z' },
    ],
    2: [
      { id: 4, goal_id: 2, title: '$1,000 saved', target_amount: 1000, achieved: true, achieved_at: '2025-02-28T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
      { id: 5, goal_id: 2, title: '$2,000 saved', target_amount: 2000, achieved: false, created_at: '2025-01-01T00:00:00Z' },
    ],
    3: [
      { id: 6, goal_id: 3, title: '$10,000 saved', target_amount: 10000, achieved: true, achieved_at: '2025-03-15T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
      { id: 7, goal_id: 3, title: '$15,000 saved', target_amount: 15000, achieved: true, achieved_at: '2025-04-10T00:00:00Z', created_at: '2025-01-01T00:00:00Z' },
      { id: 8, goal_id: 3, title: '$20,000 saved', target_amount: 20000, achieved: false, created_at: '2025-01-01T00:00:00Z' },
    ],
  };

  if (loading) {
    return (
      <div className="page-wrap">
        <div className="page-header">
          <h1 className="page-title">Savings Goals</h1>
          <p className="page-subtitle">Loading your savings data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">
              Track your savings goals and milestones
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" size="sm">
              <Calendar className="w-4 h-4" />
              All Time
            </Button>
            <DialogTrigger asChild>
              <Button variant="financial" size="sm" onClick={() => setShowGoalDialog(true)}>
                <Plus className="w-4 h-4" />
                New Goal
              </Button>
            </DialogTrigger>
          </div>
        </div>
      </div>

      {/* Overview Cards */}
      <div className="grid gap-4 md:grid-cols-3 mb-8">
        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Saved
              </FinancialCardTitle>
              <Target className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              ${totalSaved.toLocaleString()}
            </div>
            <div className="text-sm text-muted-foreground">
              Across {goals.length} goal{goals.length !== 1 ? 's' : ''}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Target
              </FinancialCardTitle>
              <TrendingUp className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              ${totalTarget.toLocaleString()}
            </div>
            <div className="text-sm text-muted-foreground">
              {totalTarget > 0 ? ((totalSaved / totalTarget) * 100).toFixed(1) : 0}% overall progress
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={completedGoals > 0 ? "success" : "financial"}>
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium">
                {completedGoals > 0 ? 'Goals Achieved' : 'Active Goals'}
              </FinancialCardTitle>
              {completedGoals > 0 ? (
                <CheckCircle2 className="w-5 h-5 text-success" />
              ) : (
                <TrendingDown className="w-5 h-5 text-muted-foreground" />
              )}
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {completedGoals} / {goals.length}
            </div>
            <div className="text-sm text-muted-foreground">
              {completedGoals > 0 ? 'Keep up the great work!' : 'Goals in progress'}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals Grid */}
      {goals.length === 0 ? (
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardContent className="py-12">
            <div className="text-center">
              <Target className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">No savings goals yet</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Create your first savings goal to start tracking your progress.
              </p>
              <Button variant="financial" onClick={() => setShowGoalDialog(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Create Your First Goal
              </Button>
            </div>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {goals.map((goal) => (
            <GoalCard
              key={goal.id}
              goal={goal}
              milestones={milestones[goal.id] || []}
              onEdit={(g) => {
                setEditingGoal(g);
                setShowGoalDialog(true);
              }}
              onDelete={handleDeleteGoal}
              onAddContribution={handleAddContribution}
              onAddMilestone={handleAddMilestone}
              onToggleMilestone={handleToggleMilestone}
            />
          ))}
        </div>
      )}

      {/* Dialogs */}
      <GoalDialog
        open={showGoalDialog}
        onOpenChange={(open) => {
          setShowGoalDialog(open);
          if (!open) setEditingGoal(undefined);
        }}
        onSubmit={editingGoal ? handleUpdateGoal : handleCreateGoal}
        initialGoal={editingGoal}
      />

      {selectedGoal && (
        <>
          <MilestoneDialog
            open={showMilestoneDialog}
            onOpenChange={setShowMilestoneDialog}
            onSubmit={handleMilestoneSubmit}
            goalId={selectedGoal.id}
          />

          <ContributionDialog
            open={showContributionDialog}
            onOpenChange={setShowContributionDialog}
            onSubmit={handleContributionSubmit}
            goalTitle={selectedGoal.title}
          />
        </>
      )}
    </div>
  );
}

export default Savings;
