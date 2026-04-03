import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const API = import.meta.env.VITE_API_URL || "";

interface Milestone {
  percent: number;
  reached: boolean;
}

interface Goal {
  id: number;
  name: string;
  target_amount: string;
  current_amount: string;
  currency: string;
  deadline: string | null;
  icon: string | null;
  is_completed: boolean;
  progress_percent: number;
  milestones: Milestone[];
  created_at: string;
}

export default function Savings() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [open, setOpen] = useState(false);
  const [contributeOpen, setContributeOpen] = useState<number | null>(null);
  const [form, setForm] = useState({
    name: "",
    target_amount: "",
    currency: "EUR",
    deadline: "",
  });
  const [contribution, setContribution] = useState({ amount: "", notes: "" });

  const token = localStorage.getItem("token");

  useEffect(() => {
    fetchGoals();
  }, []);

  const fetchGoals = async () => {
    const res = await fetch(`${API}/savings`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json();
      setGoals(data.goals);
    }
  };

  const createGoal = async () => {
    const res = await fetch(`${API}/savings`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(form),
    });
    if (res.ok) {
      setOpen(false);
      setForm({ name: "", target_amount: "", currency: "EUR", deadline: "" });
      fetchGoals();
    }
  };

  const addContribution = async (goalId: number) => {
    const res = await fetch(`${API}/savings/${goalId}/contributions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(contribution),
    });
    if (res.ok) {
      setContributeOpen(null);
      setContribution({ amount: "", notes: "" });
      fetchGoals();
    }
  };

  const deleteGoal = async (id: number) => {
    if (!confirm("Delete this goal?")) return;
    await fetch(`${API}/savings/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchGoals();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Savings Goals</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>+ New Goal</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Savings Goal</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <Input
                placeholder="Goal name (e.g., Vacation Fund)"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
              <Input
                type="number"
                placeholder="Target amount"
                value={form.target_amount}
                onChange={(e) =>
                  setForm({ ...form, target_amount: e.target.value })
                }
              />
              <Input
                placeholder="Currency (EUR, USD, INR)"
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
              />
              <Input
                type="date"
                value={form.deadline}
                onChange={(e) => setForm({ ...form, deadline: e.target.value })}
              />
              <Button onClick={createGoal} className="w-full">
                Create Goal
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {goals.length === 0 && (
        <p className="text-muted-foreground">
          No savings goals yet. Create one to start tracking!
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {goals.map((goal) => (
          <Card key={goal.id} className={goal.is_completed ? "border-green-500" : ""}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-lg font-semibold">
                {goal.icon && <span className="mr-2">{goal.icon}</span>}
                {goal.name}
              </CardTitle>
              <div className="flex gap-1">
                {goal.is_completed && (
                  <Badge variant="default" className="bg-green-600">
                    ✅ Complete
                  </Badge>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => deleteGoal(goal.id)}
                >
                  ✕
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span>
                    {goal.current_amount} / {goal.target_amount} {goal.currency}
                  </span>
                  <span className="font-medium">
                    {goal.progress_percent}%
                  </span>
                </div>
                <Progress value={goal.progress_percent} className="h-3" />
                <div className="flex gap-1">
                  {goal.milestones.map((m) => (
                    <Badge
                      key={m.percent}
                      variant={m.reached ? "default" : "outline"}
                      className={
                        m.reached ? "bg-green-100 text-green-800" : "text-xs"
                      }
                    >
                      {m.percent}%
                    </Badge>
                  ))}
                </div>
                {goal.deadline && (
                  <p className="text-xs text-muted-foreground">
                    Deadline: {goal.deadline}
                  </p>
                )}
                <Dialog
                  open={contributeOpen === goal.id}
                  onOpenChange={(o) => setContributeOpen(o ? goal.id : null)}
                >
                  <DialogTrigger asChild>
                    <Button variant="outline" size="sm" className="w-full">
                      + Add Contribution
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>
                        Add Contribution to {goal.name}
                      </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                      <Input
                        type="number"
                        placeholder="Amount"
                        value={contribution.amount}
                        onChange={(e) =>
                          setContribution({
                            ...contribution,
                            amount: e.target.value,
                          })
                        }
                      />
                      <Input
                        placeholder="Notes (optional)"
                        value={contribution.notes}
                        onChange={(e) =>
                          setContribution({
                            ...contribution,
                            notes: e.target.value,
                          })
                        }
                      />
                      <Button
                        onClick={() => addContribution(goal.id)}
                        className="w-full"
                      >
                        Add
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
