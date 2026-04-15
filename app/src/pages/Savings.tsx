import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from "@/components/ui/financial-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Target,
  Plus,
  PiggyBank,
  TrendingUp,
  CheckCircle2,
  Trash2,
  Circle,
  DollarSign,
  Calendar,
} from "lucide-react";
import { savings, SavingsGoal, SavingsMilestone } from "@/api/savings";

const statusConfig = {
  ACTIVE: { label: "Active", variant: "default" as const, className: "bg-blue-500" },
  COMPLETED: { label: "Completed", variant: "success" as const, className: "bg-green-500" },
  PAUSED: { label: "Paused", variant: "secondary" as const, className: "bg-gray-400" },
};

function ProgressBar({
  value,
  max,
  color = "bg-accent",
}: {
  value: number;
  max: number;
  color?: string;
}) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="chart-track">
      <div className={color} style={{ width: `${pct}%` }} />
    </div>
  );
}

function GoalCard({
  goal,
  onSelect,
  onDelete,
}: {
  goal: SavingsGoal;
  onSelect: (g: SavingsGoal) => void;
  onDelete: (id: number) => void;
}) {
  const pct = (goal.current_amount / goal.target_amount) * 100;
  const cfg = statusConfig[goal.status as keyof typeof statusConfig];
  const remaining = goal.target_amount - goal.current_amount;

  return (
    <div className="interactive-row p-4 rounded-xl border border-border bg-card hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <PiggyBank className="w-4 h-4 text-accent" />
          <span className="font-medium text-foreground">{goal.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium text-white ${cfg.className}`}>
            {cfg.label}
          </span>
          {goal.status !== "COMPLETED" && (
            <button
              onClick={() => onDelete(goal.id)}
              className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
              aria-label="Delete goal"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2 mb-3">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">
            ${goal.current_amount.toLocaleString()} / ${goal.target_amount.toLocaleString()}
          </span>
          <span className="font-semibold text-foreground">{pct.toFixed(0)}%</span>
        </div>
        <ProgressBar value={goal.current_amount} max={goal.target_amount} color="chart-fill-success" />
        {remaining > 0 && goal.deadline && (
          <p className="text-xs text-muted-foreground">
            ${remaining.toLocaleString()} left · Due {goal.deadline}
          </p>
        )}
      </div>

      <div className="flex gap-2">
        <Button variant="financial" size="sm" className="flex-1" onClick={() => onSelect(goal)}>
          View / Contribute
        </Button>
      </div>
    </div>
  );
}

function CreateGoalDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [deadline, setDeadline] = useState("");

  const create = useMutation({
    mutationFn: (data: Parameters<typeof savings.create>[0]) => savings.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["savings-goals"] });
      setName("");
      setTargetAmount("");
      setDeadline("");
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !targetAmount) return;
    create.mutate({
      name,
      target_amount: parseFloat(targetAmount),
      currency,
      deadline: deadline || undefined,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Savings Goal</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label>Goal Name</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Emergency Fund, Vacation"
              className="mt-1"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Target Amount</Label>
              <Input
                type="number"
                value={targetAmount}
                onChange={(e) => setTargetAmount(e.target.value)}
                placeholder="10000"
                className="mt-1"
                min="1"
                required
              />
            </div>
            <div>
              <Label>Currency</Label>
              <Input
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                placeholder="USD"
                className="mt-1"
              />
            </div>
          </div>
          <div>
            <Label>Target Date (optional)</Label>
            <Input
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="mt-1"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="financial" disabled={create.isPending}>
              {create.isPending ? "Creating..." : "Create Goal"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ContributeDialog({
  goal,
  open,
  onClose,
}: {
  goal: SavingsGoal | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState("");

  const contribute = useMutation({
    mutationFn: (amount: number) => savings.contribute(goal!.id, amount),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["savings-goals"] });
      qc.invalidateQueries({ queryKey: ["savings-goal", goal!.id] });
      setAmount("");
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || parseFloat(amount) <= 0) return;
    contribute.mutate(parseFloat(amount));
  };

  if (!goal) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Contribute to {goal.name}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="p-3 rounded-lg bg-muted text-sm">
            <div className="flex justify-between mb-1">
              <span>Current</span>
              <span className="font-medium">${goal.current_amount.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span>Target</span>
              <span className="font-medium">${goal.target_amount.toLocaleString()}</span>
            </div>
          </div>
          <div>
            <Label>Amount to Add</Label>
            <div className="relative mt-1">
              <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="500"
                className="pl-9"
                min="0.01"
                step="0.01"
                required
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="financial" disabled={contribute.isPending}>
              {contribute.isPending ? "Saving..." : "Add Savings"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AddMilestoneDialog({
  goalId,
  open,
  onClose,
}: {
  goalId: number | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [targetAmount, setTargetAmount] = useState("");

  const add = useMutation({
    mutationFn: (data: { title: string; target_amount: number }) =>
      savings.addMilestone(goalId!, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["savings-goals"] });
      qc.invalidateQueries({ queryKey: ["savings-goal", goalId!] });
      setTitle("");
      setTargetAmount("");
      onClose();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title || !targetAmount) return;
    add.mutate({ title, target_amount: parseFloat(targetAmount) });
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Milestone</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label>Milestone Title</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Save $1,000"
              className="mt-1"
              required
            />
          </div>
          <div>
            <Label>Target Amount</Label>
            <Input
              type="number"
              value={targetAmount}
              onChange={(e) => setTargetAmount(e.target.value)}
              placeholder="1000"
              className="mt-1"
              min="1"
              required
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="financial" disabled={add.isPending}>
              {add.isPending ? "Adding..." : "Add Milestone"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function GoalDetail({
  goal,
  onBack,
}: {
  goal: SavingsGoal;
  onBack: () => void;
}) {
  const qc = useQueryClient();
  const { data: detail, isLoading } = useQuery({
    queryKey: ["savings-goal", goal.id],
    queryFn: () => savings.get(goal.id),
    initialData: goal,
  });

  const deleteMilestone = useMutation({
    mutationFn: (milestoneId: number) =>
      savings.deleteMilestone(goal.id, milestoneId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["savings-goals"] });
      qc.invalidateQueries({ queryKey: ["savings-goal", goal.id] });
    },
  });

  const pct = detail
    ? (detail.current_amount / detail.target_amount) * 100
    : 0;

  return (
    <div className="space-y-6 fade-in-up">
      <button
        onClick={onBack}
        className="text-sm text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
      >
        ← Back to Goals
      </button>

      <div className="grid gap-4 md:grid-cols-3">
        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardTitle className="text-sm text-muted-foreground">
              Saved So Far
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value">
              ${detail?.current_amount.toLocaleString() ?? 0}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardTitle className="text-sm text-muted-foreground">
              Target
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value">
              ${detail?.target_amount.toLocaleString() ?? 0}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={detail?.status === "COMPLETED" ? "success" : "financial"}>
          <FinancialCardHeader>
            <FinancialCardTitle className="text-sm text-muted-foreground">
              Remaining
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value">
              {detail?.status === "COMPLETED"
                ? "🎉 Goal Reached!"
                : `$${((detail?.target_amount ?? 0) - (detail?.current_amount ?? 0)).toLocaleString()}`}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Progress */}
      <FinancialCard variant="financial">
        <FinancialCardHeader>
          <FinancialCardTitle className="section-title">Overall Progress</FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">
                ${detail?.current_amount.toLocaleString()} of ${detail?.target_amount.toLocaleString()}
              </span>
              <span className="font-semibold">{pct.toFixed(1)}%</span>
            </div>
            <div className="chart-track h-3">
              <div
                className="chart-fill-success"
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
            {detail?.deadline && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Calendar className="w-3 h-3" />
                Target date: {detail.deadline}
              </div>
            )}
          </div>
        </FinancialCardContent>
      </FinancialCard>

      {/* Milestones */}
      <FinancialCard variant="financial">
        <FinancialCardHeader>
          <div className="flex items-center justify-between">
            <FinancialCardTitle className="section-title">Milestones</FinancialCardTitle>
          </div>
          <FinancialCardDescription>
            Track checkpoints on your way to the goal
          </FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : !detail?.milestones?.length ? (
            <p className="text-sm text-muted-foreground">No milestones yet.</p>
          ) : (
            <div className="space-y-3">
              {detail?.milestones?.map((m) => {
                const reached = m.reached;
                return (
                  <div
                    key={m.id}
                    className={`flex items-center justify-between p-3 rounded-lg border ${
                      reached ? "border-success/40 bg-success/5" : "border-border"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {reached ? (
                        <CheckCircle2 className="w-4 h-4 text-success" />
                      ) : (
                        <Circle className="w-4 h-4 text-muted-foreground" />
                      )}
                      <div>
                        <p className={`text-sm font-medium ${reached ? "text-success" : "text-foreground"}`}>
                          {m.title}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          ${m.target_amount.toLocaleString()}
                          {m.reached_at && ` · Reached ${m.reached_at}`}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => deleteMilestone.mutate(m.id)}
                      className="text-muted-foreground hover:text-destructive transition-colors p-1"
                      disabled={deleteMilestone.isPending}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </FinancialCardContent>
        <FinancialCardFooter>
          <MilestoneAdder goalId={goal.id} />
        </FinancialCardFooter>
      </FinancialCard>
    </div>
  );
}

function MilestoneAdder({ goalId }: { goalId: number }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="financial" size="sm" className="w-full" onClick={() => setOpen(true)}>
        <Plus className="w-4 h-4" />
        Add Milestone
      </Button>
      <AddMilestoneDialog goalId={goalId} open={open} onClose={() => setOpen(false)} />
    </>
  );
}

export function Savings() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<SavingsGoal | null>(null);
  const [contributeGoal, setContributeGoal] = useState<SavingsGoal | null>(null);

  const { data: goals = [], isLoading } = useQuery({
    queryKey: ["savings-goals"],
    queryFn: savings.list,
  });

  const deleteGoal = useMutation({
    mutationFn: (id: number) => savings.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["savings-goals"] }),
  });

  const totalSaved = goals.reduce((sum, g) => sum + g.current_amount, 0);
  const totalTarget = goals.reduce((sum, g) => sum + g.target_amount, 0);
  const completedCount = goals.filter((g) => g.status === "COMPLETED").length;

  if (selectedGoal) {
    return (
      <GoalDetail
        goal={selectedGoal}
        onBack={() => setSelectedGoal(null)}
      />
    );
  }

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Savings Goals</h1>
            <p className="page-subtitle">
              Set goals, track progress, and celebrate milestones
            </p>
          </div>
          <Button variant="financial" size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="w-4 h-4" />
            New Goal
          </Button>
        </div>
      </div>

      {/* Overview */}
      <div className="grid gap-4 md:grid-cols-3 mb-8">
        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardTitle className="text-sm text-muted-foreground">
              Total Saved
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value">${totalSaved.toLocaleString()}</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardTitle className="text-sm text-muted-foreground">
              Total Target
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value">${totalTarget.toLocaleString()}</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={completedCount > 0 ? "success" : "financial"}>
          <FinancialCardHeader>
            <FinancialCardTitle className="text-sm text-muted-foreground">
              Goals Completed
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value">
              {completedCount} / {goals.length}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals Grid */}
      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading...</div>
      ) : goals.length === 0 ? (
        <FinancialCard variant="financial">
          <FinancialCardContent className="flex flex-col items-center justify-center py-12">
            <PiggyBank className="w-12 h-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-4">
              No savings goals yet. Create your first one!
            </p>
            <Button variant="financial" onClick={() => setShowCreate(true)}>
              <Plus className="w-4 h-4" />
              New Goal
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {goals.map((goal) => (
            <GoalCard
              key={goal.id}
              goal={goal}
              onSelect={setSelectedGoal}
              onDelete={(id) => deleteGoal.mutate(id)}
            />
          ))}
        </div>
      )}

      <CreateGoalDialog open={showCreate} onClose={() => setShowCreate(false)} />
      <ContributeDialog
        goal={contributeGoal}
        open={!!contributeGoal}
        onClose={() => setContributeGoal(null)}
      />
    </div>
  );
}
