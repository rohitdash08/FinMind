import { useState } from "react";
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
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Target,
  Trophy,
  Plus,
  TrendingUp,
  CheckCircle2,
  AlertCircle,
  Coins,
  Flag,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Milestone {
  pct: number;
  label: string;
  reached: boolean;
}

interface SavingsGoal {
  id: number;
  name: string;
  targetAmount: number;
  savedAmount: number;
  targetDate: string;
  category: string;
  color: string;
}

const MILESTONE_THRESHOLDS = [25, 50, 75, 100] as const;

function getMilestones(saved: number, target: number): Milestone[] {
  const pct = target > 0 ? (saved / target) * 100 : 0;
  return MILESTONE_THRESHOLDS.map((threshold) => ({
    pct: threshold,
    label: threshold === 100 ? "Goal reached!" : `${threshold}% milestone`,
    reached: pct >= threshold,
  }));
}

function getProgressColor(pct: number): string {
  if (pct >= 100) return "bg-success";
  if (pct >= 75) return "bg-primary";
  if (pct >= 50) return "bg-warning";
  return "bg-muted-foreground";
}

const SAMPLE_GOALS: SavingsGoal[] = [
  {
    id: 1,
    name: "Emergency Fund",
    targetAmount: 10000,
    savedAmount: 6500,
    targetDate: "2026-12-31",
    category: "Safety",
    color: "bg-primary",
  },
  {
    id: 2,
    name: "Vacation to Japan",
    targetAmount: 3000,
    savedAmount: 1800,
    targetDate: "2026-08-15",
    category: "Travel",
    color: "bg-info",
  },
  {
    id: 3,
    name: "New Laptop",
    targetAmount: 1500,
    savedAmount: 1500,
    targetDate: "2026-03-01",
    category: "Tech",
    color: "bg-success",
  },
  {
    id: 4,
    name: "Down Payment",
    targetAmount: 50000,
    savedAmount: 12000,
    targetDate: "2028-01-01",
    category: "Housing",
    color: "bg-warning",
  },
];

function GoalCard({ goal }: { goal: SavingsGoal }) {
  const pct = Math.min((goal.savedAmount / goal.targetAmount) * 100, 100);
  const milestones = getMilestones(goal.savedAmount, goal.targetAmount);
  const isComplete = pct >= 100;
  const remaining = Math.max(goal.targetAmount - goal.savedAmount, 0);

  return (
    <FinancialCard className={cn("transition-shadow hover:shadow-md", isComplete && "border-success")}>
      <FinancialCardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            {isComplete ? (
              <Trophy className="h-5 w-5 text-success" />
            ) : (
              <Target className="h-5 w-5 text-primary" />
            )}
            <FinancialCardTitle>{goal.name}</FinancialCardTitle>
          </div>
          <Badge variant={isComplete ? "default" : "secondary"}>
            {goal.category}
          </Badge>
        </div>
        <FinancialCardDescription>
          Target date: {new Date(goal.targetDate).toLocaleDateString()}
        </FinancialCardDescription>
      </FinancialCardHeader>
      <FinancialCardContent className="space-y-4">
        <div>
          <div className="mb-1 flex justify-between text-sm">
            <span className="font-medium">${goal.savedAmount.toLocaleString()} saved</span>
            <span className="text-muted-foreground">${goal.targetAmount.toLocaleString()} goal</span>
          </div>
          <Progress value={pct} className="h-3" />
          <p className="mt-1 text-right text-xs text-muted-foreground">
            {pct.toFixed(1)}% — {remaining > 0 ? `$${remaining.toLocaleString()} to go` : "Complete!"}
          </p>
        </div>

        {/* Milestone badges */}
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Milestones
          </p>
          <div className="flex flex-wrap gap-2">
            {milestones.map((m) => (
              <span
                key={m.pct}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                  m.reached
                    ? "bg-success/10 text-success"
                    : "bg-muted text-muted-foreground"
                )}
                aria-label={m.reached ? `${m.label} achieved` : `${m.label} not yet reached`}
              >
                {m.reached ? <CheckCircle2 className="h-3 w-3" /> : <Flag className="h-3 w-3" />}
                {m.label}
              </span>
            ))}
          </div>
        </div>
      </FinancialCardContent>
      <FinancialCardFooter className="text-xs text-muted-foreground">
        {isComplete ? (
          <span className="flex items-center gap-1 text-success font-medium">
            <Trophy className="h-4 w-4" /> Goal achieved! Great work.
          </span>
        ) : (
          <span className="flex items-center gap-1">
            <TrendingUp className="h-4 w-4" />
            Keep going — you&#39;re {pct.toFixed(0)}% there!
          </span>
        )}
      </FinancialCardFooter>
    </FinancialCard>
  );
}

interface AddGoalDialogProps {
  onAdd: (goal: Omit<SavingsGoal, "id">) => void;
}

function AddGoalDialog({ onAdd }: AddGoalDialogProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [savedAmount, setSavedAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [category, setCategory] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !targetAmount || !targetDate) return;
    onAdd({
      name,
      targetAmount: parseFloat(targetAmount),
      savedAmount: parseFloat(savedAmount) || 0,
      targetDate,
      category: category || "General",
      color: "bg-primary",
    });
    setOpen(false);
    setName("");
    setTargetAmount("");
    setSavedAmount("");
    setTargetDate("");
    setCategory("");
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          New Goal
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Savings Goal</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="goal-name">Goal Name</Label>
            <Input
              id="goal-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Emergency Fund"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="target-amount">Target Amount ($)</Label>
              <Input
                id="target-amount"
                type="number"
                min="1"
                value={targetAmount}
                onChange={(e) => setTargetAmount(e.target.value)}
                placeholder="5000"
                required
              />
            </div>
            <div>
              <Label htmlFor="saved-amount">Already Saved ($)</Label>
              <Input
                id="saved-amount"
                type="number"
                min="0"
                value={savedAmount}
                onChange={(e) => setSavedAmount(e.target.value)}
                placeholder="0"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="target-date">Target Date</Label>
              <Input
                id="target-date"
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="category">Category</Label>
              <Input
                id="category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="e.g. Travel"
              />
            </div>
          </div>
          <Button type="submit" className="w-full">
            Create Goal
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function SavingsGoals() {
  const [goals, setGoals] = useState<SavingsGoal[]>(SAMPLE_GOALS);

  const totalSaved = goals.reduce((s, g) => s + g.savedAmount, 0);
  const totalTarget = goals.reduce((s, g) => s + g.targetAmount, 0);
  const completed = goals.filter((g) => g.savedAmount >= g.targetAmount).length;

  const handleAdd = (goal: Omit<SavingsGoal, "id">) => {
    setGoals((prev) => [...prev, { ...goal, id: Date.now() }]);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Savings Goals</h1>
          <p className="text-muted-foreground">
            Track your progress toward financial milestones
          </p>
        </div>
        <AddGoalDialog onAdd={handleAdd} />
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Coins className="h-4 w-4 text-primary" />
              Total Saved
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-2xl font-bold">${totalSaved.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">
              of ${totalTarget.toLocaleString()} total target
            </p>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Target className="h-4 w-4 text-primary" />
              Active Goals
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-2xl font-bold">{goals.length}</p>
            <p className="text-xs text-muted-foreground">
              {completed} completed
            </p>
          </FinancialCardContent>
        </FinancialCard>
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Trophy className="h-4 w-4 text-success" />
              Overall Progress
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-2xl font-bold">
              {totalTarget > 0 ? ((totalSaved / totalTarget) * 100).toFixed(1) : 0}%
            </p>
            <Progress
              value={totalTarget > 0 ? (totalSaved / totalTarget) * 100 : 0}
              className="mt-1 h-2"
            />
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Goals grid */}
      {goals.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
          <AlertCircle className="mb-3 h-10 w-10 text-muted-foreground" />
          <h3 className="font-semibold">No savings goals yet</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Create your first goal to start tracking your progress.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-2">
          {goals.map((goal) => (
            <GoalCard key={goal.id} goal={goal} />
          ))}
        </div>
      )}
    </div>
  );
}
