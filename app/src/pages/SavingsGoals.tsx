import { useState, useEffect } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Target,
  Plus,
  TrendingUp,
  Calendar,
  DollarSign,
  Trophy,
  Edit,
  Trash2,
  PlusCircle,
  MinusCircle,
} from 'lucide-react';
import {
  listSavingsGoals,
  createSavingsGoal,
  updateSavingsGoal,
  deleteSavingsGoal,
  addToSavingsGoal,
  withdrawFromSavingsGoal,
  getGoalProgress,
  listMilestones,
  createMilestone,
  deleteMilestone,
  type SavingsGoal,
  type GoalMilestone,
} from '@/api/savings-goals';

export function SavingsGoals() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingGoal, setEditingGoal] = useState<SavingsGoal | null>(null);
  const [selectedGoal, setSelectedGoal] = useState<SavingsGoal | null>(null);
  const [milestones, setMilestones] = useState<Record<number, GoalMilestone[]>>({});

  useEffect(() => {
    loadGoals();
  }, []);

  async function loadGoals() {
    try {
      setLoading(true);
      setError(null);
      const data = await listSavingsGoals();
      setGoals(data);
      
      // Load milestones for each goal
      const milestonesData: Record<number, GoalMilestone[]> = {};
      await Promise.all(
        data.map(async (goal) => {
          try {
            milestonesData[goal.id] = await listMilestones(goal.id);
          } catch (err) {
            console.error(`Failed to load milestones for goal ${goal.id}:`, err);
            milestonesData[goal.id] = [];
          }
        })
      );
      setMilestones(milestonesData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load savings goals');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateGoal(data: {
    name: string;
    description?: string;
    target_amount: number;
    current_amount?: number;
    deadline?: string;
  }) {
    try {
      await createSavingsGoal(data);
      await loadGoals();
      setShowCreateModal(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to create goal');
    }
  }

  async function handleUpdateGoal(id: number, data: Partial<SavingsGoal>) {
    try {
      await updateSavingsGoal(id, data);
      await loadGoals();
      setEditingGoal(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update goal');
    }
  }

  async function handleDeleteGoal(id: number) {
    if (!confirm('Are you sure you want to delete this savings goal?')) return;
    try {
      await deleteSavingsGoal(id);
      await loadGoals();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete goal');
    }
  }

  async function handleAddFunds(id: number, amount: number) {
    try {
      await addToSavingsGoal(id, amount);
      await loadGoals();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to add funds');
    }
  }

  async function handleWithdraw(id: number, amount: number) {
    try {
      await withdrawFromSavingsGoal(id, amount);
      await loadGoals();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to withdraw funds');
    }
  }

  async function handleCreateMilestone(goalId: number, name: string, percentage: number) {
    try {
      await createMilestone({ goal_id: goalId, name, target_percentage: percentage });
      await loadGoals();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to create milestone');
    }
  }

  async function handleDeleteMilestone(milestoneId: number) {
    try {
      await deleteMilestone(milestoneId);
      await loadGoals();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete milestone');
    }
  }

  function calculateProgress(goal: SavingsGoal): number {
    if (goal.target_amount === 0) return 0;
    return Math.min(100, (goal.current_amount / goal.target_amount) * 100);
  }

  function getDaysLeft(deadline?: string): number | null {
    if (!deadline) return null;
    const now = new Date();
    const end = new Date(deadline);
    const diff = end.getTime() - now.getTime();
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
  }

  function getStatusBadge(goal: SavingsGoal) {
    const progress = calculateProgress(goal);
    if (progress >= 100) {
      return <Badge className="bg-green-500">Completed</Badge>;
    }
    
    const daysLeft = getDaysLeft(goal.deadline);
    if (!daysLeft) {
      return <Badge className="bg-blue-500">In Progress</Badge>;
    }
    
    if (daysLeft < 0) {
      return <Badge className="bg-red-500">Overdue</Badge>;
    }
    
    // Calculate if on track
    const daysTotal = goal.deadline ? 
      Math.ceil((new Date(goal.deadline).getTime() - new Date(goal.created_at).getTime()) / (1000 * 60 * 60 * 24)) : 
      0;
    const expectedProgress = daysTotal > 0 ? ((daysTotal - daysLeft) / daysTotal) * 100 : 0;
    
    if (progress >= expectedProgress) {
      return <Badge className="bg-green-500">On Track</Badge>;
    } else {
      return <Badge className="bg-yellow-500">Behind Schedule</Badge>;
    }
  }

  const totalSaved = goals.reduce((sum, g) => sum + g.current_amount, 0);
  const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0);
  const overallProgress = totalTarget > 0 ? (totalSaved / totalTarget) * 100 : 0;

  if (loading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading savings goals...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold">Savings Goals</h1>
          <p className="text-muted-foreground mt-2">Track your savings progress and achieve your financial milestones</p>
        </div>
        <Button onClick={() => setShowCreateModal(true)} size="lg">
          <Plus className="mr-2 h-5 w-5" />
          New Goal
        </Button>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive text-destructive px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Overview Stats */}
      <div className="grid gap-6 md:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Target className="h-5 w-5" />
              Total Goals
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-4xl font-bold">{goals.length}</p>
            <p className="text-sm text-muted-foreground mt-1">Active savings goals</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <DollarSign className="h-5 w-5" />
              Total Saved
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-4xl font-bold">${totalSaved.toFixed(2)}</p>
            <p className="text-sm text-muted-foreground mt-1">
              of ${totalTarget.toFixed(2)} target
            </p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Overall Progress
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-4xl font-bold">{overallProgress.toFixed(1)}%</p>
            <Progress value={overallProgress} className="mt-2" />
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals List */}
      {goals.length === 0 ? (
        <FinancialCard>
          <FinancialCardContent className="py-12 text-center">
            <Target className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-semibold mb-2">No savings goals yet</p>
            <p className="text-muted-foreground mb-4">
              Create your first savings goal to start tracking your financial progress
            </p>
            <Button onClick={() => setShowCreateModal(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Create Your First Goal
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {goals.map((goal) => {
            const progress = calculateProgress(goal);
            const daysLeft = getDaysLeft(goal.deadline);
            const goalMilestones = milestones[goal.id] || [];
            
            return (
              <FinancialCard key={goal.id} className="hover:shadow-lg transition-shadow">
                <FinancialCardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <FinancialCardTitle className="flex items-center gap-2">
                        <Target className="h-5 w-5" />
                        {goal.name}
                      </FinancialCardTitle>
                      {goal.description && (
                        <FinancialCardDescription>{goal.description}</FinancialCardDescription>
                      )}
                    </div>
                    {getStatusBadge(goal)}
                  </div>
                </FinancialCardHeader>

                <FinancialCardContent className="space-y-4">
                  {/* Progress Bar */}
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="font-semibold">${goal.current_amount.toFixed(2)}</span>
                      <span className="text-muted-foreground">${goal.target_amount.toFixed(2)}</span>
                    </div>
                    <Progress value={progress} className="h-3" />
                    <p className="text-xs text-center text-muted-foreground mt-1">
                      {progress.toFixed(1)}% Complete
                    </p>
                  </div>

                  {/* Deadline */}
                  {goal.deadline && (
                    <div className="flex items-center gap-2 text-sm">
                      <Calendar className="h-4 w-4 text-muted-foreground" />
                      <span>
                        {daysLeft !== null && daysLeft >= 0
                          ? `${daysLeft} days left`
                          : daysLeft !== null && daysLeft < 0
                          ? `${Math.abs(daysLeft)} days overdue`
                          : new Date(goal.deadline).toLocaleDateString()}
                      </span>
                    </div>
                  )}

                  {/* Milestones */}
                  {goalMilestones.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-sm font-semibold flex items-center gap-2">
                        <Trophy className="h-4 w-4" />
                        Milestones
                      </p>
                      <div className="space-y-1">
                        {goalMilestones.map((milestone) => {
                          const isAchieved = progress >= milestone.target_percentage;
                          return (
                            <div
                              key={milestone.id}
                              className={`flex items-center justify-between text-xs px-2 py-1 rounded ${
                                isAchieved ? 'bg-green-100 text-green-800' : 'bg-gray-100'
                              }`}
                            >
                              <span>{milestone.name}</span>
                              <span className="font-semibold">{milestone.target_percentage}%</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </FinancialCardContent>

                <FinancialCardFooter className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const amount = prompt('Enter amount to add:');
                      if (amount) handleAddFunds(goal.id, parseFloat(amount));
                    }}
                  >
                    <PlusCircle className="h-4 w-4 mr-1" />
                    Add
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const amount = prompt('Enter amount to withdraw:');
                      if (amount) handleWithdraw(goal.id, parseFloat(amount));
                    }}
                  >
                    <MinusCircle className="h-4 w-4 mr-1" />
                    Withdraw
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setEditingGoal(goal)}
                  >
                    <Edit className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDeleteGoal(goal.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </FinancialCardFooter>
              </FinancialCard>
            );
          })}
        </div>
      )}

      {/* Create Modal (simplified placeholder) */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background p-6 rounded-lg shadow-xl max-w-md w-full">
            <h2 className="text-2xl font-bold mb-4">Create Savings Goal</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.currentTarget);
                handleCreateGoal({
                  name: formData.get('name') as string,
                  description: formData.get('description') as string,
                  target_amount: parseFloat(formData.get('target_amount') as string),
                  current_amount: parseFloat(formData.get('current_amount') as string) || 0,
                  deadline: formData.get('deadline') as string || undefined,
                });
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-sm font-medium mb-1">Goal Name *</label>
                <input
                  type="text"
                  name="name"
                  required
                  className="w-full border rounded px-3 py-2"
                  placeholder="Emergency Fund"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Description</label>
                <textarea
                  name="description"
                  className="w-full border rounded px-3 py-2"
                  placeholder="Save for 6 months of expenses"
                  rows={2}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Target Amount *</label>
                <input
                  type="number"
                  name="target_amount"
                  required
                  step="0.01"
                  min="0"
                  className="w-full border rounded px-3 py-2"
                  placeholder="10000"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Current Amount</label>
                <input
                  type="number"
                  name="current_amount"
                  step="0.01"
                  min="0"
                  className="w-full border rounded px-3 py-2"
                  placeholder="0"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Deadline</label>
                <input
                  type="date"
                  name="deadline"
                  className="w-full border rounded px-3 py-2"
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button type="button" variant="outline" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </Button>
                <Button type="submit">Create Goal</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
