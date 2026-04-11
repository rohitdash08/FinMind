import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardFooter,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import {
  ArrowDownRight,
  ArrowUpRight,
  CreditCard,
  TrendingDown,
  TrendingUp,
  Wallet,
  AlertTriangle,
  Calendar,
  Plus,
  Settings2,
  ChevronUp,
  ChevronDown,
} from 'lucide-react';
import {
  getDashboardSummary,
  getDashboardPreferences,
  updateDashboardPreferences,
  DEFAULT_WIDGETS,
  type DashboardSummary,
  type WidgetConfig,
} from '@/api/dashboard';
import { useNavigate } from 'react-router-dom';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

// ---------------------------------------------------------------------------
// DashboardCustomizer — dialog for reordering and toggling widget visibility
// ---------------------------------------------------------------------------

type CustomizerProps = {
  widgets: WidgetConfig[];
  saving: boolean;
  onToggle: (id: string) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onSave: () => void;
};

function DashboardCustomizer({
  widgets,
  saving,
  onToggle,
  onMoveUp,
  onMoveDown,
  onSave,
}: CustomizerProps) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Show or hide widgets and drag them into the order you prefer. Changes
        are saved to your account.
      </p>
      <ul className="space-y-2" aria-label="Dashboard widgets">
        {widgets.map((widget, index) => (
          <li
            key={widget.id}
            className="flex items-center justify-between rounded-lg border px-3 py-2 bg-card"
          >
            <div className="flex items-center gap-3">
              <Switch
                id={`widget-toggle-${widget.id}`}
                checked={widget.visible}
                onCheckedChange={() => onToggle(widget.id)}
                aria-label={`Toggle ${widget.label}`}
              />
              <Label
                htmlFor={`widget-toggle-${widget.id}`}
                className={`cursor-pointer text-sm font-medium ${
                  widget.visible ? 'text-foreground' : 'text-muted-foreground line-through'
                }`}
              >
                {widget.label}
              </Label>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => onMoveUp(index)}
                disabled={index === 0}
                aria-label={`Move ${widget.label} up`}
              >
                <ChevronUp className="w-4 h-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => onMoveDown(index)}
                disabled={index === widgets.length - 1}
                aria-label={`Move ${widget.label} down`}
              >
                <ChevronDown className="w-4 h-4" />
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <Button
        variant="financial"
        size="sm"
        className="w-full"
        onClick={onSave}
        disabled={saving}
        aria-label="Save dashboard layout"
      >
        {saving ? 'Saving…' : 'Save Layout'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard — main page component
// ---------------------------------------------------------------------------

export function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));

  // Widget preferences
  const [widgets, setWidgets] = useState<WidgetConfig[]>(DEFAULT_WIDGETS);
  const [customizerOpen, setCustomizerOpen] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);
  // Draft config used inside the dialog (committed on "Save Layout")
  const [draft, setDraft] = useState<WidgetConfig[]>(DEFAULT_WIDGETS);

  // Load dashboard data
  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getDashboardSummary(month);
        setData(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    })();
  }, [month]);

  // Load saved widget preferences
  useEffect(() => {
    (async () => {
      try {
        const prefs = await getDashboardPreferences();
        setWidgets(prefs.widgets);
      } catch {
        // Non-critical — keep the defaults when the API is unavailable.
      }
    })();
  }, []);

  // Sync draft whenever the dialog opens
  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (open) setDraft([...widgets]);
      setCustomizerOpen(open);
    },
    [widgets],
  );

  const handleDraftToggle = useCallback((id: string) => {
    setDraft((prev) =>
      prev.map((w) => (w.id === id ? { ...w, visible: !w.visible } : w)),
    );
  }, []);

  const handleDraftMoveUp = useCallback((index: number) => {
    if (index === 0) return;
    setDraft((prev) => {
      const next = [...prev];
      [next[index - 1], next[index]] = [next[index], next[index - 1]];
      return next;
    });
  }, []);

  const handleDraftMoveDown = useCallback((index: number) => {
    setDraft((prev) => {
      if (index >= prev.length - 1) return prev;
      const next = [...prev];
      [next[index], next[index + 1]] = [next[index + 1], next[index]];
      return next;
    });
  }, []);

  const handleSavePrefs = useCallback(async () => {
    setSavingPrefs(true);
    try {
      const saved = await updateDashboardPreferences(draft);
      setWidgets(saved.widgets);
      setCustomizerOpen(false);
    } catch {
      // Keep dialog open so user can retry.
    } finally {
      setSavingPrefs(false);
    }
  }, [draft]);

  // Summary data
  const summary = useMemo(() => {
    if (!data) {
      return {
        net_flow: 0,
        monthly_income: 0,
        monthly_expenses: 0,
        upcoming_bills_total: 0,
        upcoming_bills_count: 0,
      };
    }
    return data.summary;
  }, [data]);

  const summaryCards = [
    {
      title: 'Net Flow',
      amount: currency(summary.net_flow),
      change: summary.net_flow >= 0 ? 'Positive' : 'Negative',
      trend: summary.net_flow >= 0 ? 'up' : 'down',
      icon: Wallet,
      description: 'Current month',
    },
    {
      title: 'Monthly Income',
      amount: currency(summary.monthly_income),
      change: '+',
      trend: 'up',
      icon: TrendingUp,
      description: 'Current month',
    },
    {
      title: 'Monthly Expenses',
      amount: currency(summary.monthly_expenses),
      change: '-',
      trend: 'down',
      icon: TrendingDown,
      description: 'Current month',
    },
    {
      title: 'Upcoming Bills',
      amount: currency(summary.upcoming_bills_total),
      change: `${summary.upcoming_bills_count} bill(s)`,
      trend: 'up',
      icon: CreditCard,
      description: 'Due soon',
    },
  ] as const;

  const transactions = data?.recent_transactions ?? [];
  const upcomingBills = data?.upcoming_bills ?? [];
  const categoryBreakdown = data?.category_breakdown ?? [];

  // Resolve visibility per widget ID
  const visible = useMemo(() => {
    const map: Record<string, boolean> = {};
    for (const w of widgets) {
      map[w.id] = w.visible;
    }
    return map;
  }, [widgets]);

  // ---------------------------------------------------------------------------
  // Widget render map — keyed by widget ID
  // ---------------------------------------------------------------------------
  const widgetContent: Record<string, React.ReactNode> = {
    summary_cards: (
      <div
        key="summary_cards"
        className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8"
        data-testid="widget-summary_cards"
      >
        {summaryCards.map((card, index) => (
          <FinancialCard key={index} variant="financial" className="group card-interactive fade-in-up">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  {card.title}
                </FinancialCardTitle>
                <card.icon className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {loading ? '...' : card.amount}
              </div>
              <div className="flex items-center text-sm">
                {card.trend === 'up' ? (
                  <ArrowUpRight className="w-4 h-4 text-success mr-1" />
                ) : (
                  <ArrowDownRight className="w-4 h-4 text-destructive mr-1" />
                )}
                <span
                  className={
                    card.trend === 'up'
                      ? 'text-success font-medium mr-2'
                      : 'text-destructive font-medium mr-2'
                  }
                >
                  {card.change}
                </span>
                <span className="text-muted-foreground">{card.description}</span>
              </div>
            </FinancialCardContent>
          </FinancialCard>
        ))}
      </div>
    ),

    recent_transactions: (
      <div key="recent_transactions" className="lg:col-span-2" data-testid="widget-recent_transactions">
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader>
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="section-title">Recent Transactions</FinancialCardTitle>
              <Button variant="ghost" size="sm" onClick={() => navigate('/expenses')}>
                View All
              </Button>
            </div>
            <FinancialCardDescription>Your latest financial activity</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            {transactions.length === 0 ? (
              <div className="text-sm text-muted-foreground">No transactions yet.</div>
            ) : (
              <div className="space-y-3">
                {transactions.map((transaction) => {
                  const isIncome = transaction.type === 'INCOME';
                  return (
                    <div
                      key={transaction.id}
                      className="interactive-row flex items-center justify-between"
                    >
                      <div className="flex items-center space-x-3">
                        <div
                          className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                            isIncome
                              ? 'bg-success-light text-success'
                              : 'bg-destructive-light text-destructive'
                          }`}
                        >
                          {isIncome ? (
                            <ArrowUpRight className="w-5 h-5" />
                          ) : (
                            <ArrowDownRight className="w-5 h-5" />
                          )}
                        </div>
                        <div>
                          <div className="font-medium text-foreground">
                            {transaction.description}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {new Date(transaction.date).toLocaleDateString()}
                          </div>
                        </div>
                      </div>
                      <div
                        className={`font-semibold ${isIncome ? 'text-success' : 'text-foreground'}`}
                      >
                        {isIncome ? '+' : '-'}
                        {currency(Math.abs(transaction.amount), transaction.currency)}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>
      </div>
    ),

    upcoming_bills: (
      <div key="upcoming_bills" data-testid="widget-upcoming_bills">
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader>
            <div className="flex items-center justify-between">
              <FinancialCardTitle className="section-title">Upcoming Bills</FinancialCardTitle>
              <Button variant="ghost" size="sm" onClick={() => navigate('/bills')}>
                Manage
              </Button>
            </div>
            <FinancialCardDescription>Active bills due soon</FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            {upcomingBills.length === 0 ? (
              <div className="text-sm text-muted-foreground">No upcoming bills.</div>
            ) : (
              <div className="space-y-3">
                {upcomingBills.map((bill) => (
                  <div
                    key={bill.id}
                    className="interactive-row flex items-center justify-between"
                  >
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-warning-light text-warning">
                        <AlertTriangle className="w-4 h-4" />
                      </div>
                      <div>
                        <div className="font-medium text-foreground text-sm">{bill.name}</div>
                        <div className="text-xs text-muted-foreground">
                          Due {new Date(bill.next_due_date).toLocaleDateString()}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-foreground">
                      {currency(bill.amount, bill.currency)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </FinancialCardContent>
          <FinancialCardFooter>
            <Button
              variant="financial"
              size="sm"
              className="w-full"
              onClick={() => navigate('/bills')}
            >
              <Plus className="w-4 h-4" />
              Add New Bill
            </Button>
          </FinancialCardFooter>
        </FinancialCard>
      </div>
    ),

    category_breakdown: (
      <div key="category_breakdown" data-testid="widget-category_breakdown">
        <FinancialCard variant="financial" className="fade-in-up">
          <FinancialCardHeader>
            <FinancialCardTitle className="section-title">Category Breakdown</FinancialCardTitle>
            <FinancialCardDescription>
              Expense mix for {data?.period?.month || month}
            </FinancialCardDescription>
          </FinancialCardHeader>
          <FinancialCardContent>
            {categoryBreakdown.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                No category data for this month.
              </div>
            ) : (
              <div className="space-y-3">
                {categoryBreakdown.slice(0, 6).map((row) => (
                  <div
                    key={`${row.category_id ?? 'uncat'}-${row.category_name}`}
                    className="space-y-1"
                  >
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-foreground">{row.category_name}</span>
                      <span className="text-muted-foreground">
                        {currency(row.amount)} ({row.share_pct.toFixed(0)}%)
                      </span>
                    </div>
                    <div className="chart-track h-2">
                      <div
                        className="chart-fill-primary h-2"
                        style={{
                          width: `${Math.max(2, Math.min(100, row.share_pct))}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>
      </div>
    ),
  };

  // Sidebar widget IDs — rendered in a stacked column
  const SIDEBAR_WIDGET_IDS = new Set(['upcoming_bills', 'category_breakdown']);
  // Full-width widget IDs
  const FULLWIDTH_WIDGET_IDS = new Set(['summary_cards']);

  // Partition visible widgets into layout zones, preserving user-defined order
  const sidebarWidgets = widgets.filter(
    (w) => w.visible && SIDEBAR_WIDGET_IDS.has(w.id),
  );
  const mainWidgets = widgets.filter(
    (w) => w.visible && !SIDEBAR_WIDGET_IDS.has(w.id) && !FULLWIDTH_WIDGET_IDS.has(w.id),
  );
  const fullWidthWidgets = widgets.filter(
    (w) => w.visible && FULLWIDTH_WIDGET_IDS.has(w.id),
  );

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Financial Dashboard</h1>
            <p className="page-subtitle">
              Live overview for {data?.period?.month || 'current period'}.
            </p>
          </div>
          <div className="flex gap-3 flex-wrap">
            <label className="sr-only" htmlFor="dashboard-month">
              Dashboard month
            </label>
            <input
              id="dashboard-month"
              aria-label="Dashboard month"
              type="month"
              className="input h-9 w-[160px]"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => setMonth(new Date().toISOString().slice(0, 7))}
            >
              <Calendar className="w-4 h-4" />
              This Month
            </Button>
            <Button
              variant="financial"
              size="sm"
              onClick={() => navigate('/expenses')}
            >
              <Plus className="w-4 h-4" />
              Add Transaction
            </Button>

            {/* Customize dashboard dialog */}
            <Dialog open={customizerOpen} onOpenChange={handleOpenChange}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm" aria-label="Customize dashboard">
                  <Settings2 className="w-4 h-4" />
                  Customize
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle>Dashboard Layout</DialogTitle>
                  <DialogDescription>
                    Choose which widgets to show and set their order.
                  </DialogDescription>
                </DialogHeader>
                <DashboardCustomizer
                  widgets={draft}
                  saving={savingPrefs}
                  onToggle={handleDraftToggle}
                  onMoveUp={handleDraftMoveUp}
                  onMoveDown={handleDraftMoveDown}
                  onSave={handleSavePrefs}
                />
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {error && (
        <div className="error mb-6">{error}. Showing empty fallback state.</div>
      )}

      {data?.errors && data.errors.length > 0 && (
        <div className="card mb-6 text-sm text-warning">
          Some widgets are temporarily unavailable: {data.errors.join(', ')}
        </div>
      )}

      {/* Full-width widgets (summary cards) */}
      {fullWidthWidgets.map((w) => widgetContent[w.id])}

      {/* Main 3-column layout: 2-col main + 1-col sidebar */}
      {(mainWidgets.length > 0 || sidebarWidgets.length > 0) && (
        <div className="grid lg:grid-cols-3 gap-8">
          {mainWidgets.length > 0 && (
            <div className="lg:col-span-2 space-y-6">
              {mainWidgets.map((w) => widgetContent[w.id])}
            </div>
          )}
          {sidebarWidgets.length > 0 && (
            <div className="space-y-6">
              {sidebarWidgets.map((w) => widgetContent[w.id])}
            </div>
          )}
        </div>
      )}

      {/* No visible widgets fallback */}
      {fullWidthWidgets.length === 0 &&
        mainWidgets.length === 0 &&
        sidebarWidgets.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Settings2 className="w-12 h-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground text-sm">
              All widgets are hidden. Open{' '}
              <button
                className="underline text-primary"
                onClick={() => handleOpenChange(true)}
              >
                Customize
              </button>{' '}
              to show them again.
            </p>
          </div>
        )}
    </div>
  );
}
