import { useState, useEffect, useCallback } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardHeader, FinancialCardTitle, FinancialCardDescription } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dailog';
import { Target, Plus, Coins, Trophy, Trash2, Pencil, Milestone } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { formatMoney } from '@/lib/currency';
import {
  listGoals,
  createGoal,
  updateGoal,
  deleteGoal,
  contributeToGoal,
  listMilestones,
  createMilestone,
  deleteMilestone,
  type Goal,
  type GoalMilestone,
} from '@/api/goals';

export function Goals() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editGoal, setEditGoal] = useState<Goal | null>(null);
  const [contributeGoal, setContributeGoal] = useState<Goal | null>(null);
  const [contributeAmount, setContributeAmount] = useState('');
  const [milestonesGoal, setMilestonesGoal] = useState<Goal | null>(null);
  const [milestones, setMilestones] = useState<GoalMilestone[]>([]);
  const [newMilestoneLabel, setNewMilestoneLabel] = useState('');
  const [newMilestoneAmount, setNewMilestoneAmount] = useState('');
  const { toast } = useToast();

  const [formTitle, setFormTitle] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formTarget, setFormTarget] = useState('');
  const [formDeadline, setFormDeadline] = useState('');
  const [formIcon, setFormIcon] = useState('');

  const fetchGoals = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listGoals();
      setGoals(data);
    } catch (err) {
      toast({ title: 'Error', description: String(err), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchGoals();
  }, [fetchGoals]);

  const resetForm = () => {
    setFormTitle('');
    setFormDescription('');
    setFormTarget('');
    setFormDeadline('');
    setFormIcon('');
  };

  const handleCreate = async () => {
    try {
      await createGoal({
        title: formTitle,
        description: formDescription || null,
        target_amount: parseFloat(formTarget),
        deadline: formDeadline || null,
        icon: formIcon || null,
      });
      toast({ title: 'Goal created' });
      setCreateOpen(false);
      resetForm();
      fetchGoals();
    } catch (err) {
      toast({ title: 'Error', description: String(err), variant: 'destructive' });
    }
  };

  const handleEdit = async () => {
    if (!editGoal) return;
    try {
      await updateGoal(editGoal.id, {
        title: formTitle,
        description: formDescription || null,
        target_amount: parseFloat(formTarget),
        deadline: formDeadline || null,
        icon: formIcon || null,
      });
      toast({ title: 'Goal updated' });
      setEditGoal(null);
      resetForm();
      fetchGoals();
    } catch (err) {
      toast({ title: 'Error', description: String(err), variant: 'destructive' });
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteGoal(id);
      toast({ title: 'Goal deleted' });
      fetchGoals();
    } catch (err) {
      toast({ title: 'Error', description: String(err), variant: 'destructive' });
    }
  };

  const handleContribute = async () => {
    if (!contributeGoal) return;
    try {
      await contributeToGoal(contributeGoal.id, parseFloat(contributeAmount));
      toast({ title: 'Contribution added' });
      setContributeGoal(null);
      setContributeAmount('');
      fetchGoals();
    } catch (err) {
      toast({ title: 'Error', description: String(err), variant: 'destructive' });
    }
  };

  const openEdit = (g: Goal) => {
    setEditGoal(g);
    setFormTitle(g.title);
    setFormDescription(g.description || '');
    setFormTarget(String(g.target_amount));
    setFormDeadline(g.deadline || '');
    setFormIcon(g.icon || '');
  };

  const fetchMilestones = async (g: Goal) => {
    try {
      const data = await listMilestones(g.id);
      setMilestones(data);
      setMilestonesGoal(g);
    } catch (err) {
      toast({ title: 'Error', description: String(err), variant: 'destructive' });
    }
  };

  const handleCreateMilestone = async () => {
    if (!milestonesGoal) return;
    try {
      await createMilestone(milestonesGoal.id, {
        label: newMilestoneLabel,
        target_amount: parseFloat(newMilestoneAmount),
      });
      toast({ title: 'Milestone created' });
      setNewMilestoneLabel('');
      setNewMilestoneAmount('');
      fetchMilestones(milestonesGoal);
    } catch (err) {
      toast({ title: 'Error', description: String(err), variant: 'destructive' });
    }
  };

  const handleDeleteMilestone = async (mid: number) => {
    if (!milestonesGoal) return;
    try {
      await deleteMilestone(milestonesGoal.id, mid);
      toast({ title: 'Milestone deleted' });
      fetchMilestones(milestonesGoal);
    } catch (err) {
      toast({ title: 'Error', description: String(err), variant: 'destructive' });
    }
  };

  const getProgress = (g: Goal) => {
    if (g.target_amount <= 0) return 0;
    return Math.min(100, (g.current_amount / g.target_amount) * 100);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Target className="h-6 w-6 text-primary" />
            Savings Goals
          </h1>
          <p className="text-muted-foreground">Track your savings goals and milestones</p>
        </div>
        <Dialog open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) resetForm(); }}>
          <DialogTrigger asChild>
            <Button variant="hero">
              <Plus className="h-4 w-4 mr-2" />
              New Goal
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Savings Goal</DialogTitle>
              <DialogDescription>Set a target and start saving towards it.</DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium">Title</label>
                <input className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formTitle} onChange={(e) => setFormTitle(e.target.value)} placeholder="e.g. Emergency Fund" />
              </div>
              <div>
                <label className="text-sm font-medium">Description</label>
                <input className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formDescription} onChange={(e) => setFormDescription(e.target.value)} placeholder="Optional description" />
              </div>
              <div>
                <label className="text-sm font-medium">Target Amount</label>
                <input type="number" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formTarget} onChange={(e) => setFormTarget(e.target.value)} placeholder="50000" />
              </div>
              <div>
                <label className="text-sm font-medium">Deadline (optional)</label>
                <input type="date" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formDeadline} onChange={(e) => setFormDeadline(e.target.value)} />
              </div>
              <div>
                <label className="text-sm font-medium">Icon (optional)</label>
                <input className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formIcon} onChange={(e) => setFormIcon(e.target.value)} placeholder="e.g. piggy-bank" />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => { setCreateOpen(false); resetForm(); }}>Cancel</Button>
              <Button variant="hero" onClick={handleCreate} disabled={!formTitle || !formTarget}>Create Goal</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
        </div>
      )}

      {!loading && goals.length === 0 && (
        <FinancialCard>
          <FinancialCardContent className="flex flex-col items-center justify-center py-12">
            <Target className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">No savings goals yet</h3>
            <p className="text-muted-foreground text-sm mt-1">Create your first savings goal to start tracking progress.</p>
          </FinancialCardContent>
        </FinancialCard>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {goals.map((g) => {
          const pct = getProgress(g);
          const isComplete = pct >= 100;
          return (
            <FinancialCard key={g.id} className={isComplete ? 'border-green-300 bg-green-50/50' : ''}>
              <FinancialCardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    {g.icon ? <span className="text-xl">{g.icon}</span> : <Target className="h-5 w-5 text-primary" />}
                    <FinancialCardTitle className="text-base">{g.title}</FinancialCardTitle>
                  </div>
                  {isComplete && <Trophy className="h-5 w-5 text-green-600" />}
                </div>
                {g.description && <FinancialCardDescription>{g.description}</FinancialCardDescription>}
              </FinancialCardHeader>
              <FinancialCardContent className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Progress</span>
                  <span className="font-medium">{formatMoney(g.current_amount, g.currency)} / {formatMoney(g.target_amount, g.currency)}</span>
                </div>
                <Progress value={pct} className="h-2" />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{pct.toFixed(1)}%</span>
                  {g.deadline && <span>Due: {g.deadline}</span>}
                </div>
                <div className="flex gap-2 pt-1">
                  <Button size="sm" variant="outline" onClick={() => { setContributeGoal(g); setContributeAmount(''); }}>
                    <Coins className="h-3.5 w-3.5 mr-1" />
                    Contribute
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => openEdit(g)}>
                    <Pencil className="h-3.5 w-3.5 mr-1" />
                    Edit
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => fetchMilestones(g)}>
                    <Milestone className="h-3.5 w-3.5 mr-1" />
                    Milestones
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete Goal</AlertDialogTitle>
                        <AlertDialogDescription>Are you sure you want to delete &quot;{g.title}&quot;?</AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => handleDelete(g.id)}>Delete</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          );
        })}
      </div>

      <Dialog open={!!contributeGoal} onOpenChange={(open) => { if (!open) setContributeGoal(null); setContributeAmount(''); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Contribute to Goal</DialogTitle>
            <DialogDescription>Add savings to &quot;{contributeGoal?.title}&quot;</DialogDescription>
          </DialogHeader>
          <div>
            <label className="text-sm font-medium">Amount</label>
            <input type="number" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={contributeAmount} onChange={(e) => setContributeAmount(e.target.value)} placeholder="1000" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setContributeGoal(null); setContributeAmount(''); }}>Cancel</Button>
            <Button variant="hero" onClick={handleContribute} disabled={!contributeAmount || parseFloat(contributeAmount) <= 0}>Add Contribution</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editGoal} onOpenChange={(open) => { if (!open) { setEditGoal(null); resetForm(); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Goal</DialogTitle>
            <DialogDescription>Update your savings goal details.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium">Title</label>
              <input className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formTitle} onChange={(e) => setFormTitle(e.target.value)} />
            </div>
            <div>
              <label className="text-sm font-medium">Description</label>
              <input className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formDescription} onChange={(e) => setFormDescription(e.target.value)} />
            </div>
            <div>
              <label className="text-sm font-medium">Target Amount</label>
              <input type="number" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formTarget} onChange={(e) => setFormTarget(e.target.value)} />
            </div>
            <div>
              <label className="text-sm font-medium">Deadline</label>
              <input type="date" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" value={formDeadline} onChange={(e) => setFormDeadline(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditGoal(null); resetForm(); }}>Cancel</Button>
            <Button variant="hero" onClick={handleEdit} disabled={!formTitle || !formTarget}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!milestonesGoal} onOpenChange={(open) => { if (!open) { setMilestonesGoal(null); setMilestones([]); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Milestones for &quot;{milestonesGoal?.title}&quot;</DialogTitle>
            <DialogDescription>Track progress towards your goal with milestones.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 max-h-60 overflow-y-auto">
            {milestones.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-4">No milestones yet. Create one below.</p>
            )}
            {milestones.map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                <div className="flex items-center gap-2">
                  <Badge variant={m.reached ? 'default' : 'secondary'}>{m.reached ? 'Reached' : 'Pending'}</Badge>
                  <span className="text-sm font-medium">{m.label}</span>
                  <span className="text-xs text-muted-foreground">{formatMoney(m.target_amount, milestonesGoal?.currency)}</span>
                </div>
                <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => handleDeleteMilestone(m.id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
          <div className="border-t border-border pt-3 space-y-2">
            <p className="text-sm font-medium">Add Milestone</p>
            <div className="flex gap-2">
              <input className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm" value={newMilestoneLabel} onChange={(e) => setNewMilestoneLabel(e.target.value)} placeholder="Label" />
              <input type="number" className="w-28 rounded-lg border border-border bg-background px-3 py-2 text-sm" value={newMilestoneAmount} onChange={(e) => setNewMilestoneAmount(e.target.value)} placeholder="Amount" />
              <Button size="sm" variant="hero" onClick={handleCreateMilestone} disabled={!newMilestoneLabel || !newMilestoneAmount}>Add</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
