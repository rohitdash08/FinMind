import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { formatMoney } from '@/lib/currency';
import {
  getSavingsOpportunities,
  type SavingsOpportunity,
  type SavingsOpportunitiesResponse,
} from '@/api/insights';

const TYPE_LABELS: Record<string, string> = {
  month_over_month_increase: 'Spending Spike',
  high_frequency_small_purchases: 'Latte Factor',
  subscription_duplicate: 'Possible Duplicate',
  above_average_spending: 'Above Average',
};

const TYPE_VARIANTS: Record<string, 'warning' | 'destructive' | 'financial'> = {
  month_over_month_increase: 'warning',
  high_frequency_small_purchases: 'financial',
  subscription_duplicate: 'destructive',
  above_average_spending: 'warning',
};

function TrendBadge({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
      {label}: {value}
    </span>
  );
}

function OpportunityCard({ opportunity }: { opportunity: SavingsOpportunity }) {
  const variant = TYPE_VARIANTS[opportunity.type] ?? 'financial';
  const badge = TYPE_LABELS[opportunity.type] ?? opportunity.type;
  const trend = opportunity.trend;

  return (
    <FinancialCard variant={variant} data-testid="savings-opportunity-card">
      <FinancialCardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <FinancialCardTitle className="text-sm">{opportunity.title}</FinancialCardTitle>
          <span className="rounded-full bg-background/60 px-2 py-0.5 text-xs font-medium">
            {badge}
          </span>
        </div>
        <FinancialCardDescription>{opportunity.category ?? 'General'}</FinancialCardDescription>
      </FinancialCardHeader>
      <FinancialCardContent>
        <p className="text-sm mb-3">{opportunity.description}</p>
        <div className="flex items-center justify-between">
          <div className="font-semibold text-lg">
            Save {formatMoney(opportunity.potential_savings)}
          </div>
          <div className="flex flex-wrap gap-1">
            {trend.change_pct != null && (
              <TrendBadge label="Change" value={`${trend.change_pct}%`} />
            )}
            {trend.transaction_count != null && (
              <TrendBadge label="Txns" value={String(trend.transaction_count)} />
            )}
            {trend.occurrences != null && (
              <TrendBadge label="Occurrences" value={String(trend.occurrences)} />
            )}
            {trend.months_in_average != null && (
              <TrendBadge label="Avg period" value={`${trend.months_in_average}mo`} />
            )}
          </div>
        </div>
      </FinancialCardContent>
    </FinancialCard>
  );
}

export function SavingsOpportunities({ month }: { month?: string }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<SavingsOpportunitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getSavingsOpportunities({ month })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load savings opportunities');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [month]);

  if (loading) {
    return <div className="card" data-testid="savings-loading">Analyzing spending patterns...</div>;
  }

  if (error) {
    return <div className="card text-red-600" data-testid="savings-error">{error}</div>;
  }

  if (!data || data.opportunities.length === 0) {
    return (
      <FinancialCard variant="success" data-testid="savings-empty">
        <FinancialCardHeader>
          <FinancialCardTitle>No Savings Opportunities Found</FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          <p className="text-sm text-muted-foreground">
            Your spending looks healthy this month. Keep it up!
          </p>
        </FinancialCardContent>
      </FinancialCard>
    );
  }

  const totalSavings = data.opportunities.reduce((sum, o) => sum + o.potential_savings, 0);

  return (
    <div className="space-y-4" data-testid="savings-opportunities">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          Savings Opportunities
        </h2>
        <span className="text-sm text-muted-foreground">
          Potential total savings: {formatMoney(totalSavings)}
        </span>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {data.opportunities.map((opp, idx) => (
          <OpportunityCard key={`${opp.type}-${idx}`} opportunity={opp} />
        ))}
      </div>
    </div>
  );
}
