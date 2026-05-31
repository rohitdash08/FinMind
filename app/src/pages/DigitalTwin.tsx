import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";

const API = import.meta.env.VITE_API_URL || "";

interface Twin {
  id: number;
  name: string;
  monthly_income: number;
  monthly_expenses: number;
  savings_rate_pct: number;
  current_savings: number;
  risk_tolerance: string;
  retirement_age: number;
  inflation_rate_pct: number;
  return_rate_pct: number;
}

interface SimulationResult {
  scenario: string;
  projection_years: number;
  num_simulations: number;
  final_stats: {
    median: number;
    p10: number;
    p90: number;
    success_probability: number;
  };
  milestone_stats: Record<string, { median: number; p10: number; p90: number }>;
  goals: Array<{
    goal_name: string;
    target_amount: number;
    success_probability: number;
    median_achievement_year: number | null;
  }>;
}

export default function DigitalTwin() {
  const { toast } = useToast();
  const [twins, setTwins] = useState<Twin[]>([]);
  const [selectedTwin, setSelectedTwin] = useState<Twin | null>(null);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [simulating, setSimulating] = useState(false);

  const [form, setForm] = useState({
    name: "My Financial Twin",
    monthly_income: 5000,
    monthly_expenses: 3000,
    savings_rate_pct: 20,
    current_savings: 10000,
    risk_tolerance: "moderate",
    retirement_age: 65,
    inflation_rate_pct: 6,
    return_rate_pct: 8,
  });

  const fetchTwins = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/twin`, { credentials: "include" });
      if (res.ok) {
        const data = await res.json();
        setTwins(data.twins || []);
      }
    } catch {
      // ignore
    }
    setLoading(false);
  };

  useEffect(() => { fetchTwins(); }, []);

  const createTwin = async () => {
    const res = await fetch(`${API}/twin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(form),
    });
    if (res.ok) {
      const twin = await res.json();
      setSelectedTwin(twin);
      fetchTwins();
      toast({ title: "Twin created" });
    }
  };

  const runSim = async () => {
    if (!selectedTwin) return;
    setSimulating(true);
    setResult(null);
    try {
      const res = await fetch(`${API}/twin/${selectedTwin.id}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          scenario_name: "what-if",
          projection_years: 30,
          num_simulations: 1000,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setResult(data);
        toast({ title: "Simulation complete" });
      }
    } catch {
      toast({ title: "Simulation failed", variant: "destructive" });
    }
    setSimulating(false);
  };

  const fmt = (n: number) => "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-3xl font-bold">Financial Digital Twin</h1>
      <p className="text-muted-foreground">Monte Carlo simulation of your financial future</p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle>Your Profile</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div><Label>Name</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Monthly Income</Label><Input type="number" value={form.monthly_income} onChange={e => setForm({ ...form, monthly_income: +e.target.value })} /></div>
              <div><Label>Monthly Expenses</Label><Input type="number" value={form.monthly_expenses} onChange={e => setForm({ ...form, monthly_expenses: +e.target.value })} /></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Savings Rate (%)</Label><Input type="number" value={form.savings_rate_pct} onChange={e => setForm({ ...form, savings_rate_pct: +e.target.value })} /></div>
              <div><Label>Current Savings</Label><Input type="number" value={form.current_savings} onChange={e => setForm({ ...form, current_savings: +e.target.value })} /></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Risk Tolerance</Label>
                <Select value={form.risk_tolerance} onValueChange={v => setForm({ ...form, risk_tolerance: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="conservative">Conservative</SelectItem>
                    <SelectItem value="moderate">Moderate</SelectItem>
                    <SelectItem value="aggressive">Aggressive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div><Label>Retirement Age</Label><Input type="number" value={form.retirement_age} onChange={e => setForm({ ...form, retirement_age: +e.target.value })} /></div>
            </div>
            <Button onClick={createTwin} className="w-full">Create & Simulate</Button>
          </CardContent>
        </Card>

        {selectedTwin && (
          <Card>
            <CardHeader><CardTitle>Existing Twins</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {twins.map(t => (
                <div key={t.id} className={`p-3 rounded cursor-pointer border ${selectedTwin.id === t.id ? "border-primary" : ""}`} onClick={() => setSelectedTwin(t)}>
                  <div className="font-medium">{t.name}</div>
                  <div className="text-sm text-muted-foreground">
                    {fmt(t.monthly_income)}/mo - {t.risk_tolerance}
                  </div>
                </div>
              ))}
              <Button onClick={runSim} disabled={simulating} className="w-full">
                {siminating ? "Running..." : "Run Monte Carlo Simulation"}
              </Button>
            </CardContent>
          </Card>
        )}
      </div>

      {result && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader><CardTitle>Median Net Worth</CardTitle></CardHeader>
            <CardContent><p className="text-3xl font-bold">{fmt(result.final_stats.median)}</p></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Pessimistic (P10)</CardTitle></CardHeader>
            <CardContent><p className="text-3xl font-bold text-orange-500">{fmt(result.final_stats.p10)}</p></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Optimistic (P90)</CardTitle></CardHeader>
            <CardContent><p className="text-3xl font-bold text-green-500">{fmt(result.final_stats.p90)}</p></CardContent>
          </Card>
        </div>
      )}

      {result && result.milestone_stats && (
        <Card>
          <CardHeader><CardTitle>Projected Net Worth Over Time</CardTitle></CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead><tr className="border-b"><th className="text-left py-2">Year</th><th className="text-right">P10</th><th className="text-right">Median</th><th className="text-right">P90</th></tr></thead>
              <tbody>
                {Object.entries(result.milestone_stats).map(([year, stats]) => (
                  <tr key={year} className="border-b">
                    <td className="py-2">{year}</td>
                    <td className="text-right">{fmt(stats.p10)}</td>
                    <td className="text-right font-medium">{fmt(stats.median)}</td>
                    <td className="text-right">{fmt(stats.p90)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {result && result.goals?.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Goal Success Probability</CardTitle></CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead><tr className="border-b"><th className="text-left py-2">Goal</th><th className="text-right">Target</th><th className="text-right">Success %</th><th className="text-right">Est. Year</th></tr></thead>
              <tbody>
                {result.goals.map(g => (
                  <tr key={g.goal_name} className="border-b">
                    <td className="py-2">{g.goal_name}</td>
                    <td className="text-right">{fmt(g.target_amount)}</td>
                    <td className="text-right">{g.success_probability}%</td>
                    <td className="text-right">{g.median_achievement_year || "N/A"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
