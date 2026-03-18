import { useState, useEffect, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
  PiggyBank,
  Plus,
  Target,
  Trophy,
  TrendingUp,
  Pause,
  Play,
  Trash2,
  DollarSign,
  Calendar,
  CheckCircle2,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  listGoals,
  createGoal,
  updateGoal,
  deleteGoal,
  addDeposit,
  getSummary,
  type SavingsGoal,
  type SavingsSummary,
} from '@/api/savings';
import { formatMoney } from '@/lib/currency';

const MILESTONE_LABELS: Record<number, string> = {
  25: '25%',
  50: '50%',
  75: '75%',
  100: '100% — Completed!',
};

function MilestoneBadge({ pct }: { pct: number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
      <Trophy className="h-3 w-3" />
      {MILESTONE_LABELS[pct] ?? `${pct}%`}
    </span>
  );
}

function ProgressBar({ pct, color }: { pct: number; color: string }) {
  const clamped = Math.min(100, Math.max(0, pct));
  return (
    <div className="chart-track h-2 overflow-hidden rounded-full">
      <div
        className="h-full rounded-full transition-all duration-700"
        style={{ width: `${clamped}%`, backgroundColor: color }}
      />
    </div>
  );
}

function statusVariant(status: string): 'default' | 'secondary' | 'destructive' {
  if (status === 'COMPLETED') return 'secondary';
  if (status === 'PAUSED') return 'destructive';
  return 'default';
}

// ---------------------------------------------------------------------------
// Create goal dialog
// ---------------------------------------------------------------------------

function CreateGoalDialog({ onCreated }: { onCreated: () => void }) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [target, setTarget] = useState('');
  const [deadline, setDeadline] = useState('');
  const [color, setColor] = useState('#6366f1');
  const [loading, setLoading] = useState(false);

  const reset = () => {
    setName('');
    setTarget('');
    setDeadline('');
    setColor('#6366f1');
  };

  const handleSubmit = async () => {
    if (!name.trim() || !target) return;
    setLoading(true);
    try {
      await createGoal({
        name: name.trim(),
        target_amount: parseFloat(target),
        deadline: deadline || null,
        color,
      });
      toast({ title: 'Goal created', description: `"${name}" goal has been added.` });
      setOpen(false);
      reset();
      onCreated();
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to create goal',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="financial" size="sm">
          <Plus className="h-4 w-4" />
          New Goal
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create Savings Goal</DialogTitle>
          <DialogDescription>Set a target and start tracking your progress.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <label className="text-sm font-medium">Goal Name</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="e.g. Emergency Fund"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Target Amount</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              type="number"
              min="0.01"
              step="0.01"
              placeholder="0.00"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Deadline (optional)</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium">Color</label>
            <input
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="h-8 w-10 cursor-pointer rounded border border-input"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button variant="financial" onClick={() => void handleSubmit()} disabled={loading}>
            {loading ? 'Creating…' : 'Create Goal'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Deposit dialog
// ---------------------------------------------------------------------------

function DepositDialog({
  goal,
  onDeposited,
}: {
  goal: SavingsGoal;
  onDeposited: (milestones: number[]) => void;
}) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!amount) return;
    setLoading(true);
    try {
      const res = await addDeposit(goal.id, { amount: parseFloat(amount), note: note || undefined });
      toast({
        title: 'Deposit added',
        description: `${formatMoney(res.deposit.amount, goal.currency)} saved towards "${goal.name}".`,
      });
      setOpen(false);
      setAmount('');
      setNote('');
      onDeposited(res.milestones_newly_reached);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to add deposit',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <DollarSign className="h-3.5 w-3.5" />
          Add Funds
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Add Funds</DialogTitle>
          <DialogDescription>Deposit towards "{goal.name}"</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <label className="text-sm font-medium">Amount</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              type="number"
              min="0.01"
              step="0.01"
              placeholder="0.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Note (optional)</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="e.g. Monthly contribution"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button variant="financial" onClick={() => void handleSubmit()} disabled={loading}>
            {loading ? 'Saving…' : 'Deposit'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Goal card
// ---------------------------------------------------------------------------

function GoalCard({ goal, onRefresh }: { goal: SavingsGoal; onRefresh: () => void }) {
  const { toast } = useToast();

  const handleTogglePause = async () => {
    try {
      const newStatus = goal.status === 'PAUSED' ? 'ACTIVE' : 'PAUSED';
      await updateGoal(goal.id, { status: newStatus });
      toast({ title: newStatus === 'PAUSED' ? 'Goal paused' : 'Goal resumed' });
      onRefresh();
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to update goal',
      });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteGoal(goal.id);
      toast({ title: 'Goal deleted', description: `"${goal.name}" has been removed.` });
      onRefresh();
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to delete goal',
      });
    }
  };

  const handleDeposited = (milestones: number[]) => {
    if (milestones.length > 0) {
      toast({
        title: `Milestone reached: ${milestones[milestones.length - 1]}%`,
        description:
          milestones[milestones.length - 1] === 100
            ? 'Congratulations — goal complete!'
            : `You reached the ${milestones[milestones.length - 1]}% milestone for "${goal.name}"!`,
      });
    }
    onRefresh();
  };

  const remaining = goal.target_amount - goal.current_amount;

  return (
    <FinancialCard variant="financial" className="fade-in-up">
      <FinancialCardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ backgroundColor: `${goal.color}22` }}>
              <PiggyBank className="h-4 w-4" style={{ color: goal.color }} />
            </div>
            <div>
              <FinancialCardTitle className="text-sm font-semibold leading-tight">
                {goal.name}
              </FinancialCardTitle>
              {goal.deadline && (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Calendar className="h-3 w-3" />
                  {goal.deadline}
                </div>
              )}
            </div>
          </div>
          <Badge variant={statusVariant(goal.status)} className="text-xs">
            {goal.status === 'COMPLETED' ? (
              <CheckCircle2 className="mr-1 h-3 w-3" />
            ) : null}
            {goal.status}
          </Badge>
        </div>
      </FinancialCardHeader>

      <FinancialCardContent className="space-y-4">
        {/* Amount row */}
        <div className="flex items-end justify-between">
          <div>
            <div className="text-xl font-bold text-foreground">
              {formatMoney(goal.current_amount, goal.currency)}
            </div>
            <div className="text-xs text-muted-foreground">
              of {formatMoney(goal.target_amount, goal.currency)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-lg font-semibold" style={{ color: goal.color }}>
              {goal.progress_pct.toFixed(1)}%
            </div>
            {remaining > 0 && (
              <div className="text-xs text-muted-foreground">
                {formatMoney(remaining, goal.currency)} to go
              </div>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <ProgressBar pct={goal.progress_pct} color={goal.color} />

        {/* Milestones */}
        {goal.milestones_reached.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {goal.milestones_reached.map((m) => (
              <MilestoneBadge key={m} pct={m} />
            ))}
          </div>
        )}

        {/* Estimated completion */}
        {goal.estimated_completion && goal.status === 'ACTIVE' && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <TrendingUp className="h-3 w-3" />
            Est. completion: {goal.estimated_completion}
          </div>
        )}

        {/* Action buttons */}
        {goal.status !== 'COMPLETED' && (
          <div className="flex items-center gap-2 pt-1">
            <DepositDialog goal={goal} onDeposited={handleDeposited} />

            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleTogglePause()}
              className="text-muted-foreground"
            >
              {goal.status === 'PAUSED' ? (
                <>
                  <Play className="h-3.5 w-3.5" />
                  Resume
                </>
              ) : (
                <>
                  <Pause className="h-3.5 w-3.5" />
                  Pause
                </>
              )}
            </Button>

            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="sm" className="ml-auto text-destructive hover:text-destructive">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete goal?</AlertDialogTitle>
                  <AlertDialogDescription>
                    "{goal.name}" and all its deposit history will be permanently deleted.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={() => void handleDelete()}>Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </FinancialCardContent>
    </FinancialCard>
  );
}

// ---------------------------------------------------------------------------
// Summary bar
// ---------------------------------------------------------------------------

function SummaryBar({ summary }: { summary: SavingsSummary }) {
  return (
    <div className="grid gap-4 md:grid-cols-4 mb-8">
      <FinancialCard variant="financial">
        <FinancialCardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <FinancialCardTitle className="text-xs font-medium text-muted-foreground">
              Total Saved
            </FinancialCardTitle>
            <PiggyBank className="h-4 w-4 text-muted-foreground" />
          </div>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="metric-value text-foreground">{formatMoney(summary.total_saved)}</div>
          <div className="text-xs text-muted-foreground mt-1">
            of {formatMoney(summary.total_target)} total target
          </div>
        </FinancialCardContent>
      </FinancialCard>

      <FinancialCard variant="financial">
        <FinancialCardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <FinancialCardTitle className="text-xs font-medium text-muted-foreground">
              Remaining
            </FinancialCardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </div>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="metric-value text-foreground">{formatMoney(summary.total_remaining)}</div>
          <div className="text-xs text-muted-foreground mt-1">across all active goals</div>
        </FinancialCardContent>
      </FinancialCard>

      <FinancialCard variant="financial">
        <FinancialCardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <FinancialCardTitle className="text-xs font-medium text-muted-foreground">
              Overall Progress
            </FinancialCardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </div>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="metric-value text-foreground">{summary.overall_progress_pct.toFixed(1)}%</div>
          <div className="text-xs text-muted-foreground mt-1">
            {summary.active_goals} active, {summary.completed_goals} completed
          </div>
        </FinancialCardContent>
      </FinancialCard>

      <FinancialCard variant={summary.completed_goals > 0 ? 'success' : 'financial'}>
        <FinancialCardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <FinancialCardTitle className="text-xs font-medium">
              Goals Completed
            </FinancialCardTitle>
            <Trophy className="h-4 w-4" />
          </div>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="metric-value">{summary.completed_goals}</div>
          <div className="text-xs opacity-80 mt-1">
            {summary.nearest_deadline
              ? `Next deadline: ${summary.nearest_deadline}`
              : 'No upcoming deadlines'}
          </div>
        </FinancialCardContent>
      </FinancialCard>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function Savings() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [summary, setSummary] = useState<SavingsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [goalsData, summaryData] = await Promise.all([listGoals(), getSummary()]);
      setGoals(goalsData);
      setSummary(summaryData);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to load savings goals',
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const activeGoals = goals.filter((g) => g.status === 'ACTIVE');
  const pausedGoals = goals.filter((g) => g.status === 'PAUSED');
  const completedGoals = goals.filter((g) => g.status === 'COMPLETED');

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">
              Track progress toward your financial goals with milestone badges
            </p>
          </div>
          <CreateGoalDialog onCreated={() => void load()} />
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          Loading…
        </div>
      ) : (
        <>
          {summary && <SummaryBar summary={summary} />}

          {goals.length === 0 ? (
            <FinancialCard variant="financial" className="text-center py-16">
              <FinancialCardContent>
                <PiggyBank className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                <FinancialCardTitle className="mb-2">No savings goals yet</FinancialCardTitle>
                <FinancialCardDescription>
                  Create your first goal to start tracking your savings progress.
                </FinancialCardDescription>
              </FinancialCardContent>
            </FinancialCard>
          ) : (
            <div className="space-y-8">
              {/* Active goals */}
              {activeGoals.length > 0 && (
                <section>
                  <h2 className="section-title mb-4">Active Goals</h2>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {activeGoals.map((g) => (
                      <GoalCard key={g.id} goal={g} onRefresh={() => void load()} />
                    ))}
                  </div>
                </section>
              )}

              {/* Paused goals */}
              {pausedGoals.length > 0 && (
                <section>
                  <h2 className="section-title mb-4">Paused Goals</h2>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {pausedGoals.map((g) => (
                      <GoalCard key={g.id} goal={g} onRefresh={() => void load()} />
                    ))}
                  </div>
                </section>
              )}

              {/* Completed goals */}
              {completedGoals.length > 0 && (
                <section>
                  <h2 className="section-title mb-4">Completed Goals</h2>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {completedGoals.map((g) => (
                      <GoalCard key={g.id} goal={g} onRefresh={() => void load()} />
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
