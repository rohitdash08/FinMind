import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Target, Plus, Trash2, PiggyBank, Trophy, Calendar, ArrowDownLeft } from 'lucide-react';
import {
  listSavingsGoals,
  createSavingsGoal,
  updateSavingsGoal,
  depositToGoal,
  withdrawFromGoal,
  deleteSavingsGoal,
  type SavingsGoal,
  type SavingsGoalCreate,
} from '@/api/savingsGoals';

type TransactionType = 'deposit' | 'withdraw';

export default function SavingsGoals() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [createOpen, setCreateOpen] = useState(false);
  const [transactionGoal, setTransactionGoal] = useState<{ id: number; type: TransactionType } | null>(null);
  const [transactionAmount, setTransactionAmount] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const { data: goals = [], isLoading } = useQuery({
    queryKey: ['savings-goals', statusFilter],
    queryFn: () => listSavingsGoals(statusFilter || undefined),
  });

  const invalidateGoals = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['savings-goals'] });
  }, [queryClient]);

  const createMutation = useMutation({
    mutationFn: (payload: SavingsGoalCreate) => createSavingsGoal(payload),
    onSuccess: () => {
      invalidateGoals();
      setCreateOpen(false);
      toast({ title: 'Goal created', description: 'Your savings goal has been created.' });
    },
    onError: (err: Error) => {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    },
  });

  const depositMutation = useMutation({
    mutationFn: ({ id, amount }: { id: number; amount: number }) => depositToGoal(id, amount),
    onSuccess: (data) => {
      invalidateGoals();
      setTransactionGoal(null);
      setTransactionAmount('');
      const msg = data.status === 'COMPLETED'
        ? 'Congratulations! You have reached your savings goal!'
        : 'Amount has been added to your goal.';
      toast({ title: 'Deposit added', description: msg });
    },
    onError: (err: Error) => {
      toast({ title: 'Deposit failed', description: err.message, variant: 'destructive' });
    },
  });

  const withdrawMutation = useMutation({
    mutationFn: ({ id, amount }: { id: number; amount: number }) => withdrawFromGoal(id, amount),
    onSuccess: () => {
      invalidateGoals();
      setTransactionGoal(null);
      setTransactionAmount('');
      toast({ title: 'Withdrawal complete', description: 'Amount has been withdrawn from your goal.' });
    },
    onError: (err: Error) => {
      toast({ title: 'Withdrawal failed', description: err.message, variant: 'destructive' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteSavingsGoal(id),
    onSuccess: () => {
      invalidateGoals();
      setConfirmDelete(null);
      toast({ title: 'Goal deleted' });
    },
    onError: (err: Error) => {
      toast({ title: 'Delete failed', description: err.message, variant: 'destructive' });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => updateSavingsGoal(id, { status: 'CANCELLED' }),
    onSuccess: () => {
      invalidateGoals();
      toast({ title: 'Goal cancelled' });
    },
    onError: (err: Error) => {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    },
  });

  const handleCreate = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const payload: SavingsGoalCreate = {
      name: (form.get('name') as string).trim(),
      target_amount: Number(form.get('target_amount')),
      current_amount: Number(form.get('current_amount') || 0),
      currency: (form.get('currency') as string) || undefined,
      deadline: (form.get('deadline') as string) || undefined,
    };
    if (!payload.name) return;
    if (!payload.target_amount || payload.target_amount <= 0) return;
    createMutation.mutate(payload);
  };

  const handleTransaction = () => {
    if (!transactionGoal) return;
    const amount = parseFloat(transactionAmount);
    if (!amount || amount <= 0) return;
    if (transactionGoal.type === 'deposit') {
      depositMutation.mutate({ id: transactionGoal.id, amount });
    } else {
      withdrawMutation.mutate({ id: transactionGoal.id, amount });
    }
  };

  const isTransacting = depositMutation.isPending || withdrawMutation.isPending;

  const activeGoals = goals.filter((g) => g.status === 'ACTIVE');
  const completedGoals = goals.filter((g) => g.status === 'COMPLETED');
  const totalSaved = goals.reduce((sum, g) => sum + g.current_amount, 0);
  const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0);

  // Use the most common currency among goals, or a generic label
  const primaryCurrency = goals.length > 0 ? goals[0].currency : '';

  const formatAmount = (amount: number, currency?: string) => {
    const cur = currency || primaryCurrency;
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: cur || 'USD',
        minimumFractionDigits: 2,
      }).format(amount);
    } catch {
      // Fallback if Intl doesn't recognize the currency
      return `${cur} ${amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    }
  };

  // Check if all goals share the same currency (only show summary totals if so)
  const currencies = new Set(goals.map((g) => g.currency));
  const isMixedCurrency = currencies.size > 1;

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Target className="h-6 w-6 text-primary" />
            Savings Goals
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Track your financial goals and milestones
          </p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button variant="hero">
              <Plus className="h-4 w-4 mr-2" />
              New Goal
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Savings Goal</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <Label htmlFor="name">Goal Name</Label>
                <Input
                  id="name"
                  name="name"
                  placeholder="e.g. Emergency Fund"
                  maxLength={200}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="target_amount">Target Amount</Label>
                  <Input
                    id="target_amount"
                    name="target_amount"
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="5000"
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="current_amount">Starting Amount</Label>
                  <Input
                    id="current_amount"
                    name="current_amount"
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="currency">Currency</Label>
                  <Input id="currency" name="currency" placeholder="USD" maxLength={10} />
                </div>
                <div>
                  <Label htmlFor="deadline">Deadline</Label>
                  <Input id="deadline" name="deadline" type="date" />
                </div>
              </div>
              <Button type="submit" className="w-full" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Goal'}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardDescription>Total Saved</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              {isMixedCurrency
                ? `${totalSaved.toLocaleString('en-US', { minimumFractionDigits: 2 })} (mixed)`
                : formatAmount(totalSaved)}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardDescription>Total Target</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              {isMixedCurrency
                ? `${totalTarget.toLocaleString('en-US', { minimumFractionDigits: 2 })} (mixed)`
                : formatAmount(totalTarget)}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardDescription>Goals Progress</FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              {completedGoals.length} / {goals.length} completed
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {['', 'ACTIVE', 'COMPLETED', 'CANCELLED'].map((s) => (
          <Button
            key={s}
            variant={statusFilter === s ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(s)}
          >
            {s || 'All'}
          </Button>
        ))}
      </div>

      {/* Goals List */}
      {isLoading ? (
        <p className="text-muted-foreground text-center py-12">Loading goals...</p>
      ) : goals.length === 0 ? (
        <FinancialCard variant="financial" className="text-center py-12">
          <FinancialCardContent>
            <PiggyBank className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
              {statusFilter
                ? `No ${statusFilter.toLowerCase()} goals found.`
                : 'No savings goals yet. Create your first goal to start tracking!'}
            </p>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {goals.map((goal) => (
            <GoalCard
              key={goal.id}
              goal={goal}
              formatAmount={formatAmount}
              onDeposit={() => setTransactionGoal({ id: goal.id, type: 'deposit' })}
              onWithdraw={() => setTransactionGoal({ id: goal.id, type: 'withdraw' })}
              onCancel={() => {
                if (window.confirm(`Cancel the goal "${goal.name}"? You can still view it later.`)) {
                  cancelMutation.mutate(goal.id);
                }
              }}
              onDelete={() => setConfirmDelete(goal.id)}
              isCancelling={cancelMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* Deposit / Withdraw Dialog */}
      <Dialog
        open={transactionGoal !== null}
        onOpenChange={() => {
          setTransactionGoal(null);
          setTransactionAmount('');
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {transactionGoal?.type === 'deposit' ? 'Add Deposit' : 'Withdraw Funds'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="transaction_amount">Amount</Label>
              <Input
                id="transaction_amount"
                type="number"
                step="0.01"
                min="0.01"
                value={transactionAmount}
                onChange={(e) => setTransactionAmount(e.target.value)}
                placeholder="100.00"
                autoFocus
              />
            </div>
            <Button
              className="w-full"
              onClick={handleTransaction}
              disabled={isTransacting || !transactionAmount || parseFloat(transactionAmount) <= 0}
            >
              {isTransacting
                ? 'Processing...'
                : transactionGoal?.type === 'deposit'
                  ? 'Add Deposit'
                  : 'Withdraw'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={confirmDelete !== null} onOpenChange={() => setConfirmDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Goal</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to permanently delete this savings goal? This action cannot be undone.
          </p>
          <div className="flex gap-2 justify-end pt-4">
            <Button variant="outline" onClick={() => setConfirmDelete(null)}>
              Keep
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (confirmDelete !== null) {
                  deleteMutation.mutate(confirmDelete);
                }
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GoalCard({
  goal,
  formatAmount,
  onDeposit,
  onWithdraw,
  onCancel,
  onDelete,
  isCancelling,
}: {
  goal: SavingsGoal;
  formatAmount: (amount: number, currency?: string) => string;
  onDeposit: () => void;
  onWithdraw: () => void;
  onCancel: () => void;
  onDelete: () => void;
  isCancelling: boolean;
}) {
  const statusBadge = {
    ACTIVE: <Badge variant="default">Active</Badge>,
    COMPLETED: <Badge className="bg-green-100 text-green-800">Completed</Badge>,
    CANCELLED: <Badge variant="secondary">Cancelled</Badge>,
  };

  const isOverdue =
    goal.deadline &&
    goal.status === 'ACTIVE' &&
    new Date(goal.deadline) < new Date();

  return (
    <FinancialCard variant="financial">
      <FinancialCardHeader>
        <div className="flex items-start justify-between">
          <div>
            <FinancialCardTitle className="text-lg">{goal.name}</FinancialCardTitle>
            <FinancialCardDescription className="mt-1">
              {formatAmount(goal.current_amount, goal.currency)}{' '}
              / {formatAmount(goal.target_amount, goal.currency)}
            </FinancialCardDescription>
          </div>
          {statusBadge[goal.status]}
        </div>
      </FinancialCardHeader>
      <FinancialCardContent className="space-y-4">
        {/* Progress Bar */}
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-muted-foreground">Progress</span>
            <span className="font-medium">{goal.progress}%</span>
          </div>
          <Progress value={Math.min(goal.progress, 100)} className="h-3" />
        </div>

        {/* Milestones */}
        <div className="flex justify-between">
          {goal.milestones.map((m) => (
            <div key={m.percentage} className="flex flex-col items-center gap-1">
              <Trophy
                className={`h-4 w-4 ${m.reached ? 'text-yellow-500' : 'text-muted-foreground/30'}`}
              />
              <span className={`text-xs ${m.reached ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>
                {m.percentage}%
              </span>
            </div>
          ))}
        </div>

        {/* Deadline */}
        {goal.deadline && (
          <div className={`flex items-center gap-1 text-sm ${isOverdue ? 'text-destructive font-medium' : 'text-muted-foreground'}`}>
            <Calendar className="h-3.5 w-3.5" />
            {isOverdue ? 'Overdue: ' : 'Deadline: '}
            {new Date(goal.deadline).toLocaleDateString()}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          {goal.status === 'ACTIVE' && (
            <>
              <Button size="sm" onClick={onDeposit}>
                <PiggyBank className="h-3.5 w-3.5 mr-1" />
                Deposit
              </Button>
              {goal.current_amount > 0 && (
                <Button size="sm" variant="outline" onClick={onWithdraw}>
                  <ArrowDownLeft className="h-3.5 w-3.5 mr-1" />
                  Withdraw
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={onCancel} disabled={isCancelling}>
                Cancel
              </Button>
            </>
          )}
          {goal.status === 'COMPLETED' && goal.current_amount > 0 && (
            <Button size="sm" variant="outline" onClick={onWithdraw}>
              <ArrowDownLeft className="h-3.5 w-3.5 mr-1" />
              Withdraw
            </Button>
          )}
          <Button size="sm" variant="ghost" className="text-destructive ml-auto" onClick={onDelete}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </FinancialCardContent>
    </FinancialCard>
  );
}
