import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import {
  listGoals,
  createGoal,
  deleteGoal,
  contribute,
  type SavingsGoal,
} from '@/api/goals';
import { formatMoney } from '@/lib/currency';

export function Goals() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);

  // New goal form
  const [name, setName] = useState('');
  const [target, setTarget] = useState('');
  const [deadline, setDeadline] = useState('');
  const [creating, setCreating] = useState(false);

  // Contribute form
  const [contributeGoalId, setContributeGoalId] = useState<number | null>(null);
  const [contributeAmount, setContributeAmount] = useState('');
  const [contributeNotes, setContributeNotes] = useState('');

  async function load() {
    setLoading(true);
    try {
      setGoals(await listGoals());
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load goals';
      toast({ title: 'Error', description: msg });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onCreate = async () => {
    if (!name.trim() || !target) return;
    setCreating(true);
    try {
      await createGoal({
        name: name.trim(),
        target_amount: parseFloat(target),
        deadline: deadline || undefined,
      });
      setName('');
      setTarget('');
      setDeadline('');
      await load();
      toast({ title: 'Goal created', description: `"${name}" is set!` });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create goal';
      toast({ title: 'Error', description: msg });
    } finally {
      setCreating(false);
    }
  };

  const onDelete = async (id: number) => {
    try {
      await deleteGoal(id);
      await load();
      toast({ title: 'Goal deleted' });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete goal';
      toast({ title: 'Error', description: msg });
    }
  };

  const onContribute = async (goalId: number) => {
    if (!contributeAmount) return;
    try {
      const result = await contribute(goalId, {
        amount: parseFloat(contributeAmount),
        notes: contributeNotes || undefined,
      });
      setContributeGoalId(null);
      setContributeAmount('');
      setContributeNotes('');
      await load();
      if (result.milestone_reached) {
        toast({
          title: '🎉 Goal Achieved!',
          description: `Congratulations! You've reached your "${result.name}" target!`,
        });
      } else {
        toast({ title: 'Contribution added' });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to contribute';
      toast({ title: 'Error', description: msg });
    }
  };

  const achieved = goals.filter((g) => g.achieved);
  const active = goals.filter((g) => !g.achieved);

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title">Savings Goals</h1>
          <p className="page-subtitle">
            Track your savings targets and celebrate milestones.
          </p>
        </div>
      </div>

      {/* Create goal form */}
      <FinancialCard variant="financial">
        <FinancialCardHeader>
          <FinancialCardTitle>New Goal</FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <Label htmlFor="goal-name">Goal Name</Label>
              <Input
                id="goal-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Vacation Fund"
              />
            </div>
            <div>
              <Label htmlFor="goal-target">Target Amount</Label>
              <Input
                id="goal-target"
                type="number"
                min="1"
                step="0.01"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="5000"
              />
            </div>
            <div>
              <Label htmlFor="goal-deadline">Deadline (optional)</Label>
              <Input
                id="goal-deadline"
                type="date"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
              />
            </div>
            <div className="flex items-end">
              <Button
                variant="hero"
                className="w-full"
                onClick={() => void onCreate()}
                disabled={creating || !name.trim() || !target}
              >
                {creating ? 'Creating…' : 'Create Goal'}
              </Button>
            </div>
          </div>
        </FinancialCardContent>
      </FinancialCard>

      {/* Active goals */}
      {active.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Active Goals</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {active.map((g) => (
              <FinancialCard key={g.id}>
                <FinancialCardHeader>
                  <FinancialCardTitle>{g.name}</FinancialCardTitle>
                  <FinancialCardDescription>
                    {g.deadline ? `Due ${g.deadline}` : 'No deadline'}
                  </FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span>{formatMoney(g.current_amount)}</span>
                    <span className="text-muted-foreground">
                      of {formatMoney(g.target_amount)}
                    </span>
                  </div>
                  <Progress value={Math.min(g.progress_pct, 100)} className="h-2" />
                  <p className="text-xs text-muted-foreground text-right">
                    {g.progress_pct.toFixed(1)}%
                  </p>

                  {contributeGoalId === g.id ? (
                    <div className="space-y-2">
                      <Input
                        type="number"
                        min="0.01"
                        step="0.01"
                        placeholder="Amount"
                        value={contributeAmount}
                        onChange={(e) => setContributeAmount(e.target.value)}
                      />
                      <Input
                        placeholder="Notes (optional)"
                        value={contributeNotes}
                        onChange={(e) => setContributeNotes(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => void onContribute(g.id)}
                          disabled={!contributeAmount}
                        >
                          Save
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setContributeGoalId(null)}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="financial"
                        onClick={() => setContributeGoalId(g.id)}
                      >
                        + Contribute
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive"
                        onClick={() => void onDelete(g.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            ))}
          </div>
        </div>
      )}

      {/* Achieved goals */}
      {achieved.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Achieved Goals</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {achieved.map((g) => (
              <FinancialCard key={g.id} variant="success">
                <FinancialCardHeader>
                  <FinancialCardTitle>{g.name}</FinancialCardTitle>
                  <FinancialCardDescription>
                    Target reached!
                  </FinancialCardDescription>
                </FinancialCardHeader>
                <FinancialCardContent>
                  <p className="text-lg font-bold">
                    {formatMoney(g.current_amount)} / {formatMoney(g.target_amount)}
                  </p>
                  <Progress value={100} className="h-2 mt-2" />
                </FinancialCardContent>
              </FinancialCard>
            ))}
          </div>
        </div>
      )}

      {loading && goals.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <p className="text-muted-foreground">Loading savings goals…</p>
        </div>
      )}

      {!loading && goals.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <p className="text-muted-foreground">
            No savings goals yet. Create one above to start tracking!
          </p>
        </div>
      )}
    </div>
  );
}
