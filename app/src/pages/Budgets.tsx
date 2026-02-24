import { useEffect, useState } from 'react';
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
import {
  Calendar,
  DollarSign,
  Plus,
  PieChart,
  Target,
  AlertCircle,
  AlertTriangle,
  Settings,
  Trash2,
} from 'lucide-react';
import {
  listBudgets,
  createBudget,
  deleteBudget,
  getBudgetWarnings,
  type Budget,
  type BudgetWarning,
} from '@/api/budgets';
import { api } from '@/api/client';
import { formatMoney } from '@/lib/currency';

type Category = { id: number; name: string };

function currency(n: number) {
  return formatMoney(Number(n || 0));
}

export function Budgets() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [warnings, setWarnings] = useState<BudgetWarning[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New budget form
  const [showForm, setShowForm] = useState(false);
  const [formCatId, setFormCatId] = useState<number | ''>('');
  const [formAmount, setFormAmount] = useState('');
  const [formPeriod, setFormPeriod] = useState<'MONTHLY' | 'WEEKLY'>('MONTHLY');
  const [formError, setFormError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [b, w, c] = await Promise.all([
        listBudgets(),
        getBudgetWarnings(),
        api<Category[]>('/categories'),
      ]);
      setBudgets(b);
      setWarnings(w);
      setCategories(c);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load budgets');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreate = async () => {
    setFormError(null);
    if (!formCatId || !formAmount) {
      setFormError('Category and amount are required');
      return;
    }
    try {
      await createBudget({
        category_id: Number(formCatId),
        amount: parseFloat(formAmount),
        period: formPeriod,
      });
      setShowForm(false);
      setFormCatId('');
      setFormAmount('');
      await fetchData();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Failed to create budget');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteBudget(id);
      await fetchData();
    } catch {
      // ignore
    }
  };

  const catName = (id: number) =>
    categories.find((c) => c.id === id)?.name || 'Unknown';

  const totalAllocated = budgets.reduce((s, b) => s + b.amount, 0);
  const totalWarningSpent = warnings.reduce((s, w) => s + w.spent, 0);

  const exceededWarnings = warnings.filter((w) => w.level === 'exceeded');
  const approachingWarnings = warnings.filter((w) => w.level === 'warning');

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Budget Management</h1>
            <p className="page-subtitle">
              Track your spending limits and get early warnings
            </p>
          </div>
          <div className="flex gap-3">
            <Button
              variant="financial"
              size="sm"
              onClick={() => setShowForm(!showForm)}
            >
              <Plus className="w-4 h-4" />
              New Budget
            </Button>
          </div>
        </div>
      </div>

      {error && <div className="error mb-6">{error}</div>}

      {/* Overspend Warning Cards */}
      {(exceededWarnings.length > 0 || approachingWarnings.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2 mb-8">
          {exceededWarnings.map((w) => (
            <FinancialCard
              key={`exceeded-${w.budget_id}`}
              variant="destructive"
              className="fade-in-up"
            >
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-5 h-5" />
                  <FinancialCardTitle className="text-sm font-semibold">
                    Budget Exceeded
                  </FinancialCardTitle>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="font-medium mb-1">{w.category_name}</div>
                <div className="text-sm opacity-90">
                  Spent {currency(w.spent)} of {currency(w.budget_amount)} (
                  {w.percentage.toFixed(0)}%)
                </div>
                <div className="chart-track mt-2 bg-destructive-light">
                  <div
                    className="chart-fill-danger h-2"
                    style={{ width: `${Math.min(w.percentage, 100)}%` }}
                  />
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ))}
          {approachingWarnings.map((w) => (
            <FinancialCard
              key={`warning-${w.budget_id}`}
              className="fade-in-up border-warning"
            >
              <FinancialCardHeader className="pb-3">
                <div className="flex items-center gap-2 text-warning">
                  <AlertTriangle className="w-5 h-5" />
                  <FinancialCardTitle className="text-sm font-semibold text-warning">
                    Approaching Limit
                  </FinancialCardTitle>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="font-medium mb-1">{w.category_name}</div>
                <div className="text-sm text-muted-foreground">
                  Spent {currency(w.spent)} of {currency(w.budget_amount)} (
                  {w.percentage.toFixed(0)}%)
                </div>
                <div className="chart-track mt-2">
                  <div
                    className="chart-fill-primary h-2"
                    style={{ width: `${Math.min(w.percentage, 100)}%` }}
                  />
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      )}

      {/* New Budget Form */}
      {showForm && (
        <FinancialCard variant="financial" className="mb-8 fade-in-up">
          <FinancialCardHeader>
            <FinancialCardTitle className="section-title">
              Create Budget
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            {formError && (
              <div className="text-sm text-destructive mb-3">{formError}</div>
            )}
            <div className="flex flex-wrap gap-4 items-end">
              <div>
                <label
                  htmlFor="budget-category"
                  className="text-sm text-muted-foreground block mb-1"
                >
                  Category
                </label>
                <select
                  id="budget-category"
                  className="input h-9 w-[180px]"
                  value={formCatId}
                  onChange={(e) =>
                    setFormCatId(e.target.value ? Number(e.target.value) : '')
                  }
                >
                  <option value="">Select...</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="budget-amount"
                  className="text-sm text-muted-foreground block mb-1"
                >
                  Amount
                </label>
                <input
                  id="budget-amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  className="input h-9 w-[140px]"
                  placeholder="500.00"
                  value={formAmount}
                  onChange={(e) => setFormAmount(e.target.value)}
                />
              </div>
              <div>
                <label
                  htmlFor="budget-period"
                  className="text-sm text-muted-foreground block mb-1"
                >
                  Period
                </label>
                <select
                  id="budget-period"
                  className="input h-9 w-[130px]"
                  value={formPeriod}
                  onChange={(e) =>
                    setFormPeriod(e.target.value as 'MONTHLY' | 'WEEKLY')
                  }
                >
                  <option value="MONTHLY">Monthly</option>
                  <option value="WEEKLY">Weekly</option>
                </select>
              </div>
              <Button variant="financial" size="sm" onClick={handleCreate}>
                Save
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowForm(false)}
              >
                Cancel
              </Button>
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Overview Cards */}
      <div className="grid gap-4 md:grid-cols-3 mb-8">
        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Total Budgeted
              </FinancialCardTitle>
              <Target className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {loading ? '...' : currency(totalAllocated)}
            </div>
            <div className="text-sm text-muted-foreground">
              {budgets.length} budget(s) set
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                Active Warnings
              </FinancialCardTitle>
              <AlertTriangle className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">
              {loading ? '...' : warnings.length}
            </div>
            <div className="text-sm text-muted-foreground">
              {exceededWarnings.length} exceeded, {approachingWarnings.length}{' '}
              approaching
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard
          variant={exceededWarnings.length > 0 ? 'destructive' : 'success'}
        >
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium">
                {exceededWarnings.length > 0 ? 'Over Budget' : 'On Track'}
              </FinancialCardTitle>
              {exceededWarnings.length > 0 ? (
                <AlertCircle className="w-5 h-5" />
              ) : (
                <PieChart className="w-5 h-5" />
              )}
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value mb-1">
              {loading
                ? '...'
                : exceededWarnings.length > 0
                  ? `${exceededWarnings.length} categor${exceededWarnings.length === 1 ? 'y' : 'ies'}`
                  : 'All good'}
            </div>
            <div className="text-sm opacity-80">
              {exceededWarnings.length > 0
                ? 'Needs attention'
                : 'Spending within limits'}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Budget List */}
      <FinancialCard variant="financial" className="fade-in-up">
        <FinancialCardHeader>
          <div className="flex items-center justify-between">
            <FinancialCardTitle className="section-title">
              Your Budgets
            </FinancialCardTitle>
          </div>
          <FinancialCardDescription>
            Category spending limits and current status
          </FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          {loading ? (
            <div className="text-sm text-muted-foreground">Loading...</div>
          ) : budgets.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No budgets set yet. Click "New Budget" to get started.
            </div>
          ) : (
            <div className="space-y-6">
              {budgets.map((b) => {
                const w = warnings.find((w) => w.budget_id === b.id);
                const pct = w ? w.percentage : 0;
                const spent = w ? w.spent : 0;
                const isExceeded = w?.level === 'exceeded';
                const isWarning = w?.level === 'warning';

                return (
                  <div key={b.id} className="space-y-3 interactive-row">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div
                          className={`w-4 h-4 rounded-full ${
                            isExceeded
                              ? 'bg-destructive'
                              : isWarning
                                ? 'bg-warning'
                                : 'bg-success'
                          }`}
                        />
                        <div>
                          <div className="font-medium text-foreground">
                            {catName(b.category_id)}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {currency(spent)} of {currency(b.amount)} ·{' '}
                            {b.period.toLowerCase()}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <div
                            className={`font-semibold ${
                              isExceeded
                                ? 'text-destructive'
                                : isWarning
                                  ? 'text-warning'
                                  : 'text-foreground'
                            }`}
                          >
                            {pct.toFixed(0)}%
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(b.id)}
                          aria-label={`Delete budget for ${catName(b.category_id)}`}
                        >
                          <Trash2 className="w-4 h-4 text-muted-foreground" />
                        </Button>
                      </div>
                    </div>
                    <div
                      className={`chart-track ${isExceeded ? 'bg-destructive-light' : ''}`}
                    >
                      <div
                        className={
                          isExceeded
                            ? 'chart-fill-danger h-2'
                            : isWarning
                              ? 'chart-fill-primary h-2'
                              : 'chart-fill-success h-2'
                        }
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                    {isExceeded && (
                      <Badge variant="destructive" className="text-xs">
                        Over Budget
                      </Badge>
                    )}
                    {isWarning && (
                      <Badge className="text-xs bg-warning text-warning-foreground">
                        Approaching Limit
                      </Badge>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>
    </div>
  );
}
