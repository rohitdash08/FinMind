import { useState, useEffect, useCallback } from 'react';
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
import { Progress } from '@/components/ui/progress';
import {
  PiggyBank,
  Plus,
  Target,
  TrendingUp,
  Calendar,
  DollarSign,
  Trash2,
  Edit,
  ArrowDownToLine,
  ArrowUpFromLine,
  CheckCircle,
  Clock,
  Award,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  listSavingsGoals,
  createSavingsGoal,
  updateSavingsGoal,
  deleteSavingsGoal,
  addContribution,
  withdrawFromGoal,
  getSavingsSummary,
  type SavingsGoal,
  type SavingsSummary,
} from '@/api/savings';
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
import { formatMoney } from '@/lib/currency';

const GOAL_COLORS = [
  '#6366f1',
  '#22c55e',
  '#f59e0b',
  '#ef4444',
  '#3b82f6',
  '#8b5cf6',
  '#ec4899',
  '#14b8a6',
];

const GOAL_ICONS: { value: string; label: string }[] = [
  { value: 'piggy-bank', label: 'Piggy Bank' },
  { value: 'home', label: 'Home' },
  { value: 'car', label: 'Car' },
  { value: 'plane', label: 'Travel' },
  { value: 'graduation', label: 'Education' },
  { value: 'shield', label: 'Emergency' },
  { value: 'gift', label: 'Gift' },
  { value: 'star', label: 'Other' },
];

function GoalIcon({ icon, color }: { icon: string; color: string }) {
  const style = { backgroundColor: color + '20', color };
  const iconClass = 'w-6 h-6';
  switch (icon) {
    case 'home':
      return (
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center"
          style={style}
        >
          <Target className={iconClass} />
        </div>
      );
    case 'shield':
      return (
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center"
          style={style}
        >
          <Award className={iconClass} />
        </div>
      );
    case 'car':
    case 'plane':
    case 'graduation':
    case 'gift':
    case 'star':
      return (
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center"
          style={style}
        >
          <Target className={iconClass} />
        </div>
      );
    default:
      return (
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center"
          style={style}
        >
          <PiggyBank className={iconClass} />
        </div>
      );
  }
}

export default function SavingsGoals() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [summary, setSummary] = useState<SavingsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('ACTIVE');

  // Create dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [targetDate, setTargetDate] = useState('');
  const [selectedColor, setSelectedColor] = useState(GOAL_COLORS[0]);
  const [selectedIcon, setSelectedIcon] = useState('piggy-bank');
  const [saving, setSaving] = useState(false);

  // Contribution dialog state
  const [contribOpen, setContribOpen] = useState(false);
  const [contribGoalId, setContribGoalId] = useState<number | null>(null);
  const [contribAmount, setContribAmount] = useState('');
  const [contribNote, setContribNote] = useState('');
  const [contribMode, setContribMode] = useState<'deposit' | 'withdraw'>(
    'deposit',
  );

  // Edit dialog state
  const [editOpen, setEditOpen] = useState(false);
  const [editGoal, setEditGoal] = useState<SavingsGoal | null>(null);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editTarget, setEditTarget] = useState('');
  const [editDate, setEditDate] = useState('');

  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [goalsData, summaryData] = await Promise.all([
        listSavingsGoals(statusFilter),
        getSavingsSummary(),
      ]);
      setGoals(goalsData);
      setSummary(summaryData);
    } catch (error: unknown) {
      toast({
        title: 'Failed to load savings goals',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setLoading(false);
    }
  }, [toast, statusFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate() {
    if (!name.trim() || !targetAmount) return;
    setSaving(true);
    try {
      await createSavingsGoal({
        name: name.trim(),
        description: description.trim() || undefined,
        target_amount: Number(targetAmount),
        target_date: targetDate || undefined,
        color: selectedColor,
        icon: selectedIcon,
      });
      await refresh();
      setCreateOpen(false);
      setName('');
      setDescription('');
      setTargetAmount('');
      setTargetDate('');
      setSelectedColor(GOAL_COLORS[0]);
      setSelectedIcon('piggy-bank');
      toast({ title: 'Savings goal created' });
    } catch (error: unknown) {
      toast({
        title: 'Failed to create goal',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setSaving(false);
    }
  }

  async function onContribute() {
    if (!contribGoalId || !contribAmount) return;
    setSaving(true);
    try {
      if (contribMode === 'deposit') {
        await addContribution(contribGoalId, {
          amount: Number(contribAmount),
          note: contribNote.trim() || undefined,
        });
        toast({ title: 'Contribution added' });
      } else {
        await withdrawFromGoal(contribGoalId, {
          amount: Number(contribAmount),
          note: contribNote.trim() || undefined,
        });
        toast({ title: 'Withdrawal processed' });
      }
      await refresh();
      setContribOpen(false);
      setContribAmount('');
      setContribNote('');
    } catch (error: unknown) {
      toast({
        title: contribMode === 'deposit' ? 'Failed to add' : 'Failed to withdraw',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setSaving(false);
    }
  }

  async function onEdit() {
    if (!editGoal) return;
    setSaving(true);
    try {
      await updateSavingsGoal(editGoal.id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
        target_amount: Number(editTarget),
        target_date: editDate || undefined,
      });
      await refresh();
      setEditOpen(false);
      toast({ title: 'Goal updated' });
    } catch (error: unknown) {
      toast({
        title: 'Failed to update goal',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setSaving(false);
    }
  }

  function openContribDialog(goalId: number, mode: 'deposit' | 'withdraw') {
    setContribGoalId(goalId);
    setContribMode(mode);
    setContribAmount('');
    setContribNote('');
    setContribOpen(true);
  }

  function openEditDialog(goal: SavingsGoal) {
    setEditGoal(goal);
    setEditName(goal.name);
    setEditDescription(goal.description || '');
    setEditTarget(String(goal.target_amount));
    setEditDate(goal.target_date || '');
    setEditOpen(true);
  }

  function getProgressColor(pct: number): string {
    if (pct >= 100) return 'bg-green-500';
    if (pct >= 75) return 'bg-emerald-500';
    if (pct >= 50) return 'bg-blue-500';
    if (pct >= 25) return 'bg-amber-500';
    return 'bg-slate-400';
  }

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">
              Track your savings progress and reach your financial milestones
            </p>
          </div>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button variant="financial" size="sm">
                <Plus className="w-4 h-4" />
                New Goal
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>Create Savings Goal</DialogTitle>
                <DialogDescription>
                  Set a financial target and track your progress toward it.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Goal Name
                  </label>
                  <input
                    className="input w-full"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g., Emergency Fund, Vacation, New Car"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Description (optional)
                  </label>
                  <input
                    className="input w-full"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What is this goal for?"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Target Amount
                    </label>
                    <input
                      className="input w-full"
                      type="number"
                      min="1"
                      step="0.01"
                      value={targetAmount}
                      onChange={(e) => setTargetAmount(e.target.value)}
                      placeholder="10,000"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Target Date (optional)
                    </label>
                    <input
                      className="input w-full"
                      type="date"
                      value={targetDate}
                      onChange={(e) => setTargetDate(e.target.value)}
                      min={new Date().toISOString().slice(0, 10)}
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Icon</label>
                  <div className="flex flex-wrap gap-2">
                    {GOAL_ICONS.map((ic) => (
                      <button
                        key={ic.value}
                        type="button"
                        onClick={() => setSelectedIcon(ic.value)}
                        className={`px-3 py-1.5 text-xs rounded-full border transition ${
                          selectedIcon === ic.value
                            ? 'border-primary bg-primary/10 text-primary font-semibold'
                            : 'border-border text-muted-foreground hover:bg-muted'
                        }`}
                      >
                        {ic.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Color
                  </label>
                  <div className="flex gap-2">
                    {GOAL_COLORS.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => setSelectedColor(c)}
                        className={`w-8 h-8 rounded-full border-2 transition ${
                          selectedColor === c
                            ? 'border-foreground scale-110'
                            : 'border-transparent'
                        }`}
                        style={{ backgroundColor: c }}
                      />
                    ))}
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setCreateOpen(false)}
                  disabled={saving}
                >
                  Cancel
                </Button>
                <Button
                  onClick={onCreate}
                  disabled={saving || !name.trim() || !targetAmount}
                >
                  {saving ? 'Creating...' : 'Create Goal'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-4 mb-8">
          <FinancialCard variant="financial">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Total Saved
                </FinancialCardTitle>
                <PiggyBank className="w-5 h-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {formatMoney(summary.total_saved)}
              </div>
              <div className="text-sm text-muted-foreground">
                across {summary.total_goals} goal
                {summary.total_goals !== 1 ? 's' : ''}
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Total Target
                </FinancialCardTitle>
                <Target className="w-5 h-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {formatMoney(summary.total_target)}
              </div>
              <div className="text-sm text-muted-foreground">
                {summary.active_goals} active goal
                {summary.active_goals !== 1 ? 's' : ''}
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard
            variant={
              summary.overall_progress_pct >= 100 ? 'success' : 'financial'
            }
          >
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Overall Progress
                </FinancialCardTitle>
                <TrendingUp className="w-5 h-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {summary.overall_progress_pct}%
              </div>
              <Progress
                value={Math.min(summary.overall_progress_pct, 100)}
                className="h-2"
              />
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Completed
                </FinancialCardTitle>
                <CheckCircle className="w-5 h-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {summary.completed_goals}
              </div>
              <div className="text-sm text-muted-foreground">
                goal{summary.completed_goals !== 1 ? 's' : ''} achieved
              </div>
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Status Filter Tabs */}
      <div className="flex gap-2 mb-6">
        {(['ACTIVE', 'COMPLETED', 'ALL'] as const).map((s) => (
          <Button
            key={s}
            variant={statusFilter === s ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(s)}
          >
            {s === 'ALL' ? 'All Goals' : s.charAt(0) + s.slice(1).toLowerCase()}
          </Button>
        ))}
      </div>

      {/* Goals List */}
      {loading ? (
        <div className="text-center py-12 text-muted-foreground">
          Loading savings goals...
        </div>
      ) : goals.length === 0 ? (
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardContent className="py-12 text-center">
            <PiggyBank className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No savings goals yet</h3>
            <p className="text-muted-foreground mb-4">
              Start by creating your first savings goal to track your progress
              toward financial milestones.
            </p>
            <Button variant="financial" onClick={() => setCreateOpen(true)}>
              <Plus className="w-4 h-4" />
              Create Your First Goal
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {goals.map((goal) => (
            <FinancialCard
              key={goal.id}
              variant="financial"
              className="fade-in-up relative overflow-hidden"
            >
              {/* Color accent bar */}
              <div
                className="absolute top-0 left-0 right-0 h-1"
                style={{ backgroundColor: goal.color }}
              />

              <FinancialCardHeader className="pt-5">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <GoalIcon icon={goal.icon} color={goal.color} />
                    <div>
                      <FinancialCardTitle className="text-base font-semibold">
                        {goal.name}
                      </FinancialCardTitle>
                      {goal.description && (
                        <FinancialCardDescription className="text-xs mt-0.5">
                          {goal.description}
                        </FinancialCardDescription>
                      )}
                    </div>
                  </div>
                  <Badge
                    variant={
                      goal.status === 'COMPLETED' ? 'default' : 'secondary'
                    }
                    className="text-xs"
                  >
                    {goal.status === 'COMPLETED' ? (
                      <>
                        <CheckCircle className="w-3 h-3 mr-1" />
                        Done
                      </>
                    ) : (
                      <>
                        <Clock className="w-3 h-3 mr-1" />
                        Active
                      </>
                    )}
                  </Badge>
                </div>
              </FinancialCardHeader>

              <FinancialCardContent>
                {/* Progress bar */}
                <div className="mb-4">
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="font-semibold text-foreground">
                      {formatMoney(goal.current_amount, goal.currency)}
                    </span>
                    <span className="text-muted-foreground">
                      {formatMoney(goal.target_amount, goal.currency)}
                    </span>
                  </div>
                  <div className="relative h-3 w-full overflow-hidden rounded-full bg-secondary">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${getProgressColor(goal.progress_pct)}`}
                      style={{
                        width: `${Math.min(goal.progress_pct, 100)}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between mt-1.5">
                    <span className="text-xs text-muted-foreground">
                      {goal.progress_pct}% complete
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatMoney(goal.remaining, goal.currency)} left
                    </span>
                  </div>
                </div>

                {/* Meta info */}
                <div className="space-y-2">
                  {goal.target_date && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Calendar className="w-4 h-4" />
                      <span>
                        Target:{' '}
                        {new Date(goal.target_date).toLocaleDateString()}
                      </span>
                      {goal.days_remaining !== undefined && (
                        <Badge variant="outline" className="text-xs ml-auto">
                          {goal.days_remaining} days left
                        </Badge>
                      )}
                    </div>
                  )}
                  {goal.monthly_needed !== undefined && goal.monthly_needed > 0 && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <DollarSign className="w-4 h-4" />
                      <span>
                        Save {formatMoney(goal.monthly_needed, goal.currency)}
                        /mo to stay on track
                      </span>
                    </div>
                  )}
                </div>
              </FinancialCardContent>

              <FinancialCardFooter className="flex gap-2 pt-3 border-t">
                {goal.status === 'ACTIVE' && (
                  <>
                    <Button
                      variant="financial"
                      size="sm"
                      className="flex-1"
                      onClick={() => openContribDialog(goal.id, 'deposit')}
                    >
                      <ArrowDownToLine className="w-3.5 h-3.5" />
                      Deposit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openContribDialog(goal.id, 'withdraw')}
                    >
                      <ArrowUpFromLine className="w-3.5 h-3.5" />
                    </Button>
                  </>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => openEditDialog(goal)}
                >
                  <Edit className="w-3.5 h-3.5" />
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="sm">
                      <Trash2 className="w-3.5 h-3.5 text-destructive" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete savings goal?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will permanently delete &quot;{goal.name}&quot; and
                        all its contribution history. This action cannot be
                        undone.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={async () => {
                          try {
                            await deleteSavingsGoal(goal.id);
                            await refresh();
                            toast({ title: 'Savings goal deleted' });
                          } catch (error: unknown) {
                            toast({
                              title: 'Failed to delete',
                              description: getErrorMessage(
                                error,
                                'Please try again.',
                              ),
                            });
                          }
                        }}
                      >
                        Delete
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </FinancialCardFooter>
            </FinancialCard>
          ))}
        </div>
      )}

      {/* Contribution / Withdraw Dialog */}
      <Dialog open={contribOpen} onOpenChange={setContribOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {contribMode === 'deposit'
                ? 'Add Contribution'
                : 'Withdraw Funds'}
            </DialogTitle>
            <DialogDescription>
              {contribMode === 'deposit'
                ? 'Add money toward this savings goal.'
                : 'Withdraw money from this savings goal.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Amount</label>
              <input
                className="input w-full"
                type="number"
                min="0.01"
                step="0.01"
                value={contribAmount}
                onChange={(e) => setContribAmount(e.target.value)}
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Note (optional)
              </label>
              <input
                className="input w-full"
                value={contribNote}
                onChange={(e) => setContribNote(e.target.value)}
                placeholder={
                  contribMode === 'deposit'
                    ? 'e.g., Monthly savings'
                    : 'e.g., Emergency expense'
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setContribOpen(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button
              onClick={onContribute}
              disabled={saving || !contribAmount}
              variant={contribMode === 'deposit' ? 'default' : 'destructive'}
            >
              {saving
                ? 'Processing...'
                : contribMode === 'deposit'
                  ? 'Add Contribution'
                  : 'Withdraw'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Goal Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Savings Goal</DialogTitle>
            <DialogDescription>
              Update the details of your savings goal.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">
                Goal Name
              </label>
              <input
                className="input w-full"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Description
              </label>
              <input
                className="input w-full"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">
                  Target Amount
                </label>
                <input
                  className="input w-full"
                  type="number"
                  min="1"
                  step="0.01"
                  value={editTarget}
                  onChange={(e) => setEditTarget(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Target Date
                </label>
                <input
                  className="input w-full"
                  type="date"
                  value={editDate}
                  onChange={(e) => setEditDate(e.target.value)}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEditOpen(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button
              onClick={onEdit}
              disabled={saving || !editName.trim() || !editTarget}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
