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
  Target,
  Plus,
  TrendingUp,
  Calendar,
  DollarSign,
  Trophy,
  Pencil,
  Trash2,
  Sparkles,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  listSavingsGoals,
  createSavingsGoal,
  updateSavingsGoal,
  deleteSavingsGoal,
  contributeToGoal,
  type SavingsGoal,
  type SavingsGoalCreate,
  type SavingsGoalCategory,
  type Milestone,
  CATEGORY_LABELS,
  CATEGORY_COLORS,
} from '@/api/savingsGoals';
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

const CATEGORIES: SavingsGoalCategory[] = [
  'EMERGENCY',
  'VACATION',
  'EDUCATION',
  'HOME',
  'CAR',
  'RETIREMENT',
  'INVESTMENT',
  'OTHER',
];

function MilestoneDots({ milestones }: { milestones: Milestone[] }) {
  const sorted = [...milestones].sort((a, b) => a.percentage - b.percentage);
  return (
    <div className="flex items-center gap-2 mt-2">
      {sorted.map((m) => (
        <div
          key={m.id}
          className="flex items-center gap-1"
          title={`${m.percentage}% — ${m.reached ? 'Reached!' : 'Not yet'}`}
        >
          <div
            className={`w-3 h-3 rounded-full border-2 transition-all duration-300 ${
              m.reached
                ? 'bg-primary border-primary scale-110'
                : 'bg-transparent border-muted-foreground/40'
            }`}
          />
          <span className="text-[10px] text-muted-foreground">{m.percentage}%</span>
        </div>
      ))}
    </div>
  );
}

function CelebrationOverlay({
  milestones,
  onDone,
}: {
  milestones: Milestone[];
  onDone: () => void;
}) {
  useEffect(() => {
    const timer = setTimeout(onDone, 3000);
    return () => clearTimeout(timer);
  }, [onDone]);

  const highest = Math.max(...milestones.map((m) => m.percentage));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-in fade-in duration-300"
      onClick={onDone}
    >
      <div className="bg-white rounded-2xl p-8 shadow-2xl text-center max-w-sm mx-4 animate-in zoom-in-95 duration-500">
        <div className="text-6xl mb-4">
          {highest === 100 ? '🎉' : highest >= 75 ? '🏆' : highest >= 50 ? '⭐' : '🎯'}
        </div>
        <h2 className="text-2xl font-bold mb-2">
          {highest === 100 ? 'Goal Complete!' : `${highest}% Milestone!`}
        </h2>
        <p className="text-muted-foreground">
          {highest === 100
            ? "Congratulations! You've reached your savings goal! 🥳"
            : `Amazing progress! You've hit the ${highest}% milestone!`}
        </p>
        <div className="mt-4 flex justify-center gap-1">
          {Array.from({ length: 12 }).map((_, i) => (
            <Sparkles
              key={i}
              className="w-4 h-4 text-yellow-400 animate-bounce"
              style={{ animationDelay: `${i * 100}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function SavingsGoals() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create/Edit dialog
  const [formOpen, setFormOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<SavingsGoal | null>(null);
  const [formName, setFormName] = useState('');
  const [formTarget, setFormTarget] = useState('');
  const [formDeadline, setFormDeadline] = useState('');
  const [formCategory, setFormCategory] = useState<SavingsGoalCategory>('OTHER');
  const [formSaving, setFormSaving] = useState(false);

  // Contribute dialog
  const [contributeGoal, setContributeGoal] = useState<SavingsGoal | null>(null);
  const [contributeAmount, setContributeAmount] = useState('');
  const [contributeNote, setContributeNote] = useState('');
  const [contributing, setContributing] = useState(false);

  // Celebration
  const [celebration, setCelebration] = useState<Milestone[] | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSavingsGoals();
      setGoals(data);
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Failed to load savings goals');
      setError(message);
      toast({ title: 'Failed to load savings goals', description: message });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function openCreateForm() {
    setEditingGoal(null);
    setFormName('');
    setFormTarget('');
    setFormDeadline('');
    setFormCategory('OTHER');
    setFormOpen(true);
  }

  function openEditForm(goal: SavingsGoal) {
    setEditingGoal(goal);
    setFormName(goal.name);
    setFormTarget(String(goal.target_amount));
    setFormDeadline(goal.deadline || '');
    setFormCategory(goal.category);
    setFormOpen(true);
  }

  async function onSubmitForm() {
    if (!formName.trim() || !formTarget) return;
    setFormSaving(true);
    try {
      if (editingGoal) {
        await updateSavingsGoal(editingGoal.id, {
          name: formName.trim(),
          target_amount: Number(formTarget),
          deadline: formDeadline || undefined,
          category: formCategory,
        });
        toast({ title: 'Goal updated' });
      } else {
        const payload: SavingsGoalCreate = {
          name: formName.trim(),
          target_amount: Number(formTarget),
          category: formCategory,
        };
        if (formDeadline) payload.deadline = formDeadline;
        await createSavingsGoal(payload);
        toast({ title: 'Goal created' });
      }
      await refresh();
      setFormOpen(false);
    } catch (err: unknown) {
      toast({
        title: editingGoal ? 'Failed to update goal' : 'Failed to create goal',
        description: getErrorMessage(err, 'Please try again.'),
      });
    } finally {
      setFormSaving(false);
    }
  }

  async function onContribute() {
    if (!contributeGoal || !contributeAmount) return;
    setContributing(true);
    try {
      const result = await contributeToGoal(
        contributeGoal.id,
        Number(contributeAmount),
        contributeNote || undefined,
      );
      toast({ title: 'Contribution added!' });

      if (result.newly_reached_milestones.length > 0) {
        setCelebration(result.newly_reached_milestones);
      }

      await refresh();
      setContributeGoal(null);
      setContributeAmount('');
      setContributeNote('');
    } catch (err: unknown) {
      toast({
        title: 'Failed to contribute',
        description: getErrorMessage(err, 'Please try again.'),
      });
    } finally {
      setContributing(false);
    }
  }

  async function onDelete(id: number) {
    try {
      await deleteSavingsGoal(id);
      setGoals((prev) => prev.filter((g) => g.id !== id));
      toast({ title: 'Goal deleted' });
    } catch (err: unknown) {
      toast({
        title: 'Failed to delete goal',
        description: getErrorMessage(err, 'Please try again.'),
      });
    }
  }

  // Summary stats
  const totalSaved = goals.reduce((sum, g) => sum + g.current_amount, 0);
  const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0);
  const completedGoals = goals.filter((g) => g.progress_pct >= 100).length;
  const activeGoals = goals.filter((g) => g.progress_pct < 100).length;

  return (
    <div className="page-wrap">
      {/* Celebration overlay */}
      {celebration && (
        <CelebrationOverlay milestones={celebration} onDone={() => setCelebration(null)} />
      )}

      {/* Header */}
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">Track your savings targets and celebrate milestones</p>
          </div>
          <Button variant="financial" size="sm" onClick={openCreateForm}>
            <Plus className="w-4 h-4" />
            New Goal
          </Button>
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
              <DollarSign className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {formatMoney(totalSaved)}
            </div>
            <div className="text-sm text-muted-foreground">
              of {formatMoney(totalTarget)} target
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Active Goals
              </FinancialCardTitle>
              <Target className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{activeGoals}</div>
            <div className="text-sm text-muted-foreground">in progress</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={completedGoals > 0 ? 'success' : 'financial'}>
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium">
                Completed
              </FinancialCardTitle>
              <Trophy className="w-5 h-5" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value mb-1">{completedGoals}</div>
            <div className="text-sm opacity-80">
              {completedGoals > 0 ? 'goals achieved! 🎉' : 'Keep going!'}
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
            <div className="metric-value text-foreground mb-1">
              {totalTarget > 0 ? Math.round((totalSaved / totalTarget) * 100) : 0}%
            </div>
            <Progress
              value={totalTarget > 0 ? (totalSaved / totalTarget) * 100 : 0}
              className="h-2 mt-2"
            />
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals List */}
      <FinancialCard variant="financial" className="fade-in-up">
        <FinancialCardHeader>
          <FinancialCardTitle className="section-title">Your Goals</FinancialCardTitle>
          <FinancialCardDescription>
            {goals.length === 0
              ? 'Create your first savings goal to get started'
              : `${goals.length} goal${goals.length !== 1 ? 's' : ''}`}
          </FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          {loading ? (
            <div className="text-center py-8 text-muted-foreground">Loading…</div>
          ) : error ? (
            <div className="text-center py-8 text-destructive">{error}</div>
          ) : goals.length === 0 ? (
            <div className="text-center py-12">
              <Target className="w-12 h-12 text-muted-foreground/40 mx-auto mb-4" />
              <h3 className="text-lg font-medium mb-2">No savings goals yet</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Start by creating a savings goal to track your progress
              </p>
              <Button variant="financial" size="sm" onClick={openCreateForm}>
                <Plus className="w-4 h-4" />
                Create Your First Goal
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {goals.map((goal) => (
                <div
                  key={goal.id}
                  className="interactive-row p-4 rounded-lg border border-border"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center text-white ${
                          CATEGORY_COLORS[goal.category]
                        }`}
                      >
                        {goal.progress_pct >= 100 ? (
                          <Trophy className="w-5 h-5" />
                        ) : (
                          <Target className="w-5 h-5" />
                        )}
                      </div>
                      <div>
                        <div className="font-medium text-foreground">{goal.name}</div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <Badge variant="outline" className="text-xs">
                            {CATEGORY_LABELS[goal.category]}
                          </Badge>
                          {goal.deadline && (
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              {new Date(goal.deadline).toLocaleDateString()}
                            </span>
                          )}
                          {goal.on_track === false && goal.days_remaining !== null && (
                            <Badge variant="destructive" className="text-xs">
                              Overdue
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setContributeGoal(goal)}
                        title="Contribute"
                      >
                        <DollarSign className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEditForm(goal)}
                        title="Edit"
                      >
                        <Pencil className="w-4 h-4" />
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="sm" title="Delete">
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Delete goal?</AlertDialogTitle>
                            <AlertDialogDescription>
                              This will permanently delete &ldquo;{goal.name}&rdquo; and all
                              contribution history.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => void onDelete(goal.id)}>
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>

                  {/* Progress bar */}
                  <div className="mb-2">
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="font-medium">
                        {formatMoney(goal.current_amount, goal.currency)}
                      </span>
                      <span className="text-muted-foreground">
                        {formatMoney(goal.target_amount, goal.currency)}
                      </span>
                    </div>
                    <Progress value={goal.progress_pct} className="h-3" />
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-xs font-semibold text-primary">
                        {goal.progress_pct}%
                      </span>
                      {goal.monthly_target && goal.progress_pct < 100 && (
                        <span className="text-xs text-muted-foreground">
                          {formatMoney(goal.monthly_target, goal.currency)}/mo to reach goal
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Milestone indicators */}
                  <MilestoneDots milestones={goal.milestones} />
                </div>
              ))}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>

      {/* Create/Edit Goal Dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingGoal ? 'Edit Goal' : 'New Savings Goal'}</DialogTitle>
            <DialogDescription>
              {editingGoal
                ? 'Update your savings goal details.'
                : 'Set a target and track your progress toward it.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm mb-1">Name</label>
              <input
                className="input w-full"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="Emergency Fund"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm mb-1">Target Amount</label>
                <input
                  className="input w-full"
                  type="number"
                  min="1"
                  step="0.01"
                  value={formTarget}
                  onChange={(e) => setFormTarget(e.target.value)}
                  placeholder="10000"
                />
              </div>
              <div>
                <label className="block text-sm mb-1">Deadline (optional)</label>
                <input
                  className="input w-full"
                  type="date"
                  value={formDeadline}
                  onChange={(e) => setFormDeadline(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="block text-sm mb-1">Category</label>
              <select
                className="input w-full"
                value={formCategory}
                onChange={(e) => setFormCategory(e.target.value as SavingsGoalCategory)}
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {CATEGORY_LABELS[cat]}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)} disabled={formSaving}>
              Cancel
            </Button>
            <Button
              onClick={() => void onSubmitForm()}
              disabled={formSaving || !formName.trim() || !formTarget}
            >
              {editingGoal ? 'Save Changes' : 'Create Goal'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Contribute Dialog */}
      <Dialog open={!!contributeGoal} onOpenChange={(open) => !open && setContributeGoal(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Contribute to {contributeGoal?.name}</DialogTitle>
            <DialogDescription>
              Current: {formatMoney(contributeGoal?.current_amount ?? 0, contributeGoal?.currency)}{' '}
              / {formatMoney(contributeGoal?.target_amount ?? 0, contributeGoal?.currency)}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm mb-1">Amount</label>
              <input
                className="input w-full"
                type="number"
                min="0.01"
                step="0.01"
                value={contributeAmount}
                onChange={(e) => setContributeAmount(e.target.value)}
                placeholder="100.00"
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Note (optional)</label>
              <input
                className="input w-full"
                value={contributeNote}
                onChange={(e) => setContributeNote(e.target.value)}
                placeholder="Monthly contribution"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setContributeGoal(null)}
              disabled={contributing}
            >
              Cancel
            </Button>
            <Button
              onClick={() => void onContribute()}
              disabled={contributing || !contributeAmount || Number(contributeAmount) <= 0}
            >
              Contribute
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
