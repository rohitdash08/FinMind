import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import {
  listGoals,
  createGoal,
  updateGoal,
  deleteGoal,
  getMilestones,
  type SavingsGoal,
  type SavingsMilestone,
} from '@/api/savings';
import { Target, Plus, Trash2, PiggyBank, Trophy } from 'lucide-react';

export default function Savings() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [currency, setCurrency] = useState('INR');
  const [deadline, setDeadline] = useState('');
  const [addFundsId, setAddFundsId] = useState<number | null>(null);
  const [fundsAmount, setFundsAmount] = useState('');
  const [milestonesMap, setMilestonesMap] = useState<Record<number, SavingsMilestone[]>>({});
  const [expandedGoal, setExpandedGoal] = useState<number | null>(null);
  const { toast } = useToast();

  const fetchGoals = async () => {
    try {
      const data = await listGoals();
      setGoals(data);
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void fetchGoals(); }, []);

  const handleCreate = async () => {
    if (!name.trim() || !targetAmount) return;
    try {
      await createGoal({
        name: name.trim(),
        target_amount: parseFloat(targetAmount),
        currency,
        deadline: deadline || undefined,
      });
      setName(''); setTargetAmount(''); setDeadline(''); setShowForm(false);
      toast({ title: 'Goal created!' });
      await fetchGoals();
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const handleAddFunds = async (goalId: number) => {
    if (!fundsAmount || parseFloat(fundsAmount) <= 0) return;
    try {
      await updateGoal(goalId, { add_funds: parseFloat(fundsAmount) });
      setAddFundsId(null); setFundsAmount('');
      toast({ title: 'Funds added!' });
      await fetchGoals();
      if (expandedGoal === goalId) await fetchMilestones(goalId);
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteGoal(id);
      toast({ title: 'Goal deleted' });
      await fetchGoals();
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    }
  };

  const fetchMilestones = async (goalId: number) => {
    try {
      const ms = await getMilestones(goalId);
      setMilestonesMap(prev => ({ ...prev, [goalId]: ms }));
    } catch { /* ignore */ }
  };

  const toggleMilestones = async (goalId: number) => {
    if (expandedGoal === goalId) {
      setExpandedGoal(null);
    } else {
      setExpandedGoal(goalId);
      if (!milestonesMap[goalId]) await fetchMilestones(goalId);
    }
  };

  if (loading) return <div className="p-8 text-center text-muted-foreground">Loading…</div>;

  return (
    <div className="container-financial py-8 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <PiggyBank className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">Savings Goals</h1>
        </div>
        <Button onClick={() => setShowForm(!showForm)} variant="hero" size="sm">
          <Plus className="h-4 w-4 mr-1" /> New Goal
        </Button>
      </div>

      {showForm && (
        <div className="rounded-xl border bg-card p-4 space-y-3">
          <Input placeholder="Goal name" value={name} onChange={e => setName(e.target.value)} />
          <div className="flex gap-2">
            <Input type="number" placeholder="Target amount" value={targetAmount} onChange={e => setTargetAmount(e.target.value)} />
            <Input placeholder="Currency" value={currency} onChange={e => setCurrency(e.target.value)} className="w-24" />
          </div>
          <Input type="date" placeholder="Deadline (optional)" value={deadline} onChange={e => setDeadline(e.target.value)} />
          <Button onClick={handleCreate} size="sm">Create</Button>
        </div>
      )}

      {goals.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Target className="h-12 w-12 mx-auto mb-3 opacity-40" />
          <p>No savings goals yet. Create one to start tracking!</p>
        </div>
      ) : (
        <div className="space-y-4">
          {goals.map(goal => (
            <div key={goal.id} className="rounded-xl border bg-card p-4 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-lg">{goal.name}</h3>
                  <p className="text-sm text-muted-foreground">
                    {goal.currency} {goal.current_amount.toLocaleString()} / {goal.target_amount.toLocaleString()}
                    {goal.deadline && <span className="ml-2">· Due {goal.deadline}</span>}
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => setAddFundsId(addFundsId === goal.id ? null : goal.id)}>
                    <Plus className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => toggleMilestones(goal.id)}>
                    <Trophy className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(goal.id)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-muted rounded-full h-3">
                <div
                  className="bg-primary h-3 rounded-full transition-all"
                  style={{ width: `${Math.min(goal.progress_pct, 100)}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground text-right">{goal.progress_pct}%</p>

              {/* Add funds form */}
              {addFundsId === goal.id && (
                <div className="flex gap-2">
                  <Input type="number" placeholder="Amount" value={fundsAmount} onChange={e => setFundsAmount(e.target.value)} className="w-40" />
                  <Button size="sm" onClick={() => handleAddFunds(goal.id)}>Add Funds</Button>
                </div>
              )}

              {/* Milestones */}
              {expandedGoal === goal.id && milestonesMap[goal.id] && (
                <div className="space-y-1 pt-2 border-t">
                  <p className="text-xs font-semibold text-muted-foreground mb-1">Milestones</p>
                  {milestonesMap[goal.id].map(ms => (
                    <div key={ms.id} className="flex items-center gap-2 text-sm">
                      <span className={`inline-block h-2 w-2 rounded-full ${ms.reached_at ? 'bg-green-500' : 'bg-muted-foreground/30'}`} />
                      <span className={ms.reached_at ? 'text-foreground' : 'text-muted-foreground'}>
                        {ms.name} — {goal.currency} {ms.amount.toLocaleString()}
                      </span>
                      {ms.reached_at && <span className="text-xs text-green-600">✓</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
