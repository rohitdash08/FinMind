import { useCallback, useEffect, useState } from 'react';
import { Target, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/hooks/use-toast';
import {
  createSavingsGoal,
  deleteSavingsGoal,
  listSavingsGoals,
  updateSavingsGoal,
  type SavingsGoal,
} from '@/api/savingsGoals';

export default function SavingsGoals() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [currentAmount, setCurrentAmount] = useState('0');
  const [targetDate, setTargetDate] = useState('');
  const [milestones, setMilestones] = useState('25%:250, 50%:500, Done:1000');

  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setGoals(await listSavingsGoals());
    } catch (error: unknown) {
      toast({ title: 'Failed to load savings goals', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate() {
    if (!name.trim() || !targetAmount) return;
    setSaving(true);
    try {
      await createSavingsGoal({
        name: name.trim(),
        target_amount: Number(targetAmount),
        current_amount: Number(currentAmount || 0),
        target_date: targetDate || undefined,
        milestones: parseMilestones(milestones),
      });
      setName('');
      setTargetAmount('');
      setCurrentAmount('0');
      setTargetDate('');
      toast({ title: 'Savings goal created' });
      await refresh();
    } catch (error: unknown) {
      toast({ title: 'Failed to create goal', description: getErrorMessage(error, 'Please check the form.') });
    } finally {
      setSaving(false);
    }
  }

  async function onProgress(goal: SavingsGoal, amount: number) {
    setSaving(true);
    try {
      await updateSavingsGoal(goal.id, { current_amount: amount });
      await refresh();
      toast({ title: 'Progress updated' });
    } catch (error: unknown) {
      toast({ title: 'Failed to update progress', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: number) {
    setSaving(true);
    try {
      await deleteSavingsGoal(id);
      setGoals((prev) => prev.filter((goal) => goal.id !== id));
      toast({ title: 'Savings goal deleted' });
    } catch (error: unknown) {
      toast({ title: 'Failed to delete goal', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex flex-col gap-2">
          <h2 className="page-title text-2xl md:text-3xl">Savings Goals</h2>
          <p className="page-subtitle">Track target balances, progress, and milestone wins.</p>
        </div>
      </div>

      <section className="card p-5">
        <div className="grid gap-4 md:grid-cols-5">
          <div className="md:col-span-2">
            <Label htmlFor="goal-name">Goal</Label>
            <Input id="goal-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Emergency fund" />
          </div>
          <div>
            <Label htmlFor="target-amount">Target</Label>
            <Input id="target-amount" type="number" min="0" value={targetAmount} onChange={(e) => setTargetAmount(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="current-amount">Saved</Label>
            <Input id="current-amount" type="number" min="0" value={currentAmount} onChange={(e) => setCurrentAmount(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="target-date">Target date</Label>
            <Input id="target-date" type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
          <div>
            <Label htmlFor="milestones">Milestones</Label>
            <Input id="milestones" value={milestones} onChange={(e) => setMilestones(e.target.value)} placeholder="Starter:250, Halfway:500" />
          </div>
          <Button className="self-end" onClick={onCreate} disabled={saving || !name.trim() || !targetAmount}>
            Add Goal
          </Button>
        </div>
      </section>

      {loading ? (
        <div className="card p-5">Loading...</div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {goals.map((goal) => (
            <article key={goal.id} className="card card-interactive p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Target className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold">{goal.name}</h3>
                    <p className="text-sm text-muted-foreground">
                      {goal.currency} {goal.current_amount.toFixed(2)} of {goal.target_amount.toFixed(2)}
                    </p>
                  </div>
                </div>
                <Button variant="ghost" size="icon" onClick={() => onDelete(goal.id)} disabled={saving} aria-label="Delete goal">
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              <div className="mt-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span>{goal.progress_pct.toFixed(0)}% complete</span>
                  <span>{goal.remaining_amount.toFixed(2)} remaining</span>
                </div>
                <Progress value={Math.min(goal.progress_pct, 100)} />
              </div>

              <div className="mt-4 grid gap-2">
                {goal.milestones.map((milestone) => (
                  <div key={milestone.id} className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-sm">
                    <span>{milestone.name}</span>
                    <span className={milestone.reached ? 'font-semibold text-primary' : 'text-muted-foreground'}>
                      {milestone.reached ? 'Reached' : `${goal.currency} ${milestone.amount.toFixed(2)}`}
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-4 grid grid-cols-[1fr_auto] gap-2">
                <Input
                  type="number"
                  min="0"
                  defaultValue={goal.current_amount}
                  aria-label={`Update ${goal.name} progress`}
                  onBlur={(e) => {
                    const next = Number(e.target.value);
                    if (Number.isFinite(next) && next !== goal.current_amount) void onProgress(goal, next);
                  }}
                />
                <Button variant="outline" onClick={() => onProgress(goal, goal.target_amount)} disabled={saving}>
                  Mark Done
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function parseMilestones(value: string): Array<{ name: string; amount: number }> {
  return value
    .split(',')
    .map((part) => {
      const [rawName, rawAmount] = part.split(':');
      const amount = Number(rawAmount);
      return { name: (rawName || '').trim(), amount };
    })
    .filter((row) => row.name && Number.isFinite(row.amount) && row.amount > 0);
}
