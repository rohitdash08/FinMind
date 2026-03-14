import { useState, useEffect, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Plus,
  Target,
  TrendingUp,
  Trophy,
  Wallet,
  PiggyBank,
  Pencil,
  Trash2,
  ArrowDownCircle,
  ArrowUpCircle,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  listSavingsGoals,
  createSavingsGoal,
  updateSavingsGoal,
  deleteSavingsGoal,
  addContribution,
  withdrawFromGoal,
  type SavingsGoal,
  type SavingsGoalCreate,
} from '@/api/savings-goals';
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

const ICON_OPTIONS = [
  { value: 'piggy-bank', label: 'Piggy Bank' },
  { value: 'target', label: 'Target' },
  { value: 'trophy', label: 'Trophy' },
  { value: 'wallet', label: 'Wallet' },
  { value: 'trending-up', label: 'Growth' },
];

function GoalIcon({ icon, className }: { icon: string; className?: string }) {
  const cls = className || 'w-6 h-6';
  switch (icon) {
    case 'target':
      return <Target className={cls} />;
    case 'trophy':
      return <Trophy className={cls} />;
    case 'wallet':
      return <Wallet className={cls} />;
    case 'trending-up':
      return <TrendingUp className={cls} />;
    default:
      return <PiggyBank className={cls} />;
  }
}

function MilestoneBadges({ milestones }: { milestones: number[] }) {
  const labels: Record<number, string> = {
    25: '25%',
    50: 'Halfway!',
    75: '75%',
    100: 'Complete!',
  };
  const colors: Record<number, string> = {
    25: 'bg-blue-100 text-blue-700',
    50: 'bg-yellow-100 text-yellow-700',
    75: 'bg-purple-100 text-purple-700',
    100: 'bg-green-100 text-green-700',
  };
  if (milestones.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {milestones.map((m) => (
        <Badge key={m} variant="outline" className={`text-xs ${colors[m] || ''}`}>
          <Trophy className="w-3 h-3 mr-1" />
          {labels[m] || `${m}%`}
        </Badge>
      ))}
    </div>
  );
}

export default function SavingsGoals() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCompleted, setShowCompleted] = useState(false);

  // Create/Edit modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<SavingsGoal | null>(null);
  const [formName, setFormName] = useState('');
  const [formTarget, setFormTarget] = useState('');
  const [formDate, setFormDate] = useState('');
  const [formIcon, setFormIcon] = useState('piggy-bank');
  const [saving, setSaving] = useState(false);

  // Contribute modal state
  const [contributeGoal, setContributeGoal] = useState<SavingsGoal | null>(null);
  const [contributeAmount, setContributeAmount] = useState('');
  const [contributeNotes, setContributeNotes] = useState('');
  const [contributing, setContributing] = useState(false);
  const [isWithdraw, setIsWithdraw] = useState(false);

  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSavingsGoals({ include_completed: showCompleted });
      setGoals(data);
    } catch (error: unknown) {
      toast({ title: 'Failed to load goals', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setLoading(false);
    }
  }, [toast, showCompleted]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function openCreate() {
    setEditingGoal(null);
    setFormName('');
    setFormTarget('');
    setFormDate('');
    setFormIcon('piggy-bank');
    setModalOpen(true);
  }

  function openEdit(goal: SavingsGoal) {
    setEditingGoal(goal);
    setFormName(goal.name);
    setFormTarget(String(goal.target_amount));
    setFormDate(goal.target_date || '');
    setFormIcon(goal.icon);
    setModalOpen(true);
  }

  async function onSave() {
    if (!formName.trim() || !formTarget) return;
    setSaving(true);
    try {
      if (editingGoal) {
        await updateSavingsGoal(editingGoal.id, {
          name: formName.trim(),
          target_amount: Number(formTarget),
          target_date: formDate || null,
          icon: formIcon,
        });
        toast({ title: 'Goal updated' });
      } else {
        const payload: SavingsGoalCreate = {
          name: formName.trim(),
          target_amount: Number(formTarget),
          icon: formIcon,
        };
        if (formDate) payload.target_date = formDate;
        await createSavingsGoal(payload);
        toast({ title: 'Goal created' });
      }
      setModalOpen(false);
      await refresh();
    } catch (error: unknown) {
      toast({ title: 'Failed to save goal', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  function openContribute(goal: SavingsGoal, withdraw = false) {
    setContributeGoal(goal);
    setContributeAmount('');
    setContributeNotes('');
    setIsWithdraw(withdraw);
  }

  async function onContribute() {
    if (!contributeGoal || !contributeAmount) return;
    setContributing(true);
    try {
      if (isWithdraw) {
        const res = await withdrawFromGoal(contributeGoal.id, {
          amount: Number(contributeAmount),
          notes: contributeNotes || undefined,
        });
        setGoals((prev) => prev.map((g) => (g.id === res.goal.id ? res.goal : g)));
        toast({ title: 'Withdrawal recorded' });
      } else {
        const res = await addContribution(contributeGoal.id, {
          amount: Number(contributeAmount),
          notes: contributeNotes || undefined,
        });
        setGoals((prev) => prev.map((g) => (g.id === res.goal.id ? res.goal : g)));
        if (res.new_milestones && res.new_milestones.length > 0) {
          const labels: Record<number, string> = { 25: '25%', 50: 'Halfway there!', 75: '75%', 100: 'Goal complete!' };
          const label = res.new_milestones.map((m) => labels[m] || `${m}%`).join(', ');
          toast({ title: 'Milestone reached!', description: label });
        } else {
          toast({ title: 'Contribution added' });
        }
      }
      setContributeGoal(null);
    } catch (error: unknown) {
      toast({
        title: isWithdraw ? 'Withdrawal failed' : 'Contribution failed',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setContributing(false);
    }
  }

  // Summary stats
  const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0);
  const totalSaved = goals.reduce((sum, g) => sum + g.current_amount, 0);
  const completedCount = goals.filter((g) => g.progress_pct >= 100).length;
  const overallPct = totalTarget > 0 ? Math.round((totalSaved / totalTarget) * 100) : 0;

  return (
    <div className="page-wrap">
      {/* Header */}
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">Track your savings and celebrate milestones</p>
          </div>
          <div className="flex gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCompleted((v) => !v)}
            >
              {showCompleted ? 'Hide Completed' : 'Show Completed'}
            </Button>
            <Button variant="financial" size="sm" onClick={openCreate}>
              <Plus className="w-4 h-4" />
              New Goal
            </Button>
          </div>
        </div>
      </div>

      {/* Overview Cards */}
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
              {formatMoney(totalSaved)}
            </div>
            <div className="text-sm text-muted-foreground">
              across {goals.length} goal{goals.length !== 1 ? 's' : ''}
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
              {formatMoney(totalTarget)}
            </div>
            <div className="text-sm text-muted-foreground">
              {formatMoney(totalTarget - totalSaved)} remaining
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Overall Progress
              </FinancialCardTitle>
              <TrendingUp className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{overallPct}%</div>
            <Progress value={overallPct} className="h-2 mt-1" />
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={completedCount > 0 ? 'success' : 'financial'}>
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium">
                Goals Completed
              </FinancialCardTitle>
              <Trophy className="w-5 h-5" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value mb-1">{completedCount}</div>
            <div className="text-sm opacity-80">
              {completedCount > 0 ? 'Great work!' : 'Keep saving!'}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals List */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          <div className="col-span-full text-center py-12 text-muted-foreground">Loading...</div>
        ) : goals.length === 0 ? (
          <div className="col-span-full">
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardContent className="text-center py-12">
                <PiggyBank className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                <h3 className="text-lg font-semibold mb-2">No savings goals yet</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Start by creating your first savings goal to track your progress.
                </p>
                <Button variant="financial" onClick={openCreate}>
                  <Plus className="w-4 h-4" />
                  Create Your First Goal
                </Button>
              </FinancialCardContent>
            </FinancialCard>
          </div>
        ) : (
          goals.map((goal) => (
            <FinancialCard
              key={goal.id}
              variant={goal.progress_pct >= 100 ? 'success' : 'financial'}
              className="fade-in-up"
            >
              <FinancialCardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                        goal.progress_pct >= 100
                          ? 'bg-success-light text-success'
                          : 'bg-primary/10 text-primary'
                      }`}
                    >
                      <GoalIcon icon={goal.icon} className="w-5 h-5" />
                    </div>
                    <div>
                      <FinancialCardTitle className="text-base">{goal.name}</FinancialCardTitle>
                      <FinancialCardDescription className="text-xs">
                        {goal.target_date
                          ? `Target: ${new Date(goal.target_date).toLocaleDateString()}`
                          : 'No deadline'}
                      </FinancialCardDescription>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => openEdit(goal)}>
                      <Pencil className="w-3.5 h-3.5" />
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete goal?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This will permanently delete &quot;{goal.name}&quot; and all its contribution history.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={async () => {
                              try {
                                await deleteSavingsGoal(goal.id);
                                setGoals((prev) => prev.filter((g) => g.id !== goal.id));
                                toast({ title: 'Goal deleted' });
                              } catch (error: unknown) {
                                toast({
                                  title: 'Delete failed',
                                  description: getErrorMessage(error, 'Please try again.'),
                                });
                              }
                            }}
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-3">
                  {/* Amount display */}
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xl font-bold">
                      {formatMoney(goal.current_amount, goal.currency)}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      of {formatMoney(goal.target_amount, goal.currency)}
                    </span>
                  </div>

                  {/* Progress bar */}
                  <div>
                    <div className="flex justify-between text-xs text-muted-foreground mb-1">
                      <span>{goal.progress_pct}% complete</span>
                      <span>
                        {formatMoney(Math.max(0, goal.target_amount - goal.current_amount), goal.currency)} to go
                      </span>
                    </div>
                    <Progress value={Math.min(goal.progress_pct, 100)} className="h-3" />
                  </div>

                  {/* Milestones */}
                  <MilestoneBadges milestones={goal.milestones_achieved} />

                  {/* Actions */}
                  <div className="flex gap-2 pt-2">
                    <Button
                      variant="financial"
                      size="sm"
                      className="flex-1"
                      onClick={() => openContribute(goal, false)}
                    >
                      <ArrowDownCircle className="w-4 h-4" />
                      Contribute
                    </Button>
                    {goal.current_amount > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1"
                        onClick={() => openContribute(goal, true)}
                      >
                        <ArrowUpCircle className="w-4 h-4" />
                        Withdraw
                      </Button>
                    )}
                  </div>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ))
        )}
      </div>

      {/* Create/Edit Goal Dialog */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingGoal ? 'Edit Goal' : 'New Savings Goal'}</DialogTitle>
            <DialogDescription>
              {editingGoal
                ? 'Update your savings goal details.'
                : 'Set a savings target and start tracking your progress.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm mb-1">Goal Name</label>
              <input
                className="input w-full"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g. Emergency Fund, Vacation, New Car"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm mb-1">Target Amount</label>
                <input
                  className="input w-full"
                  type="number"
                  min="0"
                  step="0.01"
                  value={formTarget}
                  onChange={(e) => setFormTarget(e.target.value)}
                  placeholder="5000"
                />
              </div>
              <div>
                <label className="block text-sm mb-1">Target Date (optional)</label>
                <input
                  className="input w-full"
                  type="date"
                  value={formDate}
                  onChange={(e) => setFormDate(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="block text-sm mb-1">Icon</label>
              <div className="flex gap-2">
                {ICON_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className={`flex items-center gap-1 px-3 py-2 rounded-lg border text-sm transition ${
                      formIcon === opt.value
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border hover:border-primary/50'
                    }`}
                    onClick={() => setFormIcon(opt.value)}
                  >
                    <GoalIcon icon={opt.value} className="w-4 h-4" />
                    <span className="hidden sm:inline">{opt.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={saving || !formName.trim() || !formTarget}>
              {editingGoal ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Contribute/Withdraw Dialog */}
      <Dialog open={!!contributeGoal} onOpenChange={(open) => !open && setContributeGoal(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {isWithdraw ? 'Withdraw from' : 'Contribute to'} {contributeGoal?.name}
            </DialogTitle>
            <DialogDescription>
              {isWithdraw
                ? `Current balance: ${formatMoney(contributeGoal?.current_amount || 0, contributeGoal?.currency)}`
                : `${formatMoney(Math.max(0, (contributeGoal?.target_amount || 0) - (contributeGoal?.current_amount || 0)), contributeGoal?.currency)} remaining to reach your goal.`}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm mb-1">Amount</label>
              <input
                className="input w-full"
                type="number"
                min="0"
                step="0.01"
                value={contributeAmount}
                onChange={(e) => setContributeAmount(e.target.value)}
                placeholder="100"
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Notes (optional)</label>
              <input
                className="input w-full"
                value={contributeNotes}
                onChange={(e) => setContributeNotes(e.target.value)}
                placeholder="e.g. Monthly deposit"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setContributeGoal(null)} disabled={contributing}>
              Cancel
            </Button>
            <Button onClick={onContribute} disabled={contributing || !contributeAmount}>
              {isWithdraw ? 'Withdraw' : 'Contribute'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
