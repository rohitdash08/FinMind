import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { getWeeklySmartDigest, type WeeklySmartDigest as WeeklySmartDigestType } from '@/api/insights';
import { TrendingUp, TrendingDown, Info, BrainCircuit, AlertCircle } from 'lucide-react';
import { formatMoney } from '@/lib/currency';

export function WeeklySmartDigest() {
  const [digest, setDigest] = useState<WeeklySmartDigestType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await getWeeklySmartDigest();
        setDigest(data);
      } catch (e) {
        console.error('Failed to fetch weekly digest', e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return null;
  if (!digest) return null;

  return (
    <FinancialCard variant="financial" className="mb-6 overflow-hidden border-primary/20 bg-primary/5 shadow-md">
      <FinancialCardHeader className="bg-primary/10 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BrainCircuit className="w-5 h-5 text-primary" />
            <FinancialCardTitle className="text-lg font-bold">Smart Weekly Digest</FinancialCardTitle>
          </div>
          <div className="px-2 py-1 rounded-full bg-background/50 text-xs font-medium border border-primary/20">
            {digest.period}
          </div>
        </div>
        <FinancialCardDescription className="text-primary/70">
          AI-powered analysis of your spending deltas and trends
        </FinancialCardDescription>
      </FinancialCardHeader>
      <FinancialCardContent className="pt-6">
        <div className="grid md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div className="flex items-end gap-3">
              <div className="text-2xl font-bold">{formatMoney(digest.total_spend)}</div>
              <div className={`flex items-center text-sm mb-1 ${digest.total_change_pct > 0 ? 'text-destructive' : 'text-success'}`}>
                {digest.total_change_pct > 0 ? <TrendingUp className="w-4 h-4 mr-1" /> : <TrendingDown className="w-4 h-4 mr-1" />}
                {Math.abs(digest.total_change_pct)}% from last week
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="text-sm font-semibold flex items-center gap-2">
                <Info className="w-4 h-4" />
                Key Observations
              </h4>
              <ul className="space-y-2">
                {digest.insights.map((insight, i) => (
                  <li key={i} className="text-sm bg-background/40 p-2 rounded border border-primary/10">
                    {insight}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="space-y-4">
            <div className="p-3 rounded-lg bg-primary/10 border border-primary/20">
              <div className="flex items-center gap-2 mb-2 text-sm font-bold uppercase tracking-wider text-primary">
                <AlertCircle className="w-4 h-4" />
                Prediction: {digest.prediction}
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {digest.trend_analysis}
              </p>
            </div>

            {digest.significant_changes.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase text-muted-foreground">Notable Shifts</h4>
                <div className="grid grid-cols-2 gap-2">
                  {digest.significant_changes.slice(0, 4).map((change, i) => (
                    <div key={i} className="text-xs p-2 bg-background/60 rounded border flex flex-col justify-between">
                      <span className="font-medium truncate">{change.category}</span>
                      <span className={change.change_pct > 0 ? 'text-destructive font-bold' : 'text-success font-bold'}>
                        {change.change_pct > 0 ? '+' : ''}{change.change_pct}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </FinancialCardContent>
    </FinancialCard>
  );
}
