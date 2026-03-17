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
import { useToast } from '@/hooks/use-toast';
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
import { PiggyBank, Plus, Target, TrendingUp, Trophy, Trash2, PlusCircle } from 'lucide-react';
import {
  listGoals,
  createGoal,
  updateGoal,
  deleteGoal,
  addDeposit,
  type SavingsGoal,
  type SavingsGoalStatus,
} from '@/api/savings';
import { formatMoney } from '@/lib/currency';

const STATUS_COLORS: Record<SavingsGoalStatus, string> = {
  ACTIVE: 'bg-success/10 text-success border-success/20',
  COMPLETED: 'bg-primary/10 text-primary border-primary/20',
  PAUSED: 'bg-warning/10 text-warning border-warning/20',
};

const MILESTONE_LABELS: Record<number, string> = {
  25: '25%',
  50: 'Halfway',
  75: '75%',
  100: 'Goal reached!',
};

function ProgressBar({ pct }: { pct: number }) {
  const clamped = Math.min(100, Math.max(0, pct));
  const color =
    clamped >= 100
      ? 'bg-success'
      : clamped >= 75
      ? 'bg-primary'
      : clamped >= 50
      ? 'bg-info'
      : 'bg-warning';
  return (
    <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

function MilestoneBadges({ reached }: { reached: number[] }) {
  if (!reached.length) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {reached.map((m) => (
        <span
          key={m}
          className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-success/10 text-success border border-success/20"
        >
          <Trophy className="w-3 h-3" />
          {MILESTONE_LABELS[m] ?? `${m}%`}
        </span>
      ))}
    </div>
  );
}

export function Savings() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [depositTarget, setDepositTarget] = useState<SavingsGoal | null>(null);
  const { toast } = useToast();

  // Create form state
  const [form, setForm] = useState({
    name: '',
    target_amount: '',
    currency: 'INR',
    deadline: '',
    notes: '',
    initial_amount: '',
  });

  // Deposit form state
  const [depositForm, setDepositForm] = useState({ amount: '', note: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listGoals();
      setGoals(data);
    } catch {
      toast({ title: 'Failed to load savings goals', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate() {
    if (!form.name || !form.target_amount) {
      toast({ title: 'Name and target amount are required', variant: 'destructive' });
      return;
    }
    try {
      await createGoal({
        name: form.name,
        target_amount: parseFloat(form.target_amount),
        currency: form.currency || 'INR',
        deadline: form.deadline || undefined,
        notes: form.notes || undefined,
        initial_amount: form.initial_amount ? parseFloat(form.initial_amount) : undefined,
      });
      toast({ title: 'Savings goal created' });
      setCreateOpen(false);
      setForm({ name: '', target_amount: '', currency: 'INR', deadline: '', notes: '', initial_amount: '' });
      load();
    } catch (e: unknown) {
      toast({ title: (e as Error).message || 'Failed to create goal', variant: 'destructive' });
    }
  }

  async function handleDeposit() {
    if (!depositTarget || !depositForm.amount) return;
    try {
      await addDeposit(depositTarget.id, {
        amount: parseFloat(depositForm.amount),
        note: depositForm.note || undefined,
      });
      toast({ title: `Deposit added to "${depositTarget.name}"` });
      setDepositTarget(null);
      setDepositForm({ amount: '', note: '' });
      load();
    } catch (e: unknown) {
      toast({ title: (e as Error).message || 'Failed to add deposit', variant: 'destructive' });
    }
  }

  async function handleStatusToggle(goal: SavingsGoal) {
    const next: SavingsGoalStatus = goal.status === 'PAUSED' ? 'ACTIVE' : 'PAUSED';
    try {
      await updateGoal(goal.id, { status: next });
      load();
    } catch {
      toast({ title: 'Failed to update goal', variant: 'destructive' });
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteGoal(id);
      toast({ title: 'Goal deleted' });
      load();
    } catch {
      toast({ title: 'Failed to delete goal', variant: 'destructive' });
    }
  }

  const totalTarget = goals.reduce((s, g) => s + g.target_amount, 0);
  const totalSaved = goals.reduce((s, g) => s + g.current_amount, 0);
  const completedCount = goals.filter((g) => g.status === 'COMPLETED').length;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <PiggyBank className="w-6 h-6 text-primary" />
            Savings Goals
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Track your savings targets and milestones
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2">
              <Plus className="w-4 h-4" /> New Goal
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Savings Goal</DialogTitle>
              <DialogDescription>Set a target and start tracking your progress.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-3 py-2">
              <input
                className="input"
                placeholder="Goal name *"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
              <input
                className="input"
                type="number"
                placeholder="Target amount *"
                value={form.target_amount}
                onChange={(e) => setForm({ ...form, target_amount: e.target.value })}
              />
              <input
                className="input"
                placeholder="Currency (e.g. INR, USD)"
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
              />
              <input
                className="input"
                type="number"
                placeholder="Initial amount (optional)"
                value={form.initial_amount}
                onChange={(e) => setForm({ ...form, initial_amount: e.target.value })}
              />
              <input
                className="input"
                type="date"
                placeholder="Deadline (optional)"
                value={form.deadline}
                onChange={(e) => setForm({ ...form, deadline: e.target.value })}
              />
              <textarea
                className="input resize-none"
                rows={2}
                placeholder="Notes (optional)"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button onClick={handleCreate}>Create Goal</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <FinancialCard>
          <FinancialCardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <Target className="w-5 h-5 text-primary" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Target</p>
                <p className="text-lg font-bold">{formatMoney(totalTarget, 'INR')}</p>
              </div>
            </div>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-success/10">
                <TrendingUp className="w-5 h-5 text-success" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Saved</p>
                <p className="text-lg font-bold">{formatMoney(totalSaved, 'INR')}</p>
              </div>
            </div>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-warning/10">
                <Trophy className="w-5 h-5 text-warning" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Goals Completed</p>
                <p className="text-lg font-bold">{completedCount} / {goals.length}</p>
              </div>
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goal cards */}
      {loading ? (
        <p className="text-muted-foreground text-center py-8">Loading goals...</p>
      ) : goals.length === 0 ? (
        <FinancialCard>
          <FinancialCardContent className="py-12 text-center">
            <PiggyBank className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">No savings goals yet. Create your first one!</p>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {goals.map((goal) => (
            <FinancialCard key={goal.id}>
              <FinancialCardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <FinancialCardTitle className="truncate">{goal.name}</FinancialCardTitle>
                    {goal.deadline && (
                      <FinancialCardDescription>
                        Due {new Date(goal.deadline).toLocaleDateString()}
                      </FinancialCardDescription>
                    )}
                  </div>
                  <Badge className={`shrink-0 text-xs border ${STATUS_COLORS[goal.status]}`}>
                    {goal.status}
                  </Badge>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent className="space-y-3">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-muted-foreground">
                      {formatMoney(goal.current_amount, goal.currency)}
                    </span>
                    <span className="font-medium">
                      {formatMoney(goal.target_amount, goal.currency)}
                    </span>
                  </div>
                  <ProgressBar pct={goal.progress_pct} />
                  <p className="text-xs text-muted-foreground mt-1">{goal.progress_pct.toFixed(1)}% complete</p>
                </div>

                <MilestoneBadges reached={goal.milestones_reached} />

                {goal.next_milestone_pct && goal.status !== 'COMPLETED' && (
                  <p className="text-xs text-muted-foreground">
                    Next milestone: {MILESTONE_LABELS[goal.next_milestone_pct] ?? `${goal.next_milestone_pct}%`}
                  </p>
                )}

                {goal.notes && (
                  <p className="text-xs text-muted-foreground italic truncate">{goal.notes}</p>
                )}

                <div className="flex gap-2 pt-1">
                  {goal.status !== 'COMPLETED' && (
                    <Button
                      size="sm"
                      className="flex-1 gap-1"
                      onClick={() => {
                        setDepositTarget(goal);
                        setDepositForm({ amount: '', note: '' });
                      }}
                    >
                      <PlusCircle className="w-3 h-3" /> Add Funds
                    </Button>
                  )}
                  {goal.status !== 'COMPLETED' && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleStatusToggle(goal)}
                    >
                      {goal.status === 'PAUSED' ? 'Resume' : 'Pause'}
                    </Button>
                  )}
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive px-2">
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete goal?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will permanently delete "{goal.name}" and all its deposits.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => handleDelete(goal.id)}>
                          Delete
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      )}

      {/* Deposit dialog */}
      <Dialog open={!!depositTarget} onOpenChange={(o) => !o && setDepositTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Funds</DialogTitle>
            <DialogDescription>
              Deposit into "{depositTarget?.name}"
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <input
              className="input"
              type="number"
              placeholder="Amount *"
              value={depositForm.amount}
              onChange={(e) => setDepositForm({ ...depositForm, amount: e.target.value })}
            />
            <input
              className="input"
              placeholder="Note (optional)"
              value={depositForm.note}
              onChange={(e) => setDepositForm({ ...depositForm, note: e.target.value })}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDepositTarget(null)}>Cancel</Button>
            <Button onClick={handleDeposit}>Deposit</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
