import { useEffect, useState } from 'react';
import { fetchWeeklyDigest, type WeeklyDigest } from '../api/digest';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '../components/ui/financial-card';

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

function formatDate(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

export default function WeeklyDigestPage() {
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchWeeklyDigest()
      .then(setDigest)
      .catch((err) => setError(err.message ?? 'Failed to load digest'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-muted-foreground">Loading weekly digest...</p>
      </div>
    );
  }

  if (error || !digest) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-destructive">{error ?? 'No data available'}</p>
      </div>
    );
  }

  const { period, totals, comparison, category_breakdown, daily_spending, highlights } = digest;

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Weekly Digest</h1>
        <p className="text-muted-foreground">
          {formatDate(period.start)} — {formatDate(period.end)}
        </p>
      </div>

      {/* Highlights */}
      {highlights.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle>Highlights</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <ul className="space-y-2">
              {highlights.map((h, i) => (
                <li key={i} className="text-sm">
                  {h}
                </li>
              ))}
            </ul>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardDescription>Income</FinancialCardDescription>
            <FinancialCardTitle className="text-green-600">
              {formatCurrency(totals.income)}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardDescription>Expenses</FinancialCardDescription>
            <FinancialCardTitle className="text-red-600">
              {formatCurrency(totals.expenses)}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>

        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardDescription>Net</FinancialCardDescription>
            <FinancialCardTitle className={totals.net >= 0 ? 'text-green-600' : 'text-red-600'}>
              {formatCurrency(totals.net)}
            </FinancialCardTitle>
          </FinancialCardHeader>
        </FinancialCard>
      </div>

      {/* Week-over-week comparison */}
      {comparison.change_percent !== null && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle>vs Previous Week</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="flex items-center gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Previous week</p>
                <p className="font-medium">{formatCurrency(comparison.previous_week_expenses)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Change</p>
                <p
                  className={`font-medium ${comparison.change <= 0 ? 'text-green-600' : 'text-red-600'}`}
                >
                  {comparison.change > 0 ? '+' : ''}
                  {formatCurrency(comparison.change)} ({comparison.change_percent > 0 ? '+' : ''}
                  {comparison.change_percent}%)
                </p>
              </div>
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Category breakdown */}
      {category_breakdown.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle>Spending by Category</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-3">
              {category_breakdown.map((cat) => (
                <div key={cat.category} className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{cat.category}</p>
                    <p className="text-xs text-muted-foreground">{cat.count} transactions</p>
                  </div>
                  <p className="font-medium">{formatCurrency(cat.total)}</p>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* Daily spending */}
      {daily_spending.length > 0 && (
        <FinancialCard>
          <FinancialCardHeader>
            <FinancialCardTitle>Daily Spending</FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent>
            <div className="space-y-2">
              {daily_spending.map((day) => (
                <div key={day.date} className="flex items-center justify-between">
                  <p className="text-sm">{formatDate(day.date)}</p>
                  <p className="font-medium">{formatCurrency(day.amount)}</p>
                </div>
              ))}
            </div>
          </FinancialCardContent>
        </FinancialCard>
      )}
    </div>
  );
}
