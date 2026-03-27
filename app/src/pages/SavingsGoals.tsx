import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import { Target, Plus, TrendingUp, Trophy, Trash2 } from 'lucide-react';
import {
  listSavingsGoals,
  createSavingsGoal,
  contributeSavingsGoal,
  deleteSavingsGoal,
  type SavingsGoal,
} from '@/api/savings_goals';

export default function SavingsGoals() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [contributeId, setContributeId] = useState<number | null>(null);
  const [contributeAmount, setContributeAmount] = useState('');
  const [form, setForm] = useState({ name: '', target_amount: '', currency: '', deadline: '' });
  const { toast } = useToast();

  const fetchGoals = async () => {
    try {
      const data = await listSavingsGoals();
      setGoals(data);
    } catch {
      toast({ title: 'Error', description: 'Failed to load savings goals', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchGoals(); }, []);

  const handleCreate = async () => {
    if (!form.name || !form.target_amount) {
      toast({ title: 'Error', description: 'Name and target amount are required', variant: 'destructive' });
      return;
    }
    try {
      await createSavingsGoal({
        name: form.name,
        target_amount: parseFloat(form.target_amount),
        currency: form.currency || undefined,
        deadline: form.deadline || null,
      });
      setForm({ name: '', target_amount: '', currency: '', deadline: '' });
      setShowCreate(false);
      toast({ title: 'Success', description: 'Savings goal created!' });
      fetchGoals();
    } catch {
      toast({ title: 'Error', description: 'Failed to create goal', variant: 'destructive' });
    }
  };

  const handleContribute = async (goalId: number) => {
    const amount = parseFloat(contributeAmount);
    if (!amount || amount <= 0) {
      toast({ title: 'Error', description: 'Enter a valid amount', variant: 'destructive' });
      return;
    }
    try {
      await contributeSavingsGoal(goalId, amount);
      setContributeId(null);
      setContributeAmount('');
      toast({ title: 'Success', description: 'Contribution added!' });
      fetchGoals();
    } catch {
      toast({ title: 'Error', description: 'Failed to contribute', variant: 'destructive' });
    }
  };

  const handleDelete = async (goalId: number) => {
    try {
      await deleteSavingsGoal(goalId);
      toast({ title: 'Deleted', description: 'Goal removed' });
      fetchGoals();
    } catch {
      toast({ title: 'Error', description: 'Failed to delete', variant: 'destructive' });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Target className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold">Savings Goals</h1>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus className="h-4 w-4 mr-2" />
          New Goal
        </Button>
      </div>

      {showCreate && (
        <div className="border rounded-lg p-4 space-y-3 bg-card">
          <h3 className="font-semibold">Create New Goal</h3>
          <div className="grid grid-cols-2 gap-3">
            <Input
              placeholder="Goal name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <Input
              type="number"
              placeholder="Target amount"
              value={form.target_amount}
              onChange={(e) => setForm({ ...form, target_amount: e.target.value })}
            />
            <Input
              placeholder="Currency (e.g. USD)"
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
            />
            <Input
              type="date"
              placeholder="Deadline"
              value={form.deadline}
              onChange={(e) => setForm({ ...form, deadline: e.target.value })}
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={handleCreate}>Create</Button>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {goals.length === 0 && !showCreate ? (
        <div className="text-center py-12 text-muted-foreground">
          <Target className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p className="text-lg">No savings goals yet</p>
          <p className="text-sm">Create your first goal to start tracking your savings.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {goals.map((goal) => (
            <div key={goal.id} className="border rounded-lg p-4 space-y-3 bg-card">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-lg">{goal.name}</h3>
                  <p className="text-sm text-muted-foreground">
                    {goal.currency} {goal.current_amount.toLocaleString()} / {goal.target_amount.toLocaleString()}
                    {goal.deadline && ` · Due ${goal.deadline}`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setContributeId(contributeId === goal.id ? null : goal.id)}
                  >
                    <TrendingUp className="h-4 w-4 mr-1" />
                    Contribute
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => handleDelete(goal.id)}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-secondary rounded-full h-3">
                <div
                  className="bg-primary h-3 rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(goal.progress, 100)}%` }}
                />
              </div>
              <p className="text-sm font-medium">{goal.progress}% complete</p>

              {/* Milestones */}
              <div className="flex gap-2">
                {goal.milestones.map((m) => (
                  <div
                    key={m.id}
                    className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
                      m.reached
                        ? 'bg-primary/20 text-primary'
                        : 'bg-secondary text-muted-foreground'
                    }`}
                  >
                    <Trophy className="h-3 w-3" />
                    {m.percent}%
                  </div>
                ))}
              </div>

              {/* Contribute form */}
              {contributeId === goal.id && (
                <div className="flex gap-2 pt-2 border-t">
                  <Input
                    type="number"
                    placeholder="Amount"
                    value={contributeAmount}
                    onChange={(e) => setContributeAmount(e.target.value)}
                    className="max-w-[200px]"
                  />
                  <Button size="sm" onClick={() => handleContribute(goal.id)}>Add</Button>
                  <Button size="sm" variant="outline" onClick={() => { setContributeId(null); setContributeAmount(''); }}>
                    Cancel
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
