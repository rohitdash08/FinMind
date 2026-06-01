import { useState, useMemo } from 'react';
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
  Target,
  Plus,
  TrendingUp,
  Calendar,
  DollarSign,
  CheckCircle2,
  Pause,
  Trash2,
  ChevronDown,
  ChevronUp,
  Flag,
  Sparkles,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listGoals,
  createGoal,
  updateGoal,
  deleteGoal,
  depositToGoal,
  type SavingsGoal,
  type GoalCreate,
} from '@/api/goals';
import { toast } from '@/components/ui/use-toast';

const CATEGORIES = [
  'Emergency Fund',
  'Vacation',
  'Home',
  'Car',
  'Education',
  'Retirement',
  'Investment',
  'Other',
];

const PRIORITY_COLORS = {
  low: 'bg-blue-100 text-blue-700',
  medium: 'bg-yellow-100 text-yellow-700',
  high: 'bg-red-100 text-red-700',
};

function GoalCard({
  goal,
  onDeposit,
  onToggle,
  onDelete,
}: {
  goal: SavingsGoal;
  onDeposit: (id: number, amount: number) => void;
  onToggle: (id: number, status: 'active' | 'paused') => void;
  onDelete: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [depositAmount, setDepositAmount] = useState('');

  const progress = Math.min((goal.current_amount / goal.target_amount) * 100, 100);
  const remaining = Math.max(goal.target_amount - goal.current_amount, 0);
  const isCompleted = goal.status === 'completed' || progress >= 100;

  const daysLeft = goal.deadline
    ? Math.max(
        0,
        Math.ceil(
          (new Date(goal.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24),
        ),
      )
    : null;

  const monthlyNeeded =
    daysLeft && daysLeft > 0 ? remaining / (daysLeft / 30) : null;

  const reachedMilestones = goal.milestones.filter((m) => m.reached).length;

  const handleDeposit = () => {
    const amount = parseFloat(depositAmount);
    if (isNaN(amount) || amount <= 0) {
      toast({ title: 'Invalid amount', variant: 'destructive' });
      return;
    }
    onDeposit(goal.id, amount);
    setDepositAmount('');
  };

  return (
    <FinancialCard className="relative overflow-hidden">
      {isCompleted && (
        <div className="absolute top-0 right-0 w-24 h-24 bg-green-500/10 rounded-bl-full flex items-start justify-end p-2">
          <CheckCircle2 className="w-6 h-6 text-green-500" />
        </div>
      )}

      <FinancialCardHeader>
        <div className="flex items-start justify-between">
          <div>
            <FinancialCardTitle className="flex items-center gap-2">
              <Target className="w-5 h-5" />
              {goal.name}
            </FinancialCardTitle>
            <FinancialCardDescription className="flex items-center gap-2 mt-1">
              <Badge variant="outline" className="text-xs">
                {goal.category}
              </Badge>
              <Badge
                variant="secondary"
                className={`text-xs ${PRIORITY_COLORS[goal.priority]}`}
              >
                {goal.priority}
              </Badge>
              {goal.status === 'paused' && (
                <Badge variant="secondary" className="text-xs bg-orange-100 text-orange-700">
                  Paused
                </Badge>
              )}
            </FinancialCardDescription>
          </div>
        </div>
      </FinancialCardHeader>

      <FinancialCardContent>
        {/* Progress bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">
              ${goal.current_amount.toLocaleString()} saved
            </span>
            <span className="font-medium">
              ${goal.target_amount.toLocaleString()} goal
            </span>
          </div>
          <div className="h-3 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                isCompleted ? 'bg-green-500' : 'bg-primary'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{progress.toFixed(1)}% complete</span>
            <span>${remaining.toLocaleString()} remaining</span>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4 mt-4">
          <div className="text-center">
            <p className="text-xs text-muted-foreground">Deadline</p>
            <p className="text-sm font-medium">
              {goal.deadline
                ? new Date(goal.deadline).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })
                : 'None'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-xs text-muted-foreground">Days Left</p>
            <p className="text-sm font-medium">
              {daysLeft !== null ? daysLeft : '∞'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-xs text-muted-foreground">Milestones</p>
            <p className="text-sm font-medium">
              {reachedMilestones}/{goal.milestones.length}
            </p>
          </div>
        </div>

        {monthlyNeeded !== null && monthlyNeeded > 0 && !isCompleted && (
          <div className="mt-3 p-2 bg-muted/50 rounded-lg flex items-center gap-2 text-sm">
            <TrendingUp className="w-4 h-4 text-primary" />
            <span>
              Save <strong>${monthlyNeeded.toFixed(0)}/month</strong> to reach
              your goal on time
            </span>
          </div>
        )}

        {/* Deposit input */}
        {!isCompleted && goal.status === 'active' && (
          <div className="mt-4 flex gap-2">
            <div className="relative flex-1">
              <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="Add funds"
                value={depositAmount}
                onChange={(e) => setDepositAmount(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleDeposit()}
                className="w-full pl-9 pr-3 py-2 text-sm border rounded-md bg-background"
              />
            </div>
            <Button size="sm" onClick={handleDeposit}>
              Deposit
            </Button>
          </div>
        )}

        {/* Milestones */}
        {goal.milestones.length > 0 && (
          <div className="mt-4">
            <button
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
              Milestones ({goal.milestones.length})
            </button>
            {expanded && (
              <div className="mt-2 space-y-2">
                {goal.milestones.map((milestone) => (
                  <div
                    key={milestone.id}
                    className={`flex items-center gap-2 p-2 rounded-md text-sm ${
                      milestone.reached
                        ? 'bg-green-50 text-green-700'
                        : 'bg-muted/50'
                    }`}
                  >
                    <Flag
                      className={`w-4 h-4 ${
                        milestone.reached ? 'text-green-500' : 'text-muted-foreground'
                      }`}
                    />
                    <span className="flex-1">{milestone.title}</span>
                    <span className="text-xs text-muted-foreground">
                      ${milestone.target_amount.toLocaleString()}
                    </span>
                    {milestone.reached && (
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </FinancialCardContent>

      <FinancialCardFooter className="flex gap-2">
        {!isCompleted && (
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() =>
              onToggle(goal.id, goal.status === 'active' ? 'paused' : 'active')
            }
          >
            <Pause className="w-4 h-4 mr-1" />
            {goal.status === 'active' ? 'Pause' : 'Resume'}
          </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          className="text-destructive hover:text-destructive"
          onClick={() => onDelete(goal.id)}
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      </FinancialCardFooter>
    </FinancialCard>
  );
}

function NewGoalForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<GoalCreate>({
    name: '',
    target_amount: 0,
    deadline: null,
    category: 'Other',
    priority: 'medium',
  });

  const createMutation = useMutation({
    mutationFn: createGoal,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      toast({ title: 'Goal created!' });
      onClose();
    },
    onError: (err: Error) => {
      toast({ title: 'Failed to create goal', description: err.message, variant: 'destructive' });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || form.target_amount <= 0) {
      toast({ title: 'Name and target amount are required', variant: 'destructive' });
      return;
    }
    createMutation.mutate(form);
  };

  return (
    <FinancialCard>
      <FinancialCardHeader>
        <FinancialCardTitle className="flex items-center gap-2">
          <Sparkles className="w-5 h-5" />
          New Savings Goal
        </FinancialCardTitle>
      </FinancialCardHeader>
      <form onSubmit={handleSubmit}>
        <FinancialCardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">Goal Name</label>
            <input
              type="text"
              placeholder="e.g., Emergency Fund"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full mt-1 px-3 py-2 text-sm border rounded-md bg-background"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium">Target Amount ($)</label>
              <input
                type="number"
                min="1"
                step="0.01"
                placeholder="10000"
                value={form.target_amount || ''}
                onChange={(e) =>
                  setForm({ ...form, target_amount: parseFloat(e.target.value) || 0 })
                }
                className="w-full mt-1 px-3 py-2 text-sm border rounded-md bg-background"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium">Deadline</label>
              <input
                type="date"
                value={form.deadline || ''}
                onChange={(e) =>
                  setForm({ ...form, deadline: e.target.value || null })
                }
                className="w-full mt-1 px-3 py-2 text-sm border rounded-md bg-background"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium">Category</label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full mt-1 px-3 py-2 text-sm border rounded-md bg-background"
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium">Priority</label>
              <select
                value={form.priority}
                onChange={(e) =>
                  setForm({ ...form, priority: e.target.value as 'low' | 'medium' | 'high' })
                }
                className="w-full mt-1 px-3 py-2 text-sm border rounded-md bg-background"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>
        </FinancialCardContent>
        <FinancialCardFooter className="flex gap-2">
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" disabled={createMutation.isPending} className="flex-1">
            {createMutation.isPending ? 'Creating...' : 'Create Goal'}
          </Button>
        </FinancialCardFooter>
      </form>
    </FinancialCard>
  );
}

export function Goals() {
  const queryClient = useQueryClient();
  const [showNewGoal, setShowNewGoal] = useState(false);

  const { data: goals = [], isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: listGoals,
  });

  const depositMutation = useMutation({
    mutationFn: ({ id, amount }: { id: number; amount: number }) =>
      depositToGoal(id, { amount }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      toast({ title: 'Deposit successful!' });
    },
    onError: (err: Error) => {
      toast({ title: 'Deposit failed', description: err.message, variant: 'destructive' });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'active' | 'paused' }) =>
      updateGoal(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteGoal,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      toast({ title: 'Goal deleted' });
    },
  });

  const stats = useMemo(() => {
    const active = goals.filter((g) => g.status === 'active');
    const completed = goals.filter((g) => g.status === 'completed' || g.current_amount >= g.target_amount);
    const totalSaved = goals.reduce((sum, g) => sum + g.current_amount, 0);
    const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0);
    return { active, completed, totalSaved, totalTarget };
  }, [goals]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Savings Goals</h1>
          <p className="text-muted-foreground">
            Track your financial goals and milestones
          </p>
        </div>
        <Button onClick={() => setShowNewGoal(!showNewGoal)}>
          <Plus className="w-4 h-4 mr-2" />
          New Goal
        </Button>
      </div>

      {/* Summary stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Total Saved</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-green-600">
              ${stats.totalSaved.toLocaleString()}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Total Target</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              ${stats.totalTarget.toLocaleString()}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Active Goals</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              {stats.active.length}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription>Completed</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-green-600">
              {stats.completed.length}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
      </div>

      {showNewGoal && <NewGoalForm onClose={() => setShowNewGoal(false)} />}

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2].map((i) => (
            <FinancialCard key={i} className="h-64 animate-pulse bg-muted/50" />
          ))}
        </div>
      ) : goals.length === 0 ? (
        <FinancialCard>
          <FinancialCardContent className="flex flex-col items-center justify-center py-12">
            <Target className="w-12 h-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium">No savings goals yet</p>
            <p className="text-sm text-muted-foreground mb-4">
              Create your first goal to start tracking your savings
            </p>
            <Button onClick={() => setShowNewGoal(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Create Goal
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {goals.map((goal) => (
            <GoalCard
              key={goal.id}
              goal={goal}
              onDeposit={(id, amount) => depositMutation.mutate({ id, amount })}
              onToggle={(id, status) => toggleMutation.mutate({ id, status })}
              onDelete={(id) => {
                if (confirm('Delete this goal? This cannot be undone.')) {
                  deleteMutation.mutate(id);
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default Goals;
