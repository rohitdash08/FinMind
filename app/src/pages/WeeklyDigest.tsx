import { useState } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { ArrowUpRight, ArrowDownRight, TrendingUp, TrendingDown, DollarSign, Download, Share2, Calendar, ShoppingCart, Home, Car, Utensils, Dumbbell, Zap, MoreHorizontal } from 'lucide-react';

interface CategorySpend {
  name: string;
  amount: number;
  prevAmount: number;
  budget?: number;
  icon: React.ElementType;
  color: string;
}

interface WeekDigest {
  weekLabel: string;
  startDate: string;
  endDate: string;
  totalSpent: number;
  prevTotalSpent: number;
  totalIncome: number;
  categories: CategorySpend[];
  topInsight: string;
}

const weekData: WeekDigest[] = [
  {
    weekLabel: 'This Week',
    startDate: '2026-03-27',
    endDate: '2026-04-02',
    totalSpent: 1247.83,
    prevTotalSpent: 1089.40,
    totalIncome: 3200.00,
    topInsight: 'Dining out increased 34% — you spent $287 at restaurants this week vs $214 last week.',
    categories: [
      { name: 'Food & Dining', amount: 287.40, prevAmount: 213.80, budget: 300, icon: Utensils, color: 'text-warning' },
      { name: 'Housing', amount: 320.00, prevAmount: 320.00, budget: 350, icon: Home, color: 'text-primary' },
      { name: 'Transportation', amount: 189.50, prevAmount: 145.20, budget: 200, icon: Car, color: 'text-accent' },
      { name: 'Shopping', amount: 234.93, prevAmount: 187.40, budget: 250, icon: ShoppingCart, color: 'text-destructive' },
      { name: 'Health & Fitness', amount: 89.00, prevAmount: 89.00, budget: 100, icon: Dumbbell, color: 'text-success' },
      { name: 'Utilities', amount: 127.00, prevAmount: 134.00, budget: 150, icon: Zap, color: 'text-muted-foreground' },
    ],
  },
  {
    weekLabel: 'Last Week',
    startDate: '2026-03-20',
    endDate: '2026-03-26',
    totalSpent: 1089.40,
    prevTotalSpent: 1134.20,
    totalIncome: 0,
    topInsight: 'Great week! Spending dropped 4% vs the week before. Shopping and dining were well under budget.',
    categories: [
      { name: 'Food & Dining', amount: 213.80, prevAmount: 241.00, budget: 300, icon: Utensils, color: 'text-warning' },
      { name: 'Housing', amount: 320.00, prevAmount: 320.00, budget: 350, icon: Home, color: 'text-primary' },
      { name: 'Transportation', amount: 145.20, prevAmount: 167.50, budget: 200, icon: Car, color: 'text-accent' },
      { name: 'Shopping', amount: 187.40, prevAmount: 203.70, budget: 250, icon: ShoppingCart, color: 'text-destructive' },
      { name: 'Health & Fitness', amount: 89.00, prevAmount: 89.00, budget: 100, icon: Dumbbell, color: 'text-success' },
      { name: 'Utilities', amount: 134.00, prevAmount: 113.00, budget: 150, icon: Zap, color: 'text-muted-foreground' },
    ],
  },
];

function pctChange(current: number, prev: number): number {
  if (prev === 0) return 0;
  return Math.round(((current - prev) / prev) * 100);
}

function formatCurrency(n: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

export function WeeklyDigest() {
  const [weekIndex, setWeekIndex] = useState(0);
  const digest = weekData[weekIndex];

  const change = pctChange(digest.totalSpent, digest.prevTotalSpent);
  const topCategories = [...digest.categories].sort((a, b) => b.amount - a.amount).slice(0, 3);
  const savingsRate = digest.totalIncome > 0
    ? Math.round(((digest.totalIncome - digest.totalSpent) / digest.totalIncome) * 100)
    : null;

  function handleExportCSV() {
    const rows = [
      ['Category', 'This Week', 'Last Week', 'Change %', 'Budget'],
      ...digest.categories.map(c => [
        c.name,
        c.amount.toFixed(2),
        c.prevAmount.toFixed(2),
        `${pctChange(c.amount, c.prevAmount)}%`,
        c.budget ? c.budget.toFixed(2) : 'N/A',
      ]),
      ['TOTAL', digest.totalSpent.toFixed(2), digest.prevTotalSpent.toFixed(2), `${change}%`, ''],
    ];
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `weekly-digest-${digest.startDate}.csv`;
    a.click();
  }

  function handleShare() {
    const text = `📊 My Weekly Spending Digest (${digest.startDate} – ${digest.endDate})\n\n`
      + `Total spent: ${formatCurrency(digest.totalSpent)} (${change >= 0 ? '+' : ''}${change}% vs last week)\n\n`
      + `Top categories:\n`
      + topCategories.map(c => `• ${c.name}: ${formatCurrency(c.amount)}`).join('\n')
      + `\n\nTracked with FinMind 💰`;
    if (navigator.share) {
      navigator.share({ title: 'Weekly Digest', text });
    } else {
      navigator.clipboard.writeText(text);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Weekly Digest</h1>
          <p className="text-muted-foreground">
            {digest.startDate} — {digest.endDate}
          </p>
        </div>
        <div className="flex gap-2">
          <div className="flex rounded-md border overflow-hidden">
            {weekData.map((w, i) => (
              <button key={i}
                className={`px-3 py-1.5 text-sm transition-colors ${i === weekIndex ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
                onClick={() => setWeekIndex(i)}>
                {w.weekLabel}
              </button>
            ))}
          </div>
          <Button variant="outline" size="sm" onClick={handleExportCSV} className="gap-1">
            <Download className="h-3 w-3" /> CSV
          </Button>
          <Button variant="outline" size="sm" onClick={handleShare} className="gap-1">
            <Share2 className="h-3 w-3" /> Share
          </Button>
        </div>
      </div>

      {/* Top insight banner */}
      <div className="rounded-lg border bg-muted/50 px-4 py-3 flex gap-3 items-start">
        <TrendingUp className="h-4 w-4 mt-0.5 text-primary shrink-0" />
        <p className="text-sm">{digest.topInsight}</p>
      </div>

      {/* Summary row */}
      <div className="grid gap-4 md:grid-cols-4">
        <FinancialCard>
          <FinancialCardHeader className="pb-1">
            <FinancialCardTitle className="text-sm">Total Spent</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{formatCurrency(digest.totalSpent)}</div>
            <div className={`text-xs flex items-center gap-0.5 mt-1 ${change > 0 ? 'text-destructive' : 'text-success'}`}>
              {change > 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
              {Math.abs(change)}% vs last week
            </div>
          </FinancialCardContent>
        </FinancialCard>

        {savingsRate !== null && (
          <FinancialCard>
            <FinancialCardHeader className="pb-1">
              <FinancialCardTitle className="text-sm">Savings Rate</FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="text-2xl font-bold text-success">{savingsRate}%</div>
              <p className="text-xs text-muted-foreground mt-1">
                {formatCurrency(digest.totalIncome - digest.totalSpent)} saved
              </p>
            </FinancialCardContent>
          </FinancialCard>
        )}

        <FinancialCard>
          <FinancialCardHeader className="pb-1">
            <FinancialCardTitle className="text-sm">Categories</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-2xl font-bold">{digest.categories.length}</div>
            <p className="text-xs text-muted-foreground mt-1">spending areas tracked</p>
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader className="pb-1">
            <FinancialCardTitle className="text-sm">Biggest Spend</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="text-lg font-bold truncate">{topCategories[0]?.name}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {formatCurrency(topCategories[0]?.amount ?? 0)}
            </p>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      {/* Top 3 categories highlight */}
      <div>
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          <Calendar className="h-4 w-4" /> Top Spending Categories
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          {topCategories.map((cat, i) => {
            const catChange = pctChange(cat.amount, cat.prevAmount);
            const budgetPct = cat.budget ? Math.round((cat.amount / cat.budget) * 100) : null;
            const Icon = cat.icon;
            return (
              <FinancialCard key={cat.name} className={budgetPct && budgetPct > 90 ? 'border-destructive/50' : ''}>
                <FinancialCardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <div className="rounded-full bg-muted p-1.5">
                      <Icon className={`h-3.5 w-3.5 ${cat.color}`} />
                    </div>
                    <div>
                      <FinancialCardTitle className="text-sm">{cat.name}</FinancialCardTitle>
                      <FinancialCardDescription>#{i + 1} this week</FinancialCardDescription>
                    </div>
                  </div>
                </FinancialCardHeader>
                <FinancialCardContent className="space-y-2">
                  <div className="flex justify-between items-baseline">
                    <span className="text-xl font-bold">{formatCurrency(cat.amount)}</span>
                    <span className={`text-xs flex items-center gap-0.5 ${catChange > 0 ? 'text-destructive' : 'text-success'}`}>
                      {catChange > 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      {Math.abs(catChange)}%
                    </span>
                  </div>
                  {cat.budget && (
                    <div>
                      <div className="flex justify-between text-xs text-muted-foreground mb-1">
                        <span>Budget</span>
                        <span>{budgetPct}% used</span>
                      </div>
                      <Progress value={Math.min(budgetPct ?? 0, 100)}
                        className={budgetPct && budgetPct > 90 ? '[&>div]:bg-destructive' : ''} />
                    </div>
                  )}
                </FinancialCardContent>
              </FinancialCard>
            );
          })}
        </div>
      </div>

      {/* Full category breakdown */}
      <div>
        <h2 className="font-semibold mb-3">All Categories</h2>
        <div className="space-y-2">
          {digest.categories.map(cat => {
            const catChange = pctChange(cat.amount, cat.prevAmount);
            const budgetPct = cat.budget ? Math.round((cat.amount / cat.budget) * 100) : null;
            const Icon = cat.icon;
            return (
              <FinancialCard key={cat.name} className="py-3">
                <FinancialCardContent className="py-0">
                  <div className="flex items-center gap-3">
                    <Icon className={`h-4 w-4 shrink-0 ${cat.color}`} />
                    <span className="flex-1 font-medium text-sm">{cat.name}</span>
                    {cat.budget && (
                      <div className="flex-1 max-w-[140px]">
                        <Progress value={Math.min(budgetPct ?? 0, 100)}
                          className={`h-1.5 ${budgetPct && budgetPct > 90 ? '[&>div]:bg-destructive' : ''}`} />
                      </div>
                    )}
                    <span className="text-sm font-semibold w-24 text-right">{formatCurrency(cat.amount)}</span>
                    <span className={`text-xs w-14 text-right flex items-center justify-end gap-0.5 ${catChange > 0 ? 'text-destructive' : 'text-success'}`}>
                      {catChange > 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      {Math.abs(catChange)}%
                    </span>
                    {cat.budget && (
                      <Badge variant={budgetPct && budgetPct > 100 ? 'destructive' : budgetPct && budgetPct > 80 ? 'outline' : 'secondary'}
                        className="w-16 justify-center text-xs">
                        {budgetPct}%
                      </Badge>
                    )}
                  </div>
                </FinancialCardContent>
              </FinancialCard>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default WeeklyDigest;
