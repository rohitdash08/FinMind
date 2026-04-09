import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listGoals,
  createGoal,
  updateGoal,
  depositToGoal,
  deleteGoal,
  SavingsGoal,
  GoalCreate,
} from '@/api/goals';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/hooks/use-toast';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Target,
  Plus,
  Pencil,
  Trash2,
  PiggyBank,
  TrendingUp,
  CheckCircle2,
  Clock,
  PauseCircle,
  ArrowDownToLine,
} from 'lucide-react';

// ─── helpers ────────────────────────────────────────────────────────────────

function statusBadge(status: string) {
  switch (status) {
    case 'COMPLETED':
      return <Badge className="bg-success/20 text-success border-success/30">Completed</Badge>;
    case 'PAUSED':
      return <Badge variant="outline" className="text-muted-foreground">Paused</Badge>;
    default:
      return <Badge className="bg-primary/20 text-primary border-primary/30">Active</Badge>;
  }
}

function statusIcon(status: string) {
  switch (status) {
    case 'COMPLETED': return <CheckCircle2 className="w-5 h-5 text-success" />;
    case 'PAUSED':    return <PauseCircle  className="w-5 h-5 text-muted-foreground" />;
    default:          return <Clock        className="w-5 h-5 text-primary" />;
  }
}

const GOAL_ICONS = ['🏖️', '🚗', '🏠', '💍', '🎓', '🌎', '🏥', '💻', '🐾', '🎸'];

// ─── GoalCard ───────────────────────────────────────────────────────────────

function GoalCard({
  goal,
  onDeposit,
  onEdit,
  onDelete,
}: {
  goal: SavingsGoal;
  onDeposit: (g: SavingsGoal) => void;
  onEdit: (g: SavingsGoal) => void;
  onDelete: (id: number) => void;
}) {
  const remaining = goal.target_amount - goal.current_amount;

  return (
    <FinancialCard variant="financial" className="flex flex-col gap-0">
      <FinancialCardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{goal.icon || '🎯'}</span>
            <div>
              <FinancialCardTitle className="text-base font-semibold">{goal.title}</FinancialCardTitle>
              {goal.description && (
                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{goal.description}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {statusIcon(goal.status)}
            {statusBadge(goal.status)}
          </div>
        </div>
      </FinancialCardHeader>

      <FinancialCardContent className="space-y-4">
        {/* Amounts */}
        <div className="flex justify-between items-end">
          <div>
            <p className="text-2xl font-bold">
              {goal.currency} {goal.current_amount.toLocaleString()}
            </p>
            <p className="text-sm text-muted-foreground">
              of {goal.currency} {goal.target_amount.toLocaleString()} goal
            </p>
          </div>
          <div className="text-right">
            <p className="text-lg font-semibold text-primary">{goal.progress_pct}%</p>
            {remaining > 0 && (
              <p className="text-xs text-muted-foreground">
                {goal.currency} {remaining.toLocaleString()} to go
              </p>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <Progress value={Math.min(goal.progress_pct, 100)} className="h-2" />

        {/* Milestones */}
        <div className="flex gap-1 justify-between">
          {goal.milestones.map((m) => (
            <div
              key={m.pct}
              className={`flex flex-col items-center gap-0.5 flex-1 ${m.reached ? 'opacity-100' : 'opacity-40'}`}
            >
              <div
                className={`w-3 h-3 rounded-full ${m.reached ? 'bg-success' : 'bg-muted-foreground/30'}`}
              />
              <span className="text-[10px] text-muted-foreground">{m.pct}%</span>
            </div>
          ))}
        </div>

        {/* Meta row */}
        <div className="flex gap-4 text-sm text-muted-foreground">
          {goal.deadline && (
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              {goal.days_remaining != null && goal.days_remaining > 0
                ? `${goal.days_remaining}d left`
                : 'Deadline passed'}
            </span>
          )}
          {goal.monthly_target && (
            <span className="flex items-center gap-1">
              <TrendingUp className="w-3.5 h-3.5" />
              {goal.currency} {goal.monthly_target.toLocaleString()}/mo
            </span>
          )}
        </div>

        {/* Actions */}
        {goal.status !== 'COMPLETED' && (
          <div className="flex gap-2 pt-1">
            <Button
              size="sm"
              variant="financial"
              className="flex-1 gap-1.5"
              onClick={() => onDeposit(goal)}
            >
              <ArrowDownToLine className="w-4 h-4" />
              Add Funds
            </Button>
            <Button size="sm" variant="outline" className="px-3" onClick={() => onEdit(goal)}>
              <Pencil className="w-4 h-4" />
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="px-3 text-destructive hover:text-destructive"
              onClick={() => onDelete(goal.id)}
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        )}
      </FinancialCardContent>
    </FinancialCard>
  );
}

// ─── GoalFormDialog ──────────────────────────────────────────────────────────

function GoalFormDialog({
  open,
  initial,
  onClose,
  onSave,
}: {
  open: boolean;
  initial: SavingsGoal | null;
  onClose: () => void;
  onSave: (data: GoalCreate) => void;
}) {
  const [form, setForm] = useState<GoalCreate>(() =>
    initial
      ? {
          title: initial.title,
          description: initial.description ?? '',
          target_amount: initial.target_amount,
          current_amount: initial.current_amount,
          currency: initial.currency,
          deadline: initial.deadline ?? '',
          monthly_target: initial.monthly_target ?? undefined,
          icon: initial.icon ?? '',
        }
      : { title: '', target_amount: 0, icon: '🎯' }
  );

  const set = (k: keyof GoalCreate, v: string | number) =>
    setForm((f) => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{initial ? 'Edit Goal' : 'New Savings Goal'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div>
            <Label>Icon</Label>
            <div className="flex gap-2 flex-wrap mt-1">
              {GOAL_ICONS.map((ic) => (
                <button
                  key={ic}
                  type="button"
                  className={`text-xl p-1 rounded border-2 transition-colors ${
                    form.icon === ic ? 'border-primary' : 'border-transparent'
                  }`}
                  onClick={() => set('icon', ic)}
                >
                  {ic}
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label htmlFor="title">Goal Name *</Label>
            <Input
              id="title"
              value={form.title}
              onChange={(e) => set('title', e.target.value)}
              placeholder="Emergency Fund"
              className="mt-1"
            />
          </div>

          <div>
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={form.description ?? ''}
              onChange={(e) => set('description', e.target.value)}
              placeholder="Optional description..."
              className="mt-1 resize-none"
              rows={2}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="target">Target Amount *</Label>
              <Input
                id="target"
                type="number"
                min={0}
                value={form.target_amount || ''}
                onChange={(e) => set('target_amount', parseFloat(e.target.value) || 0)}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="current">Current Savings</Label>
              <Input
                id="current"
                type="number"
                min={0}
                value={form.current_amount || ''}
                onChange={(e) => set('current_amount', parseFloat(e.target.value) || 0)}
                className="mt-1"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="deadline">Target Date</Label>
              <Input
                id="deadline"
                type="date"
                value={form.deadline ?? ''}
                onChange={(e) => set('deadline', e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="monthly">Monthly Target</Label>
              <Input
                id="monthly"
                type="number"
                min={0}
                value={form.monthly_target || ''}
                onChange={(e) =>
                  set('monthly_target', parseFloat(e.target.value) || 0)
                }
                placeholder="Auto-calc"
                className="mt-1"
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="financial"
            onClick={() => onSave(form)}
            disabled={!form.title || !form.target_amount}
          >
            {initial ? 'Save Changes' : 'Create Goal'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── DepositDialog ───────────────────────────────────────────────────────────

function DepositDialog({
  goal,
  onClose,
  onDeposit,
}: {
  goal: SavingsGoal;
  onClose: () => void;
  onDeposit: (amount: number) => void;
}) {
  const [amount, setAmount] = useState('');

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Add Funds — {goal.title}</DialogTitle>
        </DialogHeader>
        <div className="py-2 space-y-3">
          <p className="text-sm text-muted-foreground">
            Current: {goal.currency} {goal.current_amount.toLocaleString()} /{' '}
            {goal.target_amount.toLocaleString()}
          </p>
          <div>
            <Label htmlFor="deposit-amount">Amount ({goal.currency})</Label>
            <Input
              id="deposit-amount"
              type="number"
              min={0.01}
              step={0.01}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              className="mt-1"
              autoFocus
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="financial"
            onClick={() => onDeposit(parseFloat(amount))}
            disabled={!amount || parseFloat(amount) <= 0}
          >
            <PiggyBank className="w-4 h-4 mr-1.5" />
            Add Funds
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Goals page ─────────────────────────────────────────────────────────────

export function Goals() {
  const { toast } = useToast();
  const qc = useQueryClient();

  const [showForm, setShowForm] = useState(false);
  const [editGoal, setEditGoal] = useState<SavingsGoal | null>(null);
  const [depositTarget, setDepositTarget] = useState<SavingsGoal | null>(null);

  const { data: goals = [], isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => listGoals(),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['goals'] });

  const createMut = useMutation({
    mutationFn: createGoal,
    onSuccess: () => { invalidate(); setShowForm(false); toast({ title: 'Goal created!' }); },
    onError: (e: Error) => toast({ title: 'Error', description: e.message, variant: 'destructive' }),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof updateGoal>[1] }) =>
      updateGoal(id, data),
    onSuccess: () => { invalidate(); setEditGoal(null); toast({ title: 'Goal updated!' }); },
    onError: (e: Error) => toast({ title: 'Error', description: e.message, variant: 'destructive' }),
  });

  const depositMut = useMutation({
    mutationFn: ({ id, amount }: { id: number; amount: number }) => depositToGoal(id, amount),
    onSuccess: (updated) => {
      invalidate();
      setDepositTarget(null);
      if (updated.status === 'COMPLETED') {
        toast({ title: '🎉 Goal completed!', description: `You reached your ${updated.title} goal!` });
      } else {
        toast({ title: 'Funds added', description: `${updated.progress_pct}% progress` });
      }
    },
    onError: (e: Error) => toast({ title: 'Error', description: e.message, variant: 'destructive' }),
  });

  const deleteMut = useMutation({
    mutationFn: deleteGoal,
    onSuccess: () => { invalidate(); toast({ title: 'Goal deleted' }); },
    onError: (e: Error) => toast({ title: 'Error', description: e.message, variant: 'destructive' }),
  });

  // Summary stats
  const active = goals.filter((g) => g.status === 'ACTIVE');
  const completed = goals.filter((g) => g.status === 'COMPLETED');
  const totalSaved = goals.reduce((s, g) => s + g.current_amount, 0);
  const totalTarget = goals.reduce((s, g) => s + g.target_amount, 0);

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">Track milestones and build toward your dreams</p>
          </div>
          <Button variant="financial" size="sm" onClick={() => setShowForm(true)}>
            <Plus className="w-4 h-4" />
            New Goal
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-4 mb-8">
        {[
          { label: 'Active Goals', value: active.length, icon: <Target className="w-5 h-5" /> },
          { label: 'Completed', value: completed.length, icon: <CheckCircle2 className="w-5 h-5 text-success" /> },
          {
            label: 'Total Saved',
            value: `${totalSaved.toLocaleString()}`,
            icon: <PiggyBank className="w-5 h-5 text-primary" />,
          },
          {
            label: 'Overall Progress',
            value: totalTarget > 0 ? `${Math.round((totalSaved / totalTarget) * 100)}%` : '—',
            icon: <TrendingUp className="w-5 h-5 text-accent" />,
          },
        ].map(({ label, value, icon }) => (
          <FinancialCard key={label} variant="financial">
            <FinancialCardHeader className="pb-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">{label}</span>
                {icon}
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-2xl font-bold">{value}</p>
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>

      {/* Goal grid */}
      {isLoading ? (
        <p className="text-muted-foreground text-center py-16">Loading goals…</p>
      ) : goals.length === 0 ? (
        <div className="text-center py-20 space-y-3">
          <Target className="w-12 h-12 mx-auto text-muted-foreground/40" />
          <p className="text-muted-foreground">No savings goals yet</p>
          <Button variant="financial" size="sm" onClick={() => setShowForm(true)}>
            <Plus className="w-4 h-4 mr-1" /> Create your first goal
          </Button>
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {goals.map((g) => (
            <GoalCard
              key={g.id}
              goal={g}
              onDeposit={setDepositTarget}
              onEdit={(goal) => { setEditGoal(goal); setShowForm(true); }}
              onDelete={(id) => deleteMut.mutate(id)}
            />
          ))}
        </div>
      )}

      {/* Create / Edit dialog */}
      {showForm && (
        <GoalFormDialog
          open={showForm}
          initial={editGoal}
          onClose={() => { setShowForm(false); setEditGoal(null); }}
          onSave={(data) => {
            if (editGoal) {
              updateMut.mutate({ id: editGoal.id, data });
            } else {
              createMut.mutate(data);
            }
          }}
        />
      )}

      {/* Deposit dialog */}
      {depositTarget && (
        <DepositDialog
          goal={depositTarget}
          onClose={() => setDepositTarget(null)}
          onDeposit={(amount) => depositMut.mutate({ id: depositTarget.id, amount })}
        />
      )}
    </div>
  );
}

export default Goals;
