import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
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
  Plus,
  Target,
  Trophy,
  Calendar,
  Trash2,
  ChevronDown,
  ChevronUp,
  PiggyBank,
  TrendingUp,
  Star,
  Sparkles,
  Heart,
  Shield,
  Gem,
  Car,
  Home,
  Plane,
  GraduationCap,
  Gift,
  Wallet,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatMoney } from '@/lib/currency';
import {
  listGoals,
  createGoal,
  deleteGoal,
  addContribution,
  listContributions,
  getGoalsSummary,
  type SavingsGoal,
  type SavingsContribution,
  type GoalsSummary,
} from '@/api/savings';

// ── Icon map ───────────────────────────────────────────────────────────

const ICON_OPTIONS = [
  { value: 'piggy-bank', label: 'Piggy Bank', Icon: PiggyBank },
  { value: 'target', label: 'Target', Icon: Target },
  { value: 'star', label: 'Star', Icon: Star },
  { value: 'heart', label: 'Heart', Icon: Heart },
  { value: 'shield', label: 'Shield', Icon: Shield },
  { value: 'gem', label: 'Gem', Icon: Gem },
  { value: 'car', label: 'Car', Icon: Car },
  { value: 'home', label: 'Home', Icon: Home },
  { value: 'plane', label: 'Travel', Icon: Plane },
  { value: 'graduation', label: 'Education', Icon: GraduationCap },
  { value: 'gift', label: 'Gift', Icon: Gift },
  { value: 'wallet', label: 'Wallet', Icon: Wallet },
] as const;

const COLOR_OPTIONS = [
  '#4F46E5', '#7C3AED', '#EC4899', '#EF4444',
  '#F97316', '#EAB308', '#22C55E', '#14B8A6',
  '#06B6D4', '#3B82F6', '#6366F1', '#8B5CF6',
];

function getIconComponent(icon: string) {
  const found = ICON_OPTIONS.find((o) => o.value === icon);
  return found ? found.Icon : PiggyBank;
}

// ── Confetti ───────────────────────────────────────────────────────────

function Confetti({ active }: { active: boolean }) {
  if (!active) return null;
  const pieces = useMemo(
    () =>
      Array.from({ length: 50 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        delay: Math.random() * 0.5,
        duration: 1 + Math.random() * 1.5,
        color: ['#4F46E5', '#22C55E', '#EAB308', '#EC4899', '#F97316', '#06B6D4'][
          Math.floor(Math.random() * 6)
        ],
        size: 4 + Math.random() * 6,
      })),
    [],
  );
  return (
    <div className="fixed inset-0 pointer-events-none z-50 overflow-hidden">
      {pieces.map((p) => (
        <div
          key={p.id}
          className="absolute animate-confetti-fall"
          style={{
            left: `${p.x}%`,
            top: '-10px',
            width: p.size,
            height: p.size,
            backgroundColor: p.color,
            borderRadius: Math.random() > 0.5 ? '50%' : '2px',
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
          }}
        />
      ))}
      <style>{`
        @keyframes confetti-fall {
          0% { transform: translateY(0) rotate(0deg); opacity: 1; }
          100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
        }
        .animate-confetti-fall {
          animation: confetti-fall linear forwards;
        }
      `}</style>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const diff = new Date(dateStr).getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

// ── Main Page ──────────────────────────────────────────────────────────

export default function Savings() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [summary, setSummary] = useState<GoalsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [confetti, setConfetti] = useState(false);

  // Add goal dialog
  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newTarget, setNewTarget] = useState('');
  const [newDeadline, setNewDeadline] = useState('');
  const [newColor, setNewColor] = useState(COLOR_OPTIONS[0]);
  const [newIcon, setNewIcon] = useState('piggy-bank');
  const [saving, setSaving] = useState(false);

  // Contribute dialog
  const [contributeGoalId, setContributeGoalId] = useState<number | null>(null);
  const [contributeAmount, setContributeAmount] = useState('');
  const [contributeNotes, setContributeNotes] = useState('');
  const [contributing, setContributing] = useState(false);

  // Expanded contributions
  const [expandedGoals, setExpandedGoals] = useState<Set<number>>(new Set());
  const [contributions, setContributions] = useState<Record<number, SavingsContribution[]>>({});

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [goalsData, summaryData] = await Promise.all([listGoals(), getGoalsSummary()]);
      setGoals(goalsData);
      setSummary(summaryData);
    } catch (err) {
      toast({ title: 'Failed to load savings', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // ── Add Goal ───────────────────────────────────────────────────────

  async function handleCreateGoal() {
    if (!newName.trim() || !newTarget) return;
    setSaving(true);
    try {
      await createGoal({
        name: newName.trim(),
        target_amount: Number(newTarget),
        deadline: newDeadline || undefined,
        color: newColor,
        icon: newIcon,
      });
      await refresh();
      setAddOpen(false);
      setNewName('');
      setNewTarget('');
      setNewDeadline('');
      setNewColor(COLOR_OPTIONS[0]);
      setNewIcon('piggy-bank');
      toast({ title: '🎯 Goal created!', description: `"${newName.trim()}" has been added to your savings goals.` });
    } catch (err) {
      toast({ title: 'Failed to create goal', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  // ── Delete Goal ────────────────────────────────────────────────────

  async function handleDeleteGoal(id: number) {
    try {
      await deleteGoal(id);
      setGoals((prev) => prev.filter((g) => g.id !== id));
      toast({ title: 'Goal deleted' });
      void refresh(); // refresh summary
    } catch (err) {
      toast({ title: 'Failed to delete', description: getErrorMessage(err, 'Please try again.') });
    }
  }

  // ── Contribute ─────────────────────────────────────────────────────

  async function handleContribute() {
    if (!contributeGoalId || !contributeAmount) return;
    setContributing(true);
    try {
      const res = await addContribution(contributeGoalId, {
        amount: Number(contributeAmount),
        notes: contributeNotes.trim() || undefined,
      });
      await refresh();
      setContributeGoalId(null);
      setContributeAmount('');
      setContributeNotes('');

      if (res.just_completed) {
        setConfetti(true);
        toast({
          title: '🎉 Goal Completed!',
          description: `Congratulations! You've reached your "${res.goal.name}" savings goal!`,
        });
        setTimeout(() => setConfetti(false), 3000);
      } else {
        toast({
          title: '💰 Contribution added',
          description: `${formatMoney(Number(contributeAmount), res.goal.currency)} saved toward "${res.goal.name}"`,
        });
      }

      // Refresh contributions if expanded
      if (expandedGoals.has(contributeGoalId)) {
        const contribs = await listContributions(contributeGoalId);
        setContributions((prev) => ({ ...prev, [contributeGoalId]: contribs }));
      }
    } catch (err) {
      toast({ title: 'Failed to add contribution', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setContributing(false);
    }
  }

  // ── Toggle Contributions ───────────────────────────────────────────

  async function toggleContributions(goalId: number) {
    const next = new Set(expandedGoals);
    if (next.has(goalId)) {
      next.delete(goalId);
    } else {
      next.add(goalId);
      if (!contributions[goalId]) {
        try {
          const contribs = await listContributions(goalId);
          setContributions((prev) => ({ ...prev, [goalId]: contribs }));
        } catch {
          toast({ title: 'Failed to load contributions' });
        }
      }
    }
    setExpandedGoals(next);
  }

  // ── Render ─────────────────────────────────────────────────────────

  const activeGoals = goals.filter((g) => !g.completed);
  const completedGoals = goals.filter((g) => g.completed);

  return (
    <div className="page-wrap">
      <Confetti active={confetti} />

      {/* Header */}
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">Track your savings and celebrate every milestone</p>
          </div>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button variant="financial" size="sm">
                <Plus className="w-4 h-4" />
                New Goal
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Create Savings Goal</DialogTitle>
                <DialogDescription>
                  Set a target and start saving toward something meaningful.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1.5">Goal Name</label>
                  <input
                    className="input w-full"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g., Emergency Fund, Vacation, New Laptop"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1.5">Target Amount</label>
                    <input
                      className="input w-full"
                      type="number"
                      min="1"
                      step="0.01"
                      value={newTarget}
                      onChange={(e) => setNewTarget(e.target.value)}
                      placeholder="5000"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1.5">Deadline (optional)</label>
                    <input
                      className="input w-full"
                      type="date"
                      value={newDeadline}
                      onChange={(e) => setNewDeadline(e.target.value)}
                    />
                  </div>
                </div>

                {/* Icon picker */}
                <div>
                  <label className="block text-sm font-medium mb-1.5">Icon</label>
                  <div className="flex flex-wrap gap-2">
                    {ICON_OPTIONS.map(({ value, label, Icon }) => (
                      <button
                        key={value}
                        type="button"
                        title={label}
                        onClick={() => setNewIcon(value)}
                        className={`p-2 rounded-lg border-2 transition-all ${
                          newIcon === value
                            ? 'border-primary bg-primary/10 scale-110'
                            : 'border-border hover:border-primary/40'
                        }`}
                      >
                        <Icon className="w-5 h-5" />
                      </button>
                    ))}
                  </div>
                </div>

                {/* Color picker */}
                <div>
                  <label className="block text-sm font-medium mb-1.5">Color</label>
                  <div className="flex flex-wrap gap-2">
                    {COLOR_OPTIONS.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => setNewColor(c)}
                        className={`w-8 h-8 rounded-full border-2 transition-all ${
                          newColor === c ? 'border-foreground scale-110 ring-2 ring-offset-2' : 'border-transparent'
                        }`}
                        style={{ backgroundColor: c }}
                      />
                    ))}
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setAddOpen(false)} disabled={saving}>
                  Cancel
                </Button>
                <Button onClick={handleCreateGoal} disabled={saving || !newName.trim() || !newTarget}>
                  {saving ? 'Creating...' : 'Create Goal'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Summary Stats */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-4 mb-8">
          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Total Saved
                </FinancialCardTitle>
                <TrendingUp className="w-5 h-5 text-primary" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {formatMoney(summary.total_saved)}
              </div>
              <div className="text-sm text-muted-foreground">
                of {formatMoney(summary.total_target)} target
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Active Goals
                </FinancialCardTitle>
                <Target className="w-5 h-5 text-primary" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">{summary.active_count}</div>
              <div className="text-sm text-muted-foreground">in progress</div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="success" className="fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium">Completed</FinancialCardTitle>
                <Trophy className="w-5 h-5" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value mb-1">{summary.completed_count}</div>
              <div className="text-sm opacity-80">
                {summary.completed_count > 0 ? 'goals achieved! 🎉' : 'Start your first goal'}
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Next Deadline
                </FinancialCardTitle>
                <Calendar className="w-5 h-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              {summary.nearest_deadline ? (
                <>
                  <div className="metric-value text-foreground mb-1">
                    {daysUntil(summary.nearest_deadline.deadline)} days
                  </div>
                  <div className="text-sm text-muted-foreground truncate">
                    {summary.nearest_deadline.name}
                  </div>
                </>
              ) : (
                <>
                  <div className="metric-value text-foreground mb-1">—</div>
                  <div className="text-sm text-muted-foreground">No deadlines set</div>
                </>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="text-muted-foreground">Loading your savings goals...</div>
        </div>
      )}

      {/* Empty State */}
      {!loading && goals.length === 0 && (
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardContent className="py-16 text-center">
            <div className="mx-auto w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mb-6">
              <PiggyBank className="w-10 h-10 text-primary" />
            </div>
            <h3 className="text-xl font-semibold mb-2">No savings goals yet</h3>
            <p className="text-muted-foreground max-w-md mx-auto mb-6">
              Create your first savings goal to start tracking your progress toward financial
              milestones. Whether it's an emergency fund, vacation, or a big purchase — we'll help
              you get there.
            </p>
            <Button variant="financial" onClick={() => setAddOpen(true)}>
              <Plus className="w-4 h-4" />
              Create Your First Goal
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Active Goals */}
      {activeGoals.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            Active Goals
          </h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {activeGoals.map((goal) => (
              <GoalCard
                key={goal.id}
                goal={goal}
                contributions={contributions[goal.id]}
                expanded={expandedGoals.has(goal.id)}
                onContribute={() => {
                  setContributeGoalId(goal.id);
                  setContributeAmount('');
                  setContributeNotes('');
                }}
                onToggleHistory={() => toggleContributions(goal.id)}
                onDelete={() => handleDeleteGoal(goal.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Completed Goals */}
      {completedGoals.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Trophy className="w-5 h-5 text-yellow-500" />
            Completed
          </h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {completedGoals.map((goal) => (
              <GoalCard
                key={goal.id}
                goal={goal}
                contributions={contributions[goal.id]}
                expanded={expandedGoals.has(goal.id)}
                onContribute={() => {
                  setContributeGoalId(goal.id);
                  setContributeAmount('');
                  setContributeNotes('');
                }}
                onToggleHistory={() => toggleContributions(goal.id)}
                onDelete={() => handleDeleteGoal(goal.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Contribute Dialog */}
      <Dialog
        open={contributeGoalId !== null}
        onOpenChange={(open) => {
          if (!open) setContributeGoalId(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Contribution</DialogTitle>
            <DialogDescription>
              Record a savings contribution toward{' '}
              <span className="font-semibold">
                {goals.find((g) => g.id === contributeGoalId)?.name ?? 'your goal'}
              </span>
              .
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">Amount</label>
              <input
                className="input w-full"
                type="number"
                min="0.01"
                step="0.01"
                value={contributeAmount}
                onChange={(e) => setContributeAmount(e.target.value)}
                placeholder="250.00"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Notes (optional)</label>
              <input
                className="input w-full"
                value={contributeNotes}
                onChange={(e) => setContributeNotes(e.target.value)}
                placeholder="e.g., Birthday gift, Freelance payment"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setContributeGoalId(null)} disabled={contributing}>
              Cancel
            </Button>
            <Button onClick={handleContribute} disabled={contributing || !contributeAmount}>
              {contributing ? 'Saving...' : '💰 Add Contribution'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Goal Card Component ──────────────────────────────────────────────

interface GoalCardProps {
  goal: SavingsGoal;
  contributions?: SavingsContribution[];
  expanded: boolean;
  onContribute: () => void;
  onToggleHistory: () => void;
  onDelete: () => void;
}

function GoalCard({ goal, contributions, expanded, onContribute, onToggleHistory, onDelete }: GoalCardProps) {
  const IconComp = getIconComponent(goal.icon);
  const days = daysUntil(goal.deadline);
  const isOverdue = days !== null && days < 0 && !goal.completed;
  const isUrgent = days !== null && days >= 0 && days <= 7 && !goal.completed;

  return (
    <FinancialCard
      variant={goal.completed ? 'success' : 'financial'}
      className="fade-in-up flex flex-col"
    >
      <FinancialCardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-11 h-11 rounded-xl flex items-center justify-center text-white shadow-sm"
              style={{ backgroundColor: goal.color }}
            >
              <IconComp className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <FinancialCardTitle className="text-base truncate">{goal.name}</FinancialCardTitle>
              {goal.deadline && (
                <div className="flex items-center gap-1 mt-0.5">
                  <Calendar className="w-3 h-3 text-muted-foreground" />
                  <span
                    className={`text-xs ${
                      isOverdue
                        ? 'text-destructive font-medium'
                        : isUrgent
                          ? 'text-warning font-medium'
                          : 'text-muted-foreground'
                    }`}
                  >
                    {isOverdue
                      ? `${Math.abs(days!)} days overdue`
                      : days === 0
                        ? 'Due today'
                        : `${days} days left`}
                  </span>
                </div>
              )}
            </div>
          </div>
          {goal.completed && (
            <Badge variant="secondary" className="bg-green-100 text-green-700 border-green-200 shrink-0">
              <Trophy className="w-3 h-3 mr-1" />
              Done
            </Badge>
          )}
        </div>
      </FinancialCardHeader>

      <FinancialCardContent className="flex-1 flex flex-col">
        {/* Progress */}
        <div className="mb-4">
          <div className="flex justify-between text-sm mb-2">
            <span className="font-semibold">{formatMoney(goal.current_amount, goal.currency)}</span>
            <span className="text-muted-foreground">
              of {formatMoney(goal.target_amount, goal.currency)}
            </span>
          </div>
          <div className="relative">
            <Progress value={goal.progress} className="h-3" />
            <div
              className="absolute inset-0 h-3 rounded-full overflow-hidden"
              style={{ width: `${Math.min(goal.progress, 100)}%` }}
            >
              <div
                className="w-full h-full rounded-full transition-all duration-500"
                style={{
                  background: `linear-gradient(90deg, ${goal.color}CC, ${goal.color})`,
                }}
              />
            </div>
          </div>
          <div className="text-right mt-1">
            <span className="text-xs font-semibold" style={{ color: goal.color }}>
              {goal.progress}%
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-auto">
          {!goal.completed && (
            <Button variant="financial" size="sm" className="flex-1" onClick={onContribute}>
              <Plus className="w-3.5 h-3.5" />
              Contribute
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleHistory}
            className="text-muted-foreground"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            History
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive">
                <Trash2 className="w-4 h-4" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete "{goal.name}"?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently remove this goal and all its contribution history. This
                  action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={onDelete}>Delete</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        {/* Contribution History */}
        {expanded && (
          <div className="mt-4 pt-4 border-t border-border/50">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              Contributions
            </h4>
            {!contributions ? (
              <div className="text-xs text-muted-foreground">Loading...</div>
            ) : contributions.length === 0 ? (
              <div className="text-xs text-muted-foreground">No contributions yet</div>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {contributions.map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center justify-between text-sm py-1.5 px-2 rounded-lg hover:bg-muted/50"
                  >
                    <div>
                      <span className="font-medium text-foreground">
                        +{formatMoney(c.amount, goal.currency)}
                      </span>
                      {c.notes && (
                        <span className="text-xs text-muted-foreground ml-2">{c.notes}</span>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0 ml-2">
                      {c.contributed_at
                        ? new Date(c.contributed_at).toLocaleDateString()
                        : '—'}
                    </span>
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
