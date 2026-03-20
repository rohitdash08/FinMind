import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { formatMoney } from '@/lib/currency';
import {
  getSpendingBreakdown,
  type SpendingBreakdownResponse,
  type SpendingBucket,
} from '@/api/expenses';

// ---------------------------------------------------------------------------
// SVG Donut Chart
// ---------------------------------------------------------------------------
type Slice = { label: string; value: number; color: string };

function DonutChart({ slices }: { slices: Slice[] }) {
  const total = slices.reduce((s, sl) => s + sl.value, 0);
  if (total === 0) {
    return (
      <svg viewBox="0 0 120 120" className="mx-auto h-48 w-48" role="img" aria-label="Spending donut chart">
        <circle cx="60" cy="60" r="50" fill="none" stroke="#e5e7eb" strokeWidth="20" />
        <text x="60" y="64" textAnchor="middle" className="fill-muted-foreground text-[10px]">
          No data
        </text>
      </svg>
    );
  }

  const circumference = 2 * Math.PI * 50;
  let offset = 0;

  return (
    <svg viewBox="0 0 120 120" className="mx-auto h-48 w-48" role="img" aria-label="Spending donut chart">
      {slices.map((sl) => {
        const pct = sl.value / total;
        const dashLength = pct * circumference;
        const currentOffset = offset;
        offset += dashLength;
        return (
          <circle
            key={sl.label}
            cx="60"
            cy="60"
            r="50"
            fill="none"
            stroke={sl.color}
            strokeWidth="20"
            strokeDasharray={`${dashLength} ${circumference - dashLength}`}
            strokeDashoffset={-currentOffset}
            transform="rotate(-90 60 60)"
          />
        );
      })}
      <text x="60" y="58" textAnchor="middle" className="fill-foreground text-[11px] font-semibold">
        {formatMoney(total)}
      </text>
      <text x="60" y="70" textAnchor="middle" className="fill-muted-foreground text-[8px]">
        Total
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Category detail list (expandable)
// ---------------------------------------------------------------------------
function BucketDetail({
  title,
  bucket,
  color,
  dotClass,
}: {
  title: string;
  bucket: SpendingBucket;
  color: string;
  dotClass: string;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <FinancialCard variant="financial" size="sm">
      <FinancialCardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`inline-block h-3 w-3 rounded-full ${dotClass}`} />
            <FinancialCardTitle className="text-sm">{title}</FinancialCardTitle>
          </div>
          <span className="font-semibold">{formatMoney(bucket.total)}</span>
        </div>
      </FinancialCardHeader>
      <FinancialCardContent>
        {bucket.categories.length > 0 ? (
          <>
            <button
              type="button"
              className="text-xs text-muted-foreground underline"
              onClick={() => setExpanded((prev) => !prev)}
              aria-expanded={expanded}
              data-testid={`toggle-${title.toLowerCase()}`}
            >
              {expanded ? 'Hide categories' : `Show ${bucket.categories.length} categories`}
            </button>
            {expanded && (
              <ul className="mt-2 space-y-1" data-testid={`list-${title.toLowerCase()}`}>
                {bucket.categories.map((cat) => (
                  <li
                    key={cat.name}
                    className="flex items-center justify-between rounded-md px-2 py-1 text-sm odd:bg-muted/40"
                  >
                    <span>{cat.name}</span>
                    <span className="font-medium">{formatMoney(cat.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <span className="text-xs text-muted-foreground">No categories</span>
        )}
      </FinancialCardContent>
    </FinancialCard>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export function SpendingBreakdown() {
  const [data, setData] = useState<SpendingBreakdownResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        // Default: current quarter
        const now = new Date();
        const qStart = new Date(now.getFullYear(), Math.floor(now.getMonth() / 3) * 3, 1);
        const from = qStart.toISOString().slice(0, 10);
        const to = now.toISOString().slice(0, 10);
        const result = await getSpendingBreakdown({ period: 'monthly', from, to });
        if (!cancelled) setData(result);
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load spending breakdown');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <div className="card" data-testid="spending-breakdown-loading">Loading spending breakdown...</div>;
  }

  if (error) {
    return <div className="card text-red-600" data-testid="spending-breakdown-error">{error}</div>;
  }

  if (!data) return null;

  const essentialPct = data.period_total > 0 ? ((data.essential.total / data.period_total) * 100).toFixed(1) : '0.0';
  const discretionaryPct = data.period_total > 0 ? ((data.discretionary.total / data.period_total) * 100).toFixed(1) : '0.0';

  const slices: Slice[] = [
    { label: 'Essential', value: data.essential.total, color: '#22c55e' },
    { label: 'Discretionary', value: data.discretionary.total, color: '#f97316' },
    { label: 'Uncategorized', value: data.uncategorized.total, color: '#9ca3af' },
  ];

  return (
    <div className="space-y-4" data-testid="spending-breakdown">
      <FinancialCard variant="financial">
        <FinancialCardHeader>
          <FinancialCardTitle>Essential vs Discretionary Spending</FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          <div className="grid gap-6 md:grid-cols-2">
            {/* Donut */}
            <DonutChart slices={slices} />

            {/* Summary cards */}
            <div className="flex flex-col justify-center gap-3">
              <div className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 p-3 dark:border-green-900 dark:bg-green-950/30">
                <span className="inline-block h-3 w-3 rounded-full bg-green-500" />
                <div>
                  <div className="text-xs text-muted-foreground">Essential</div>
                  <div className="font-semibold">{formatMoney(data.essential.total)}</div>
                </div>
                <span className="ml-auto text-sm font-medium text-green-700 dark:text-green-400">
                  {essentialPct}%
                </span>
              </div>
              <div className="flex items-center gap-3 rounded-lg border border-orange-200 bg-orange-50 p-3 dark:border-orange-900 dark:bg-orange-950/30">
                <span className="inline-block h-3 w-3 rounded-full bg-orange-500" />
                <div>
                  <div className="text-xs text-muted-foreground">Discretionary</div>
                  <div className="font-semibold">{formatMoney(data.discretionary.total)}</div>
                </div>
                <span className="ml-auto text-sm font-medium text-orange-700 dark:text-orange-400">
                  {discretionaryPct}%
                </span>
              </div>
              <div className="text-center text-xs text-muted-foreground">
                Essential-to-Discretionary ratio:{' '}
                <strong>
                  {data.discretionary.total > 0
                    ? (data.essential.total / data.discretionary.total).toFixed(2)
                    : 'N/A'}
                </strong>
              </div>
            </div>
          </div>
        </FinancialCardContent>
      </FinancialCard>

      {/* Category details */}
      <div className="grid gap-4 md:grid-cols-3">
        <BucketDetail title="Essential" bucket={data.essential} color="#22c55e" dotClass="bg-green-500" />
        <BucketDetail title="Discretionary" bucket={data.discretionary} color="#f97316" dotClass="bg-orange-500" />
        <BucketDetail title="Uncategorized" bucket={data.uncategorized} color="#9ca3af" dotClass="bg-gray-400" />
      </div>
    </div>
  );
}
