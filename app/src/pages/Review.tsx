import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { getMonthlyReview, type MonthlyReview } from '@/api/review';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  Lightbulb,
  BarChart3,
} from 'lucide-react';
import { formatMoney } from '@/lib/currency';

function currency(n: number, code?: string) {
  return formatMoney(Number(n || 0), code);
}

const SEVERITY_COLORS: Record<string, string> = {
  info: 'border-l-blue-400 bg-blue-50',
  medium: 'border-l-amber-400 bg-amber-50',
  high: 'border-l-red-400 bg-red-50',
};

const SEVERITY_ICONS: Record<string, typeof AlertTriangle> = {
  info: CheckCircle,
  medium: AlertTriangle,
  high: AlertTriangle,
};

const SEVERITY_INDICATOR: Record<string, string> = {
  info: 'bg-blue-100 text-blue-700',
  medium: 'bg-amber-100 text-amber-700',
  high: 'bg-red-100 text-red-700',
};

export default function Review() {
  const [data, setData] = useState<MonthlyReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [step, setStep] = useState(0);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      setStep(0);
      try {
        const res = await getMonthlyReview(month);
        setData(res);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load review');
      } finally {
        setLoading(false);
      }
    })();
  }, [month]);

  if (loading) {
    return (
      <div className="page-wrap">
        <div className="page-header"><h1 className="page-title">Monthly Review</h1></div>
        <div className="card">Loading review...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-wrap">
        <div className="page-header"><h1 className="page-title">Monthly Review</h1></div>
        <div className="error">{error}</div>
      </div>
    );
  }

  if (!data) return null;

  const { current, previous, reviews, recommendations } = data;
  const totalSteps = 1 + (reviews.length > 0 ? 1 : 0) + (recommendations.length > 0 ? 1 : 0) + 1;
  const isLast = step >= totalSteps - 1;

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Monthly Financial Review</h1>
            <p className="page-subtitle">
              Step {Math.min(step + 1, totalSteps)} of {totalSteps}
            </p>
          </div>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="review-month">Review month</label>
            <input
              id="review-month"
              type="month"
              className="input h-9 w-[160px]"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
          </div>
        </div>
        <div className="mt-4 flex gap-1.5">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <div
              key={i}
              className={`h-2 flex-1 rounded-full transition-colors ${
                i <= step ? 'bg-primary' : 'bg-muted-dark'
              }`}
            />
          ))}
        </div>
      </div>

      {step === 0 && (
        <div className="space-y-6 fade-in-up">
          <FinancialCard>
            <FinancialCardHeader>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary-light flex items-center justify-center">
                  <BarChart3 className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <FinancialCardTitle>Period Overview</FinancialCardTitle>
                  <FinancialCardDescription>{data.period} vs {data.previous_period}</FinancialCardDescription>
                </div>
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-3 rounded-xl border bg-white">
                  <div className="text-xs text-muted-foreground mb-1">Income</div>
                  <div className="text-lg font-bold text-success">{currency(current.total_income)}</div>
                  <div className="text-xs text-muted-foreground">Prev: {currency(previous.total_income)}</div>
                </div>
                <div className="p-3 rounded-xl border bg-white">
                  <div className="text-xs text-muted-foreground mb-1">Expenses</div>
                  <div className="text-lg font-bold text-destructive">{currency(current.total_expenses)}</div>
                  <div className="text-xs text-muted-foreground">Prev: {currency(previous.total_expenses)}</div>
                </div>
                <div className="p-3 rounded-xl border bg-white">
                  <div className="text-xs text-muted-foreground mb-1">Net Flow</div>
                  <div className={`text-lg font-bold ${current.net_flow >= 0 ? 'text-success' : 'text-destructive'}`}>
                    {currency(current.net_flow)}
                  </div>
                </div>
                <div className="p-3 rounded-xl border bg-white">
                  <div className="text-xs text-muted-foreground mb-1">Transactions</div>
                  <div className="text-lg font-bold">{current.transaction_count}</div>
                </div>
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard>
            <FinancialCardHeader>
              <FinancialCardTitle>Top Categories</FinancialCardTitle>
              <FinancialCardDescription>Largest expense categories this period</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              {current.categories.length === 0 ? (
                <div className="text-sm text-muted-foreground">No categories tracked.</div>
              ) : (
                <div className="space-y-3">
                  {current.categories.slice(0, 5).map((cat, i) => {
                    const total = current.total_expenses || 1;
                    const pct = (cat.amount / total) * 100;
                    return (
                      <div key={cat.name}>
                        <div className="flex justify-between text-sm mb-1">
                          <span>{cat.name}</span>
                          <span className="text-muted-foreground">{currency(cat.amount)} ({pct.toFixed(0)}%)</span>
                        </div>
                        <div className="chart-track">
                          <div
                            className="chart-fill-primary"
                            style={{ width: `${Math.max(2, pct)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {step === 1 && reviews.length > 0 && (
        <div className="space-y-4 fade-in-up">
          <FinancialCard>
            <FinancialCardHeader>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-amber-600" />
                </div>
                <div>
                  <FinancialCardTitle>Key Findings</FinancialCardTitle>
                  <FinancialCardDescription>
                    {reviews.length} item{reviews.length !== 1 ? 's' : ''} to review
                  </FinancialCardDescription>
                </div>
              </div>
            </FinancialCardHeader>
            <FinancialCardContent className="space-y-3">
              {reviews.map((r, i) => {
                const Icon = SEVERITY_ICONS[r.severity] || AlertTriangle;
                return (
                  <div
                    key={i}
                    className={`border-l-4 rounded-lg p-4 ${SEVERITY_COLORS[r.severity] || 'border-l-gray-400 bg-gray-50'}`}
                  >
                    <div className="flex items-start gap-3">
                      <Icon className={`w-5 h-5 mt-0.5 ${
                        r.severity === 'high' ? 'text-red-500' : r.severity === 'medium' ? 'text-amber-500' : 'text-blue-500'
                      }`} />
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold text-sm">{r.title}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SEVERITY_INDICATOR[r.severity]}`}>
                            {r.severity}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground">{r.description}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </FinancialCardContent>
          </FinancialCard>
        </div>
      )}

      {step === 1 && reviews.length === 0 && step < totalSteps - 1 && (
        <div className="card fade-in-up text-center py-8">
          <CheckCircle className="w-12 h-12 text-success mx-auto mb-3" />
          <h3 className="text-lg font-bold mb-1">No significant findings</h3>
          <p className="text-sm text-muted-foreground">Everything looks stable compared to last month.</p>
        </div>
      )}

      {((step === 1 && reviews.length === 0) || (step === 2 && reviews.length > 0)) && recommendations.length > 0 && (() => {
        const recStep = step - (reviews.length > 0 ? 1 : 0);
        return (
          <div className="space-y-4 fade-in-up">
            <FinancialCard>
              <FinancialCardHeader>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                    <Lightbulb className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <FinancialCardTitle>Recommendations</FinancialCardTitle>
                    <FinancialCardDescription>
                      {recommendations.length} suggestion{recommendations.length !== 1 ? 's' : ''} for you
                    </FinancialCardDescription>
                  </div>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent className="space-y-3">
                {recommendations.map((r, i) => (
                  <div key={i} className="rounded-lg border p-4 hover:bg-muted/30 transition-colors">
                    <div className="flex items-start gap-3">
                      <Lightbulb className="w-5 h-5 text-primary mt-0.5" />
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold text-sm">{r.action.replace(/_/g, ' ')}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            r.priority === 'high'
                              ? 'bg-red-100 text-red-700'
                              : r.priority === 'medium'
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-blue-100 text-blue-700'
                          }`}>
                            {r.priority}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground">{r.message}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </FinancialCardContent>
            </FinancialCard>
          </div>
        );
      })()}

      {(step === totalSteps - 1 || (reviews.length === 0 && recommendations.length === 0 && step >= 1)) && (
        <div className="card fade-in-up text-center py-10">
          <CheckCircle className="w-16 h-16 text-success mx-auto mb-4" />
          <h2 className="text-2xl font-bold mb-2">Review Complete</h2>
          <p className="text-muted-foreground mb-6 max-w-md mx-auto">
            Your financial review for {data.period} is done.
            {reviews.length > 0 && ` Found ${reviews.length} item${reviews.length !== 1 ? 's' : ''} to act on.`}
            {recommendations.length > 0 && ` ${recommendations.length} recommendation${recommendations.length !== 1 ? 's' : ''} available.`}
          </p>
          <div className="flex gap-3 justify-center">
            <Button variant="outline" onClick={() => { setMonth(new Date().toISOString().slice(0, 7)); }}>
              <ArrowLeft className="w-4 h-4 mr-1" />
              Start Fresh
            </Button>
          </div>
        </div>
      )}

      <div className="flex justify-between mt-8">
        <Button variant="outline" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
          <ArrowLeft className="w-4 h-4 mr-1" />
          Previous
        </Button>
        <Button onClick={() => setStep((s) => Math.min(totalSteps - 1, s + 1))}>
          {isLast ? 'Finish' : 'Next'}
          {!isLast && <ArrowRight className="w-4 h-4 ml-1" />}
        </Button>
      </div>
    </div>
  );
}
