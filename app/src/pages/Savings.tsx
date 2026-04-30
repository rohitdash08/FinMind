import { useEffect, useState, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Target,
  Plus,
  Trash2,
  PiggyBank,
  TrendingUp,
  CheckCircle2,
  Clock,
  ArrowLeft,
  DollarSign,
} from 'lucide-react';
import {
  listGoals,
  getGoal,
  createGoal,
  deleteGoal,
  addContribution,
  getSavingsSummary,
  type SavingsGoal,
  type SavingsGoalDetail,
  type SavingsSummary,
} from '@/api/savings';
import { formatMoney } from '@/lib/currency';
import { useToast } from '@/components/ui/use-toast';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

export default function Savings() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [summary, setSummary] = useState<SavingsSummary | null>(null);
  const [selectedGoal, setSelectedGoal] = useState<SavingsGoalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showContributeModal, setShowContributeModal] = useState(false);
  const [contributeGoalId, setContributeGoalId] = useState<number | null>(null);

  // Form states
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formTarget, setFormTarget] = useState('');
  const [formDeadline, setFormDeadline] = useState('');
  const [formColor, setFormColor] = useState('#3b82f6');

  const [contributeAmount, setContributeAmount] = useState('');
  const [contributeNote, setContributeNote] = useState('');

  const [submitting, setSubmitting] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [goalsData, summaryData] = await Promise.all([
        listGoals(),
        getSavingsSummary(),
      ]);
      setGoals(goalsData);
      setSummary(summaryData);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load savings data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleViewGoal = async (goalId: number) => {
    try {
      const detail = await getGoal(goalId);
      setSelectedGoal(detail);
    } catch (err: unknown) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to load goal details',
        variant: 'destructive',
      });
    }
  };

  const handleCreateGoal = async () => {
    if (!formName.trim() || !formTarget) return;
    setSubmitting(true);
    try {
      await createGoal({
        name: formName.trim(),
        description: formDescription.trim() || undefined,
        target_amount: parseFloat(formTarget),
        deadline: formDeadline || undefined,
        color: formColor,
      });
      toast({ title: 'Goal created', description: `"${formName}" has been created.` });
      setShowCreateModal(false);
      resetCreateForm();
      await fetchData();
    } catch (err: unknown) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to create goal',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteGoal = async (goalId: number) => {
    try {
      await deleteGoal(goalId);
      toast({ title: 'Goal deleted', description: 'The savings goal has been removed.' });
      if (selectedGoal?.id === goalId) setSelectedGoal(null);
      await fetchData();
    } catch (err: unknown) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to delete goal',
        variant: 'destructive',
      });
    }
  };

  const openContributeModal = (goalId: number) => {
    setContributeGoalId(goalId);
    setContributeAmount('');
    setContributeNote('');
    setShowContributeModal(true);
  };

  const handleContribute = async () => {
    if (!contributeGoalId || !contributeAmount) return;
    setSubmitting(true);
    try {
      const updated = await addContribution(contributeGoalId, {
        amount: parseFloat(contributeAmount),
        note: contributeNote.trim() || undefined,
      });
      toast({ title: 'Contribution added', description: `Added ${currency(parseFloat(contributeAmount))}` });
      setShowContributeModal(false);
      setSelectedGoal(updated);
      await fetchData();
    } catch (err: unknown) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to add contribution',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const resetCreateForm = () => {
    setFormName('');
    setFormDescription('');
    setFormTarget('');
    setFormDeadline('');
    setFormColor('#3b82f6');
  };

  // Detail view
  if (selectedGoal) {
    return (
      <div className="page-wrap">
        <div className="page-header">
          <div className="flex items-center gap-4 mb-4">
            <Button variant="ghost" size="sm" onClick={() => setSelectedGoal(null)}>
              <ArrowLeft className="w-4 h-4 mr-1" />
              Back to Goals
            </Button>
          </div>
          <div className="flex justify-between items-start">
            <div>
              <h1 className="page-title">{selectedGoal.name}</h1>
              {selectedGoal.description && (
                <p className="page-subtitle">{selectedGoal.description}</p>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="financial" size="sm" onClick={() => openContributeModal(selectedGoal.id)}>
                <Plus className="w-4 h-4" />
                Add Contribution
              </Button>
              <Button variant="outline" size="sm" onClick={() => void handleDeleteGoal(selectedGoal.id)}>
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Progress overview */}
        <FinancialCard variant="financial" className="mb-8 fade-in-up">
          <FinancialCardContent className="pt-6">
            <div className="flex justify-between items-end mb-3">
              <div>
                <div className="text-sm text-muted-foreground">Current / Target</div>
                <div className="metric-value text-foreground">
                  {currency(selectedGoal.current_amount, selectedGoal.currency)}{' '}
                  <span className="text-muted-foreground text-lg font-normal">
                    / {currency(selectedGoal.target_amount, selectedGoal.currency)}
                  </span>
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-primary">{selectedGoal.progress.toFixed(1)}%</div>
                {selectedGoal.deadline && (
                  <div className="text-xs text-muted-foreground">
                    Deadline: {new Date(selectedGoal.deadline).toLocaleDateString()}
                  </div>
                )}
              </div>
            </div>

            {/* Progress bar with milestone markers */}
            <div className="relative mt-4 mb-2">
              <Progress value={Math.min(selectedGoal.progress, 100)} className="h-4" />
              {/* Milestone markers */}
              <div className="absolute top-0 left-0 w-full h-4 pointer-events-none">
                {selectedGoal.milestones.map((ms) => (
                  <div
                    key={ms.id}
                    className="absolute top-0 h-full flex items-center"
                    style={{ left: `${ms.target_percentage}%`, transform: 'translateX(-50%)' }}
                  >
                    <div
                      className={`w-2 h-6 rounded-full border-2 ${
                        ms.reached_at
                          ? 'bg-green-500 border-green-600'
                          : 'bg-white border-gray-400'
                      }`}
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Milestone labels */}
            <div className="flex justify-between mt-4 flex-wrap gap-2">
              {selectedGoal.milestones.map((ms) => (
                <div
                  key={ms.id}
                  className={`text-xs px-2 py-1 rounded-full ${
                    ms.reached_at
                      ? 'bg-green-100 text-green-700'
                      : 'bg-gray-100 text-gray-500'
                  }`}
                >
                  {ms.reached_at ? <CheckCircle2 className="w-3 h-3 inline mr-1" /> : null}
                  {ms.name} ({ms.target_percentage}%)
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        {/* Contributions history */}
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader>
            <FinancialCardTitle className="section-title">Contributions</FinancialCardTitle>
            <FinancialCardDescription>
              {selectedGoal.contributions.length} contribution(s) made
            </FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            {selectedGoal.contributions.length === 0 ? (
              <div className="text-sm text-muted-foreground py-4 text-center">
                No contributions yet. Add your first contribution to get started!
              </div>
            ) : (
              <div className="space-y-3">
                {selectedGoal.contributions.map((c) => (
                  <div key={c.id} className="interactive-row flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-green-100 text-green-600">
                        <DollarSign className="w-4 h-4" />
                      </div>
                      <div>
                        <div className="font-medium text-foreground text-sm">
                          {c.note || 'Contribution'}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {c.contributed_at
                            ? new Date(c.contributed_at).toLocaleDateString()
                            : '-'}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-green-600">
                      +{currency(c.amount, selectedGoal.currency)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </FinancialCardContent>
          <FinancialCardFooter>
            <Button
              variant="financial"
              size="sm"
              className="w-full"
              onClick={() => openContributeModal(selectedGoal.id)}
            >
              <Plus className="w-4 h-4" />
              Add Contribution
            </Button>
          </FinancialCardFooter>
        </FinancialCard>

        {/* Contribute Modal */}
        <Dialog open={showContributeModal} onOpenChange={setShowContributeModal}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Contribution</DialogTitle>
              <DialogDescription>Add money towards your savings goal.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <label className="text-sm font-medium" htmlFor="contribute-amount">
                  Amount
                </label>
                <input
                  id="contribute-amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  className="input w-full mt-1"
                  placeholder="0.00"
                  value={contributeAmount}
                  onChange={(e) => setContributeAmount(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm font-medium" htmlFor="contribute-note">
                  Note (optional)
                </label>
                <input
                  id="contribute-note"
                  type="text"
                  className="input w-full mt-1"
                  placeholder="e.g., Monthly savings"
                  value={contributeNote}
                  onChange={(e) => setContributeNote(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowContributeModal(false)}>
                Cancel
              </Button>
              <Button
                variant="financial"
                disabled={!contributeAmount || submitting}
                onClick={() => void handleContribute()}
              >
                {submitting ? 'Adding...' : 'Add Contribution'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // Goals list view
  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">Track your progress towards financial goals.</p>
          </div>
          <Button variant="financial" size="sm" onClick={() => setShowCreateModal(true)}>
            <Plus className="w-4 h-4" />
            New Goal
          </Button>
        </div>
      </div>

      {error && (
        <div className="error mb-6">{error}</div>
      )}

      {/* Summary cards */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Total Saved
                </FinancialCardTitle>
                <PiggyBank className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {loading ? '...' : currency(summary.total_saved)}
              </div>
              <div className="text-sm text-muted-foreground">
                of {currency(summary.total_target)} target
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Overall Progress
                </FinancialCardTitle>
                <TrendingUp className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {loading ? '...' : `${summary.overall_progress.toFixed(1)}%`}
              </div>
              <Progress value={summary.overall_progress} className="h-2 mt-2" />
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  In Progress
                </FinancialCardTitle>
                <Clock className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {loading ? '...' : summary.in_progress_goals}
              </div>
              <div className="text-sm text-muted-foreground">active goal(s)</div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Completed
                </FinancialCardTitle>
                <CheckCircle2 className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {loading ? '...' : summary.completed_goals}
              </div>
              <div className="text-sm text-muted-foreground">goal(s) achieved</div>
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {/* Goals list */}
      {loading && goals.length === 0 ? (
        <div className="text-center text-muted-foreground py-12">Loading savings goals...</div>
      ) : goals.length === 0 ? (
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardContent className="py-12 text-center">
            <Target className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold text-foreground mb-2">No savings goals yet</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Create your first savings goal to start tracking your progress.
            </p>
            <Button variant="financial" onClick={() => setShowCreateModal(true)}>
              <Plus className="w-4 h-4" />
              Create Your First Goal
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {goals.map((goal) => (
            <FinancialCard
              key={goal.id}
              variant="financial"
              className="group card-interactive fade-in-up cursor-pointer"
              onClick={() => void handleViewGoal(goal.id)}
            >
              <FinancialCardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-white"
                      style={{ backgroundColor: goal.color || '#3b82f6' }}
                    >
                      <Target className="w-4 h-4" />
                    </div>
                    <FinancialCardTitle className="text-base font-semibold">
                      {goal.name}
                    </FinancialCardTitle>
                  </div>
                  {goal.is_completed && (
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                  )}
                </div>
                {goal.description && (
                  <FinancialCardDescription className="mt-1">
                    {goal.description}
                  </FinancialCardDescription>
                )}
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-muted-foreground">
                    {currency(goal.current_amount, goal.currency)}
                  </span>
                  <span className="font-medium text-foreground">
                    {currency(goal.target_amount, goal.currency)}
                  </span>
                </div>
                <Progress value={Math.min(goal.progress, 100)} className="h-2 mb-2" />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{goal.progress.toFixed(1)}% complete</span>
                  {goal.deadline && (
                    <span>Due {new Date(goal.deadline).toLocaleDateString()}</span>
                  )}
                </div>
              </FinancialCardContent>
              <FinancialCardFooter className="flex gap-2">
                <Button
                  variant="financial"
                  size="sm"
                  className="flex-1"
                  onClick={(e) => {
                    e.stopPropagation();
                    openContributeModal(goal.id);
                  }}
                >
                  <Plus className="w-4 h-4" />
                  Contribute
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleDeleteGoal(goal.id);
                  }}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </FinancialCardFooter>
            </FinancialCard>
          ))}
        </div>
      )}

      {/* Create Goal Modal */}
      <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Savings Goal</DialogTitle>
            <DialogDescription>
              Set a target and track your progress with automatic milestones at 25%, 50%, 75%, and 100%.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium" htmlFor="goal-name">
                Goal Name *
              </label>
              <input
                id="goal-name"
                type="text"
                className="input w-full mt-1"
                placeholder="e.g., Emergency Fund"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium" htmlFor="goal-description">
                Description
              </label>
              <input
                id="goal-description"
                type="text"
                className="input w-full mt-1"
                placeholder="e.g., 6 months of living expenses"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium" htmlFor="goal-target">
                Target Amount *
              </label>
              <input
                id="goal-target"
                type="number"
                step="0.01"
                min="0.01"
                className="input w-full mt-1"
                placeholder="0.00"
                value={formTarget}
                onChange={(e) => setFormTarget(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium" htmlFor="goal-deadline">
                Deadline (optional)
              </label>
              <input
                id="goal-deadline"
                type="date"
                className="input w-full mt-1"
                value={formDeadline}
                onChange={(e) => setFormDeadline(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium" htmlFor="goal-color">
                Color
              </label>
              <div className="flex gap-2 mt-1">
                {['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'].map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`w-8 h-8 rounded-full border-2 ${
                      formColor === c ? 'border-foreground ring-2 ring-primary' : 'border-transparent'
                    }`}
                    style={{ backgroundColor: c }}
                    onClick={() => setFormColor(c)}
                  />
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreateModal(false); resetCreateForm(); }}>
              Cancel
            </Button>
            <Button
              variant="financial"
              disabled={!formName.trim() || !formTarget || submitting}
              onClick={() => void handleCreateGoal()}
            >
              {submitting ? 'Creating...' : 'Create Goal'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Contribute Modal (from list view) */}
      <Dialog open={showContributeModal} onOpenChange={setShowContributeModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Contribution</DialogTitle>
            <DialogDescription>Add money towards your savings goal.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium" htmlFor="list-contribute-amount">
                Amount
              </label>
              <input
                id="list-contribute-amount"
                type="number"
                step="0.01"
                min="0.01"
                className="input w-full mt-1"
                placeholder="0.00"
                value={contributeAmount}
                onChange={(e) => setContributeAmount(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium" htmlFor="list-contribute-note">
                Note (optional)
              </label>
              <input
                id="list-contribute-note"
                type="text"
                className="input w-full mt-1"
                placeholder="e.g., Monthly savings"
                value={contributeNote}
                onChange={(e) => setContributeNote(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowContributeModal(false)}>
              Cancel
            </Button>
            <Button
              variant="financial"
              disabled={!contributeAmount || submitting}
              onClick={() => void handleContribute()}
            >
              {submitting ? 'Adding...' : 'Add Contribution'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
