import { useEffect, useState } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Brain,
  Calendar,
  Mail,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import {
  getWeeklyDigest,
  getDigestPreferences,
  updateDigestPreferences,
  type WeeklyDigest,
  type DigestPreferences,
} from '@/api/digest';
import { formatMoney } from '@/lib/currency';
import { useToast } from '@/hooks/use-toast';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export function Digest() {
  const { toast } = useToast();
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [prefs, setPrefs] = useState<DigestPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadDigest() {
    setLoading(true);
    setError(null);
    try {
      const [d, p] = await Promise.all([getWeeklyDigest(), getDigestPreferences()]);
      setDigest(d);
      setPrefs(p);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load digest';
      setError(message);
      toast({ title: 'Failed to load digest', description: message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDigest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggleEnabled() {
    if (!prefs) return;
    try {
      const updated = await updateDigestPreferences({ enabled: !prefs.enabled });
      setPrefs(updated);
      toast({ title: updated.enabled ? 'Digest enabled' : 'Digest disabled' });
    } catch (err: unknown) {
      toast({ title: 'Failed to update preferences', description: err instanceof Error ? err.message : 'Unknown error' });
    }
  }

  async function toggleEmail() {
    if (!prefs) return;
    try {
      const updated = await updateDigestPreferences({ send_email: !prefs.send_email });
      setPrefs(updated);
      toast({ title: updated.send_email ? 'Email notifications enabled' : 'Email notifications disabled' });
    } catch (err: unknown) {
      toast({ title: 'Failed to update preferences', description: err instanceof Error ? err.message : 'Unknown error' });
    }
  }

  async function updateDay(day: number) {
    try {
      const updated = await updateDigestPreferences({ day_of_week: day });
      setPrefs(updated);
      toast({ title: 'Digest day set to ' + DAY_NAMES[day] });
    } catch (err: unknown) {
      toast({ title: 'Failed to update preferences', description: err instanceof Error ? err.message : 'Unknown error' });
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="page-title">Weekly Digest</h1>
            <p className="page-subtitle">
              Smart financial summary with AI-powered insights and trends.
            </p>
          </div>
          <Button onClick={loadDigest} disabled={loading}>
            <RefreshCw className={'mr-2 h-4 w-4 ' + (loading ? 'animate-spin' : '')} />
            Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="card">Loading digest...</div>
      ) : error ? (
        <div className="card text-red-600">{error}</div>
      ) : digest ? (
        <div className="space-y-6">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Calendar className="h-4 w-4" />
            <span>{digest.period.start} to {digest.period.end}</span>
            <span className="ml-2 text-xs">({digest.transactions_count} transactions)</span>
          </div>

          <div className="grid gap-4 md:grid-cols-4">
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm flex items-center gap-2">
                  <TrendingDown className="h-4 w-4 text-red-500" />
                  Total Spent
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">{formatMoney(digest.total_expenses)}</div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-green-500" />
                  Total Income
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">{formatMoney(digest.total_income)}</div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm flex items-center gap-2">
                  <Wallet className="h-4 w-4" />
                  Net
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className={'text-2xl font-bold ' + (digest.net >= 0 ? 'text-green-600' : 'text-red-600')}>
                  {formatMoney(digest.net)}
                </div>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader className="pb-2">
                <FinancialCardTitle className="text-sm flex items-center gap-2">
                  {digest.wow_change > 0 ? (
                    <ArrowUpRight className="h-4 w-4 text-red-500" />
                  ) : digest.wow_change < 0 ? (
                    <ArrowDownRight className="h-4 w-4 text-green-500" />
                  ) : (
                    <BarChart3 className="h-4 w-4" />
                  )}
                  WoW Change
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className={'text-2xl font-bold ' + (digest.wow_change > 0 ? 'text-red-600' : digest.wow_change < 0 ? 'text-green-600' : '')}>
                  {digest.wow_change > 0 ? '+' : ''}{digest.wow_change.toFixed(1)}%
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  Daily avg: {formatMoney(digest.daily_average)}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5" />
                Top Categories
              </FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              {digest.top_categories.length > 0 ? (
                <div className="space-y-3">
                  {digest.top_categories.map((cat, i) => (
                    <div key={cat.category_id ?? 'uncat-' + i} className="flex items-center justify-between rounded-lg border p-3">
                      <span className="font-medium">{cat.name}</span>
                      <span className="font-semibold">{formatMoney(cat.amount)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">No spending categories this week.</div>
              )}
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial" className="fade-in-up">
            <FinancialCardHeader>
              <FinancialCardTitle className="flex items-center gap-2">
                <Brain className="h-5 w-5" />
                AI Insight
                <span className="text-xs font-normal text-muted-foreground">({digest.method})</span>
              </FinancialCardTitle>
            </FinancialCardHeader>
            <FinancialCardContent>
              <p className="text-sm leading-relaxed">{digest.narrative}</p>
            </FinancialCardContent>
          </FinancialCard>

          {prefs && (
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <FinancialCardTitle className="flex items-center gap-2">
                  <Mail className="h-5 w-5" />
                  Digest Preferences
                </FinancialCardTitle>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">Weekly Digest</div>
                      <div className="text-sm text-muted-foreground">Receive a weekly financial summary</div>
                    </div>
                    <Button variant={prefs.enabled ? 'default' : 'outline'} size="sm" onClick={toggleEnabled}>
                      {prefs.enabled ? 'Enabled' : 'Disabled'}
                    </Button>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">Email Notifications</div>
                      <div className="text-sm text-muted-foreground">Send digest via email</div>
                    </div>
                    <Button variant={prefs.send_email ? 'default' : 'outline'} size="sm" onClick={toggleEmail}>
                      {prefs.send_email ? 'On' : 'Off'}
                    </Button>
                  </div>

                  <div>
                    <div className="font-medium mb-2">Delivery Day</div>
                    <div className="flex flex-wrap gap-2">
                      {DAY_NAMES.map((name, i) => (
                        <Button
                          key={name}
                          variant={prefs.day_of_week === i ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => updateDay(i)}
                        >
                          {name.slice(0, 3)}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>
              </FinancialCardContent>
            </FinancialCard>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default Digest;
