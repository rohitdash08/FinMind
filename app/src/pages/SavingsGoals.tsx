import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { Plus, Target, Wallet, TrendingUp, Calendar, Trash2 } from 'lucide-react';
import {
  listGoals,
  createGoal,
  deleteGoal,
  addContribution,
  type SavingsGoal,
  type SavingsGoalCreate,
} from '@/api/savings';
import { useToast } from '@/hooks/use-toast';

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4'];

function getMilestone(progress: number): string {
  if (progress >= 100) return '🏆 Goal reached!';
  if (progress >= 75) return '🔥 Almost there!';
  if (progress >= 50) return '💪 Halfway!';
  if (progress >= 25) return '🌱 Growing!';
  return '🚀 Just started';
}

export default function SavingsGoals() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [contributeGoalId, setContributeGoalId] = useState<number | null>(null);
  const [newGoal, setNewGoal] = useState<SavingsGoalCreate>({
    name: '',
    target_amount: 0,
    color: COLORS[0],
  });
  const [contributionAmount, setContributionAmount] = useState('');
  const [contributionNotes, setContributionNotes] = useState('');

  const { data: goals = [], isLoading } = useQuery({
    queryKey: ['savings-goals'],
    queryFn: () => listGoals(),
  });

  const createMutation = useMutation({
    mutationFn: createGoal,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savings-goals'] });
      setShowCreate(false);
      setNewGoal({ name: '', target_amount: 0, color: COLORS[0] });
      toast({ title: 'Goal created!', description: 'Start saving towards your goal.' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to create goal.', variant: 'destructive' }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteGoal,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savings-goals'] });
      toast({ title: 'Goal deleted' });
    },
  });

  const contributeMutation = useMutation({
    mutationFn: ({ goalId, amount, notes }: { goalId: number; amount: number; notes?: string }) =>
      addContribution(goalId, { amount, notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savings-goals'] });
      setContributeGoalId(null);
      setContributionAmount('');
      setContributionNotes('');
      toast({ title: 'Contribution added!', description: 'Great progress!' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to add contribution.', variant: 'destructive' }),
  });

  const totalSaved = goals.reduce((sum, g) => sum + g.current_amount, 0);
  const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0);
  const overallProgress = totalTarget > 0 ? Math.round((totalSaved / totalTarget) * 100) : 0;

  return (
    <div className="space-y-6 p-4 md:p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Savings Goals</h1>
          <p className="text-muted-foreground">Track your progress towards financial milestones</p>
        </div>
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" /> New Goal
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Savings Goal</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label htmlFor="goal-name">Goal Name</Label>
                <Input
                  id="goal-name"
                  placeholder="e.g. Emergency Fund"
                  value={newGoal.name}
                  onChange={(e) => setNewGoal({ ...newGoal, name: e.target.value })}
                />
              </div>
              <div>
                <Label htmlFor="goal-target">Target Amount</Label>
                <Input
                  id="goal-target"
                  type="number"
                  min="1"
                  placeholder="5000"
                  value={newGoal.target_amount || ''}
                  onChange={(e) => setNewGoal({ ...newGoal, target_amount: Number(e.target.value) })}
                />
              </div>
              <div>
                <Label htmlFor="goal-date">Target Date (optional)</Label>
                <Input
                  id="goal-date"
                  type="date"
                  value={newGoal.target_date || ''}
                  onChange={(e) => setNewGoal({ ...newGoal, target_date: e.target.value })}
                />
              </div>
              <div>
                <Label>Color</Label>
                <div className="flex gap-2 mt-1">
                  {COLORS.map((c) => (
                    <button
                      key={c}
                      className={`w-8 h-8 rounded-full border-2 ${newGoal.color === c ? 'border-foreground' : 'border-transparent'}`}
                      style={{ backgroundColor: c }}
                      onClick={() => setNewGoal({ ...newGoal, color: c })}
                    />
                  ))}
                </div>
              </div>
              <Button
                className="w-full"
                disabled={!newGoal.name || !newGoal.target_amount}
                onClick={() => createMutation.mutate(newGoal)}
              >
                Create Goal
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between pb-2">
            <FinancialCardTitle className="text-sm font-medium">Total Saved</FinancialCardTitle>
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">${totalSaved.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">of ${totalTarget.toLocaleString()} target</p>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between pb-2">
            <FinancialCardTitle className="text-sm font-medium">Overall Progress</FinancialCardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{overallProgress}%</div>
            <Progress value={overallProgress} className="mt-2" />
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader className="flex flex-row items-center justify-between pb-2">
            <FinancialCardTitle className="text-sm font-medium">Active Goals</FinancialCardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{goals.length}</div>
            <p className="text-xs text-muted-foreground">
              {goals.filter((g) => g.progress >= 100).length} completed
            </p>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals Grid */}
      {isLoading ? (
        <div className="text-center py-12 text-muted-foreground">Loading goals...</div>
      ) : goals.length === 0 ? (
        <FinancialCard>
          <FinancialCardContent className="text-center py-12">
            <Target className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">No savings goals yet</h3>
            <p className="text-muted-foreground mb-4">
              Create your first goal and start tracking your progress.
            </p>
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-2 h-4 w-4" /> Create Goal
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {goals.map((goal) => (
            <GoalCard
              key={goal.id}
              goal={goal}
              onContribute={() => setContributeGoalId(goal.id)}
              onDelete={() => deleteMutation.mutate(goal.id)}
            />
          ))}
        </div>
      )}

      {/* Contribute Dialog */}
      <Dialog
        open={contributeGoalId !== null}
        onOpenChange={(open) => !open && setContributeGoalId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Contribution</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="contrib-amount">Amount</Label>
              <Input
                id="contrib-amount"
                type="number"
                min="0.01"
                step="0.01"
                placeholder="100"
                value={contributionAmount}
                onChange={(e) => setContributionAmount(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="contrib-notes">Notes (optional)</Label>
              <Input
                id="contrib-notes"
                placeholder="e.g. Monthly savings"
                value={contributionNotes}
                onChange={(e) => setContributionNotes(e.target.value)}
              />
            </div>
            <Button
              className="w-full"
              disabled={!contributionAmount || Number(contributionAmount) <= 0}
              onClick={() =>
                contributeGoalId &&
                contributeMutation.mutate({
                  goalId: contributeGoalId,
                  amount: Number(contributionAmount),
                  notes: contributionNotes || undefined,
                })
              }
            >
              Add Contribution
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GoalCard({
  goal,
  onContribute,
  onDelete,
}: {
  goal: SavingsGoal;
  onContribute: () => void;
  onDelete: () => void;
}) {
  const milestone = getMilestone(goal.progress);
  const isComplete = goal.progress >= 100;

  return (
    <FinancialCard className="relative overflow-hidden">
      <div
        className="absolute top-0 left-0 h-1 w-full"
        style={{ backgroundColor: goal.color }}
      />
      <FinancialCardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <FinancialCardTitle className="text-base">{goal.name}</FinancialCardTitle>
          <Badge variant={isComplete ? 'default' : 'secondary'}>{milestone}</Badge>
        </div>
      </FinancialCardHeader>
      <FinancialCardContent className="space-y-4">
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span>${goal.current_amount.toLocaleString()}</span>
            <span className="text-muted-foreground">${goal.target_amount.toLocaleString()}</span>
          </div>
          <Progress value={Math.min(goal.progress, 100)} />
          <p className="text-xs text-muted-foreground mt-1">{goal.progress}% complete</p>
        </div>

        {goal.target_date && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Calendar className="h-3 w-3" />
            <span>Target: {new Date(goal.target_date).toLocaleDateString()}</span>
          </div>
        )}

        <div className="flex gap-2">
          <Button size="sm" className="flex-1" onClick={onContribute} disabled={isComplete}>
            <Plus className="mr-1 h-3 w-3" /> Contribute
          </Button>
          <Button size="sm" variant="ghost" onClick={onDelete}>
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      </FinancialCardContent>
    </FinancialCard>
  );
}
