import { useEffect, useState } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { DollarSign, Plus, Target, AlertCircle } from 'lucide-react';
import { getBudgetWarnings, setBudget, type BudgetWarning } from '@/api/budgets';
import { listCategories, type Category } from '@/api/categories';
import { useToast } from '@/hooks/use-toast';
import { formatMoney } from '@/lib/currency';

const statusColor: Record<string, string> = {
  ok: 'bg-green-500',
  warning: 'bg-yellow-500',
  critical: 'bg-orange-500',
  over: 'bg-red-500',
};

const statusBadge: Record<string, 'default' | 'secondary' | 'destructive'> = {
  ok: 'default',
  warning: 'secondary',
  critical: 'destructive',
  over: 'destructive',
};

export function Budgets() {
  const [warnings, setWarnings] = useState<BudgetWarning[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formCatId, setFormCatId] = useState<string>('');
  const [formLimit, setFormLimit] = useState('');
  const { toast } = useToast();

  const currentMonth = new Date().toISOString().slice(0, 7);

  const load = async () => {
    setLoading(true);
    try {
      const [w, c] = await Promise.all([getBudgetWarnings(currentMonth), listCategories()]);
      setWarnings(w);
      setCategories(c);
      w.filter(i => i.status === 'over' || i.status === 'critical').forEach(i => {
        toast({ title: `${i.category_name} is at ${i.pct_used}% of budget`, variant: 'destructive' });
      });
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const totalLimit = warnings.reduce((s, w) => s + w.monthly_limit, 0);
  const totalSpent = warnings.reduce((s, w) => s + w.spent, 0);
  const totalRemaining = totalLimit - totalSpent;

  const handleSave = async () => {
    const limit = parseFloat(formLimit);
    if (!limit || limit <= 0) return;
    try {
      await setBudget({
        category_id: formCatId && formCatId !== '__total__' ? Number(formCatId) : null,
        monthly_limit: limit,
        month: currentMonth,
      });
      setDialogOpen(false);
      setFormCatId('');
      setFormLimit('');
      await load();
    } catch { /* ignore */ }
  };

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Budget Management</h1>
            <p className="page-subtitle">Track your spending and stay on top of your financial goals</p>
          </div>
          <Button variant="financial" size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="w-4 h-4" /> Set Budget
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3 mb-8">
        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Allocated</FinancialCardTitle>
              <Target className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{loading ? '...' : formatMoney(totalLimit)}</div>
            <div className="text-sm text-muted-foreground">This month's budget</div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium text-muted-foreground">Total Spent</FinancialCardTitle>
              <DollarSign className="w-5 h-5 text-muted-foreground" />
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value text-foreground mb-1">{loading ? '...' : formatMoney(totalSpent)}</div>
            <div className="text-sm text-muted-foreground">
              {totalLimit > 0 ? `${((totalSpent / totalLimit) * 100).toFixed(1)}% of budget used` : 'No budgets set'}
            </div>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant={totalRemaining < 0 ? 'destructive' : 'success'}>
          <FinancialCardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="text-sm font-medium">
                {totalRemaining < 0 ? 'Over Budget' : 'Remaining'}
              </FinancialCardTitle>
              {totalRemaining < 0 ? <AlertCircle className="w-5 h-5" /> : <Target className="w-5 h-5" />}
            </div>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="metric-value mb-1">{loading ? '...' : formatMoney(Math.abs(totalRemaining))}</div>
            <div className="text-sm opacity-80">{totalRemaining < 0 ? 'Overspent this month' : 'Available to spend'}</div>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      <FinancialCard variant="financial" className="fade-in-up">
        <FinancialCardHeader>
          <FinancialCardTitle className="section-title">Budget Categories</FinancialCardTitle>
          <FinancialCardDescription>Track spending across different categories</FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          {warnings.length === 0 && !loading ? (
            <div className="text-sm text-muted-foreground">No budgets set for this month. Click "Set Budget" to get started.</div>
          ) : (
            <div className="space-y-6">
              {warnings.map((w) => (
                <div key={`${w.category_id ?? 'total'}`} className="space-y-2 interactive-row">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-foreground">{w.category_name}</div>
                      <div className="text-sm text-muted-foreground">
                        {formatMoney(w.spent)} of {formatMoney(w.monthly_limit)}
                      </div>
                    </div>
                    <div className="text-right flex items-center gap-2">
                      <span className={`font-semibold ${w.status === 'over' ? 'text-destructive' : 'text-foreground'}`}>
                        {formatMoney(Math.abs(w.remaining))} {w.remaining < 0 ? 'over' : 'left'}
                      </span>
                      <Badge variant={statusBadge[w.status]}>{w.status}</Badge>
                    </div>
                  </div>
                  <Progress
                    value={Math.min(w.pct_used, 100)}
                    className={`h-3 [&>div]:${statusColor[w.status]}`}
                  />
                </div>
              ))}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Set Budget Limit</DialogTitle>
            <DialogDescription>Set a monthly spending limit for a category.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium" htmlFor="budget-category">Category</label>
              <Select value={formCatId} onValueChange={setFormCatId}>
                <SelectTrigger id="budget-category">
                  <SelectValue placeholder="Total (all categories)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__total__">Total (all categories)</SelectItem>
                  {categories.map(c => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium" htmlFor="budget-limit">Monthly Limit</label>
              <Input id="budget-limit" type="number" min="0" step="0.01" placeholder="0.00" value={formLimit} onChange={e => setFormLimit(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
