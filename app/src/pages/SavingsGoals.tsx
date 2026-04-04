import { useEffect, useState } from 'react';
import { getSavingsGoals, createSavingsGoal, updateSavingsGoal, deleteSavingsGoal, type SavingsGoal } from '@/api/savingsGoals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Trash2 } from 'lucide-react';

const MILESTONE_LABELS: Record<number, string> = { 25: '🥉 25%', 50: '🥈 50%', 75: '🥇 75%', 100: '🏆 100%' };

export default function SavingsGoals() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState('');
  const [target, setTarget] = useState('');
  const [targetDate, setTargetDate] = useState('');
  const [addAmount, setAddAmount] = useState<Record<number, string>>({});

  const load = () => {
    getSavingsGoals().then(setGoals).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !target) return;
    await createSavingsGoal({ name, target_amount: parseFloat(target), target_date: targetDate || undefined });
    setName(''); setTarget(''); setTargetDate('');
    load();
  };

  const handleAddSaved = async (goal: SavingsGoal) => {
    const amt = parseFloat(addAmount[goal.id] || '0');
    if (!amt || amt <= 0) return;
    await updateSavingsGoal(goal.id, { saved_amount: goal.saved_amount + amt });
    setAddAmount((p) => ({ ...p, [goal.id]: '' }));
    load();
  };

  const handleDelete = async (id: number) => {
    await deleteSavingsGoal(id);
    load();
  };

  if (loading) return <div className="p-6 text-center text-muted-foreground">Loading…</div>;

  return (
    <div className="container-financial py-8 space-y-6">
      <h1 className="text-2xl font-bold">Savings Goals</h1>

      <Card>
        <CardHeader><CardTitle>Create Goal</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="flex flex-wrap gap-3">
            <Input placeholder="Goal name" value={name} onChange={(e) => setName(e.target.value)} className="w-48" required />
            <Input type="number" placeholder="Target amount" value={target} onChange={(e) => setTarget(e.target.value)} className="w-36" min="0.01" step="0.01" required />
            <Input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className="w-40" />
            <Button type="submit">Add Goal</Button>
          </form>
        </CardContent>
      </Card>

      {goals.length === 0 && <p className="text-center text-muted-foreground">No goals yet. Create one above!</p>}

      <div className="grid gap-4 md:grid-cols-2">
        {goals.map((g) => (
          <Card key={g.id}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-base">{g.name}</CardTitle>
              <Button variant="ghost" size="icon" onClick={() => handleDelete(g.id)} aria-label={`Delete ${g.name}`}>
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm">
                <span>${g.saved_amount.toFixed(2)} / ${g.target_amount.toFixed(2)}</span>
                <span className="font-semibold">{g.progress_pct}%</span>
              </div>
              <Progress value={g.progress_pct} className="h-3" />
              {g.target_date && <p className="text-xs text-muted-foreground">Target: {g.target_date}</p>}
              <div className="flex flex-wrap gap-1">
                {[25, 50, 75, 100].map((m) => (
                  <span key={m} className={`text-xs px-2 py-0.5 rounded-full ${g.milestones.includes(m) ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'}`}>
                    {MILESTONE_LABELS[m]}
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <Input type="number" placeholder="Add savings" value={addAmount[g.id] || ''} onChange={(e) => setAddAmount((p) => ({ ...p, [g.id]: e.target.value }))} className="w-32" min="0.01" step="0.01" />
                <Button size="sm" onClick={() => handleAddSaved(g)}>Add</Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
