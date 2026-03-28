import { useState, useMemo } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  TrendingUp,
  TrendingDown,
  Calendar,
  DollarSign,
  PieChart,
  AlertTriangle,
  CheckCircle2,
  Info,
  Lightbulb,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Wallet,
  Target,
} from 'lucide-react';
import type {
  WeeklySummary,
  WeeklySummaryResponse,
  WeeklyCategoryBreakdown,
  WeeklyTrend,
  WeeklyInsight,
} from '@/api/weekly-summary';

// --- Helpers ---------------------------------------------------------------

function getWeekStart(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Monday
  d.setDate(diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function getWeekEnd(weekStart: Date): Date {
  const d = new Date(weekStart);
  d.setDate(d.getDate() + 6);
  return d;
}

function formatDate(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

// --- Mock Data -------------------------------------------------------------

const CATEGORY_COLORS: Record<string, string> = {
  Housing: '#6366f1',
  Food: '#22c55e',
  Transportation: '#f59e0b',
  Entertainment: '#ec4899',
  Healthcare: '#06b6d4',
  Shopping: '#8b5cf6',
  Utilities: '#f97316',
  Other: '#64748b',
};

function generateMockData(weekStart: Date): WeeklySummaryResponse {
  const weekEnd = getWeekEnd(weekStart);

  const generateBreakdown = (): WeeklyCategoryBreakdown[] => {
    const categories = ['Housing', 'Food', 'Transportation', 'Entertainment', 'Healthcare', 'Shopping', 'Utilities'];
    const total = 1200 + Math.random() * 600;
    return categories.map((cat, i) => {
      const amount = (total / categories.length) * (0.5 + Math.random());
      return {
        category: cat,
        amount: Math.round(amount),
        percentage: (amount / total) * 100,
        change: Math.round((Math.random() - 0.5) * 30 * 10) / 10,
        transactionCount: Math.floor(2 + Math.random() * 8),
      };
    }).sort((a, b) => b.amount - a.amount);
  };

  const generateInsights = (): WeeklyInsight[] => {
    const insights: WeeklyInsight[] = [
      {
        type: 'warning',
        title: 'Dining Out Increased',
        description: 'Food spending is up 23% compared to last week. Consider meal prepping to save.',
        metric: '+$127',
        change: 23,
      },
      {
        type: 'success',
        title: 'Savings Goal On Track',
        description: 'You saved 18% of your income this week. Keep it up!',
        metric: '$340',
        change: 5,
      },
      {
        type: 'info',
        title: 'Recurring Bills',
        description: '3 bills are due next week totaling $450.',
      },
      {
        type: 'tip',
        title: 'Cashback Opportunity',
        description: 'Switch your grocery spending to a 3% cashback card for ~$12/month savings.',
      },
    ];
    return insights.slice(0, 2 + Math.floor(Math.random() * 3));
  };

  const generateTrends = (): WeeklyTrend[] => {
    const trends: WeeklyTrend[] = [];
    for (let i = 11; i >= 0; i--) {
      const w = new Date(weekStart);
      w.setDate(w.getDate() - i * 7);
      const income = 2000 + Math.random() * 500;
      const expenses = 1000 + Math.random() * 800;
      trends.push({
        week: w.toISOString().slice(0, 10),
        income: Math.round(income),
        expenses: Math.round(expenses),
        savings: Math.round(income - expenses),
        savingsRate: Math.round(((income - expenses) / income) * 100),
      });
    }
    return trends;
  };

  const breakdown = generateBreakdown();
  const totalExpenses = breakdown.reduce((s, c) => s + c.amount, 0);
  const totalIncome = 2200 + Math.round(Math.random() * 400);
  const netSavings = totalIncome - totalExpenses;
  const savingsRate = Math.round((netSavings / totalIncome) * 100);
  const budgetLimit = 1500;
  const budgetAdherence = Math.round((totalExpenses / budgetLimit) * 100);

  const current: WeeklySummary = {
    weekStart: weekStart.toISOString(),
    weekEnd: weekEnd.toISOString(),
    totalIncome,
    totalExpenses,
    netSavings,
    savingsRate,
    topCategories: breakdown,
    budgetAdherence,
    budgetStatus: budgetAdherence <= 90 ? 'under' : budgetAdherence <= 105 ? 'on-track' : 'over',
    insights: generateInsights(),
    trends: generateTrends(),
    transactionCount: breakdown.reduce((s, c) => s + c.transactionCount, 0),
  };

  const prevBreakdown = generateBreakdown();
  const prevTotalExpenses = prevBreakdown.reduce((s, c) => s + c.amount, 0);
  const prevTotalIncome = totalIncome - Math.round((Math.random() - 0.5) * 200);

  const previous: WeeklySummary = {
    weekStart: new Date(weekStart.getTime() - 7 * 86400000).toISOString(),
    weekEnd: new Date(weekEnd.getTime() - 7 * 86400000).toISOString(),
    totalIncome: prevTotalIncome,
    totalExpenses: prevTotalExpenses,
    netSavings: prevTotalIncome - prevTotalExpenses,
    savingsRate: Math.round(((prevTotalIncome - prevTotalExpenses) / prevTotalIncome) * 100),
    topCategories: prevBreakdown,
    budgetAdherence: Math.round((prevTotalExpenses / budgetLimit) * 100),
    budgetStatus: 'on-track',
    insights: [],
    trends: [],
    transactionCount: prevBreakdown.reduce((s, c) => s + c.transactionCount, 0),
  };

  return { current, previous };
}

// --- Insight Icon ----------------------------------------------------------

function InsightIcon({ type }: { type: WeeklyInsight['type'] }) {
  switch (type) {
    case 'warning':
      return <AlertTriangle className="h-5 w-5 text-warning" />;
    case 'success':
      return <CheckCircle2 className="h-5 w-5 text-success" />;
    case 'info':
      return <Info className="h-5 w-5 text-primary" />;
    case 'tip':
      return <Lightbulb className="h-5 w-5 text-accent" />;
  }
}

// --- Main Component --------------------------------------------------------

export function WeeklySummaryPage() {
  const [currentWeek, setCurrentWeek] = useState<Date>(() => getWeekStart(new Date()));

  const data = useMemo(() => generateMockData(currentWeek), [currentWeek]);

  const { current, previous } = data;

  const weekChange = useMemo(() => {
    if (!previous) return null;
    const incomeChange = ((current.totalIncome - previous.totalIncome) / previous.totalIncome) * 100;
    const expenseChange = ((current.totalExpenses - previous.totalExpenses) / previous.totalExpenses) * 100;
    const savingsChange = current.netSavings - previous.netSavings;
    return { incomeChange, expenseChange, savingsChange };
  }, [current, previous]);

  const goPrevWeek = () => {
    const d = new Date(currentWeek);
    d.setDate(d.getDate() - 7);
    setCurrentWeek(d);
  };

  const goNextWeek = () => {
    const d = new Date(currentWeek);
    d.setDate(d.getDate() + 7);
    if (d <= getWeekStart(new Date())) setCurrentWeek(d);
  };

  const weekLabel = `${formatDate(currentWeek)} – ${formatDate(getWeekEnd(currentWeek))}`;
  const isCurrentWeek = currentWeek.getTime() === getWeekStart(new Date()).getTime();

  return (
    <div className="container-financial py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Weekly Summary</h1>
          <p className="text-muted-foreground">Financial trends and insights at a glance.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={goPrevWeek}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex items-center gap-2 rounded-lg border px-4 py-2">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{weekLabel}</span>
            {isCurrentWeek && <Badge variant="outline">Current</Badge>}
          </div>
          <Button variant="outline" size="icon" onClick={goNextWeek} disabled={isCurrentWeek}>
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <DollarSign className="h-3 w-3" /> Income
            </FinancialCardDescription>
            <FinancialCardTitle className="text-2xl text-success">
              {formatCurrency(current.totalIncome)}
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            {weekChange && (
              <p className={`text-xs ${weekChange.incomeChange >= 0 ? 'text-success' : 'text-destructive'}`}>
                {formatPercent(weekChange.incomeChange)} vs last week
              </p>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <Wallet className="h-3 w-3" /> Expenses
            </FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              {formatCurrency(current.totalExpenses)}
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            {weekChange && (
              <p className={`text-xs ${weekChange.expenseChange <= 0 ? 'text-success' : 'text-destructive'}`}>
                {formatPercent(weekChange.expenseChange)} vs last week
              </p>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <TrendingUp className="h-3 w-3" /> Net Savings
            </FinancialCardDescription>
            <FinancialCardTitle className={`text-2xl ${current.netSavings >= 0 ? 'text-success' : 'text-destructive'}`}>
              {formatCurrency(current.netSavings)}
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <p className="text-xs text-muted-foreground">{current.savingsRate}% savings rate</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-2">
            <FinancialCardDescription className="flex items-center gap-1">
              <Target className="h-3 w-3" /> Budget
            </FinancialCardDescription>
            <FinancialCardTitle className="text-2xl">
              {current.budgetAdherence}%
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <Badge
              variant={
                current.budgetStatus === 'under'
                  ? 'default'
                  : current.budgetStatus === 'on-track'
                  ? 'secondary'
                  : 'destructive'
              }
            >
              {current.budgetStatus === 'under'
                ? 'Under Budget'
                : current.budgetStatus === 'on-track'
                ? 'On Track'
                : 'Over Budget'}
            </Badge>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Category Breakdown */}
        <div className="lg:col-span-2">
          <FinancialCard>
            <FinancialCardHeader>
              <FinancialCardTitle className="flex items-center gap-2">
                <PieChart className="h-5 w-5" />
                Spending by Category
              </FinancialCardTitle>
              <FinancialCardDescription>{current.transactionCount} transactions this week</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="space-y-4">
                {current.topCategories.map((cat) => {
                  const barWidth = (cat.amount / current.topCategories[0].amount) * 100;
                  const color = CATEGORY_COLORS[cat.category] || CATEGORY_COLORS.Other;
                  return (
                    <div key={cat.category} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
                          <span className="font-medium">{cat.category}</span>
                          <span className="text-muted-foreground">({cat.transactionCount})</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`text-xs ${cat.change >= 0 ? 'text-destructive' : 'text-success'}`}>
                            {formatPercent(cat.change)}
                          </span>
                          <span className="font-medium">{formatCurrency(cat.amount)}</span>
                        </div>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div
                          className="h-2 rounded-full transition-all"
                          style={{ width: `${barWidth}%`, backgroundColor: color }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </FinancialCardContent>
          </FinancialCard>
        </div>

        {/* Insights */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Lightbulb className="h-5 w-5" />
            Insights & Tips
          </h3>
          {current.insights.map((insight, i) => (
            <FinancialCard key={i}>
              <FinancialCardContent className="pt-4">
                <div className="flex gap-3">
                  <InsightIcon type={insight.type} />
                  <div className="space-y-1">
                    <p className="text-sm font-medium">{insight.title}</p>
                    <p className="text-xs text-muted-foreground">{insight.description}</p>
                    {insight.metric && (
                      <div className="flex items-center gap-2 pt-1">
                        <Badge variant="outline" className="text-xs">
                          {insight.metric}
                        </Badge>
                        {insight.change !== undefined && (
                          <span className={`text-xs ${insight.change >= 0 ? 'text-destructive' : 'text-success'}`}>
                            {formatPercent(insight.change)}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      </div>

      {/* 12-Week Trend */}
      <FinancialCard>
        <FinancialCardHeader>
          <FinancialCardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            12-Week Trend
          </FinancialCardTitle>
          <FinancialCardDescription>Income vs Expenses over the past 12 weeks</FinancialCardDescription>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="flex items-end gap-1 h-40">
            {current.trends.map((trend, i) => {
              const maxVal = Math.max(...current.trends.map((t) => Math.max(t.income, t.expenses)));
              const incomeH = (trend.income / maxVal) * 100;
              const expenseH = (trend.expenses / maxVal) * 100;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5 group relative">
                  <div className="flex gap-0.5 items-end h-full w-full">
                    <div
                      className="flex-1 rounded-t bg-success/60 group-hover:bg-success transition-colors"
                      style={{ height: `${incomeH}%` }}
                      title={`Income: ${formatCurrency(trend.income)}`}
                    />
                    <div
                      className="flex-1 rounded-t bg-primary/60 group-hover:bg-primary transition-colors"
                      style={{ height: `${expenseH}%` }}
                      title={`Expenses: ${formatCurrency(trend.expenses)}`}
                    />
                  </div>
                  <span className="text-[9px] text-muted-foreground">
                    {new Date(trend.week).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-4 mt-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <div className="h-3 w-3 rounded bg-success/60" />
              Income
            </div>
            <div className="flex items-center gap-1">
              <div className="h-3 w-3 rounded bg-primary/60" />
              Expenses
            </div>
          </div>
        </FinancialCardContent>
      </FinancialCard>
    </div>
  );
}
