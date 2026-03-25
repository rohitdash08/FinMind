import { useState, useEffect, useCallback } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Target, Plus, TrendingUp, Calendar, CheckCircle2, XCircle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { listGoals, createGoal, getProgress, addContribution, cancelGoal, type SavingsGoal, type GoalProgress } from '@/api/goals';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { formatMoney } from '@/lib/currency';

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'bg-blue-100 text-blue-800',
  COMPLETED: 'bg-green-100 text-green-800',
  CANCELLED: 'bg-gray-100 text-gray-800',
};

export default function Goals() {
  const { toast } = useToast();
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [progressMap, setProgressMap] = useState<Record<number, GoalProgress>>({});
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [contributeGoalId, setContributeGoalId] = useState<number | null>(null);
  const [newGoal, setNewGoal] = useState({ name: '', target_amount: '', currency: 'INR', deadline: '' });
  const [contributeAmount, setContributeAmount] = useState('');
  const [contributeNote, setContributeNote] = useState('');

  const loadData = useCallback(async () => {
    try {
      const g = await listGoals();
      setGoals(g);
      const progEntries = await Promise.all(
        g.filter(gl => gl.status === 'ACTIVE').map(async gl => {
          try {
            const p = await getProgress(gl.id);
            return [gl.id, p] as [number, GoalProgress];
          } catch { return null; }
        })
      );
      const map: Record<number, GoalProgress> = {};
      progEntries.forEach(e => { if (e) map[e[0]] = e[1]; });
      setProgressMap(map);
    } catch (e: unknown) {
      toast({ title: 'Error', description: e instanceof Error ? e.message : 'Failed to load goals', variant: 'destructive' });
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    try {
      await createGoal({
        name: newGoal.name,
        target_amount: parseFloat(newGoal.target_amount),
        currency: newGoal.currency,
        deadline: newGoal.deadline || undefined,
      });
      toast({ title: 'Goal created' });
      setCreateOpen(false);
      setNewGoal({ name: '', target_amount: '', currency: 'INR', deadline: '' });
      loadData();
    } catch (e: unknown) {
      toast({ title: 'Error', description: e instanceof Error ? e.message : 'Failed', variant: 'destructive' });
    }
  };

  const handleContribute = async () => {
    if (!contributeGoalId) return;
    try {
      await addContribution(contributeGoalId, parseFloat(contributeAmount), contributeNote || undefined);
      toast({ title: 'Contribution added' });
      setContributeGoalId(null);
      setContributeAmount('');
      setContributeNote('');
      loadData();
    } catch (e: unknown) {
      toast({ title: 'Error', description: e instanceof Error ? e.message : 'Failed', variant: 'destructive' });
    }
  };

  const handleCancel = async (id: number) => {
    try {
      await cancelGoal(id);
      toast({ title: 'Goal cancelled' });
      loadData();
    } catch (e: unknown) {
      toast({ title: 'Error', description: e instanceof Error ? e.message : 'Failed', variant: 'destructive' });
    }
  };

  if (loading) return <div className="flex justify-center p-8">Loading...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Savings Goals</h1>
          <p className="text-muted-foreground">Track your savings goals and milestones</p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button><Plus className="mr-2 h-4 w-4" /> New Goal</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Savings Goal</DialogTitle>
              <DialogDescription>Set a target and track your progress.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <input className="w-full rounded-md border px-3 py-2" placeholder="Goal name (e.g. Emergency Fund)" value={newGoal.name} onChange={e => setNewGoal(p => ({ ...p, name: e.target.value }))} />
              <input className="w-full rounded-md border px-3 py-2" type="number" placeholder="Target amount" value={newGoal.target_amount} onChange={e => setNewGoal(p => ({ ...p, target_amount: e.target.value }))} />
              <input className="w-full rounded-md border px-3 py-2" placeholder="Currency" value={newGoal.currency} onChange={e => setNewGoal(p => ({ ...p, currency: e.target.value }))} />
              <input className="w-full rounded-md border px-3 py-2" type="date" placeholder="Deadline (optional)" value={newGoal.deadline} onChange={e => setNewGoal(p => ({ ...p, deadline: e.target.value }))} />
            </div>
            <DialogFooter>
              <Button onClick={handleCreate} disabled={!newGoal.name || !newGoal.target_amount}>Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Contribute Dialog */}
      <Dialog open={contributeGoalId !== null} onOpenChange={open => { if (!open) setContributeGoalId(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Contribution</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <input className="w-full rounded-md border px-3 py-2" type="number" placeholder="Amount" value={contributeAmount} onChange={e => setContributeAmount(e.target.value)} />
            <input className="w-full rounded-md border px-3 py-2" placeholder="Note (optional)" value={contributeNote} onChange={e => setContributeNote(e.target.value)} />
          </div>
          <DialogFooter>
            <Button onClick={handleContribute} disabled={!contributeAmount}>Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {goals.length === 0 ? (
        <FinancialCard>
          <FinancialCardContent className="flex flex-col items-center justify-center py-12">
            <Target className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground">No goals yet. Create your first savings goal!</p>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {goals.map(goal => {
            const progress = progressMap[goal.id];
            const pct = progress?.progress_pct ?? (goal.target_amount > 0 ? (goal.current_amount / goal.target_amount) * 100 : 0);

            return (
              <FinancialCard key={goal.id}>
                <FinancialCardHeader className="flex flex-row items-center justify-between pb-2">
                  <div className="flex items-center gap-2">
                    {goal.status === 'COMPLETED' ? <CheckCircle2 className="h-5 w-5 text-green-600" /> : <Target className="h-5 w-5 text-muted-foreground" />}
                    <FinancialCardTitle className="text-base">{goal.name}</FinancialCardTitle>
                  </div>
                  <Badge className={STATUS_COLORS[goal.status] || ''}>{goal.status}</Badge>
                </FinancialCardHeader>
                <FinancialCardContent className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span>{formatMoney(goal.current_amount, goal.currency)}</span>
                    <span className="text-muted-foreground">of {formatMoney(goal.target_amount, goal.currency)}</span>
                  </div>
                  {/* Progress bar */}
                  <div className="w-full bg-gray-200 rounded-full h-3">
                    <div className="bg-primary h-3 rounded-full transition-all" style={{ width: `${Math.min(pct, 100)}%` }} />
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{pct.toFixed(1)}%</span>
                    {goal.deadline && (
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {goal.deadline}
                      </span>
                    )}
                  </div>
                  {/* Milestones */}
                  {progress?.milestones && (
                    <div className="flex gap-2">
                      {progress.milestones.map(m => (
                        <div key={m.pct} className={`text-xs px-2 py-0.5 rounded ${m.reached ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                          {m.pct}%
                        </div>
                      ))}
                    </div>
                  )}
                  {progress?.daily_savings_needed && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <TrendingUp className="h-3 w-3" />
                      Save {formatMoney(progress.daily_savings_needed, goal.currency)}/day to reach your goal
                    </p>
                  )}
                  {goal.status === 'ACTIVE' && (
                    <div className="flex gap-2 pt-2">
                      <Button size="sm" onClick={() => setContributeGoalId(goal.id)}>
                        <Plus className="mr-1 h-3 w-3" /> Contribute
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => handleCancel(goal.id)}>
                        <XCircle className="mr-1 h-3 w-3" /> Cancel
                      </Button>
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
