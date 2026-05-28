/**
 * Weekly Smart Digest Page — financial summary with trends and AI insights.
 */

import { useEffect, useState } from 'react';
import { getWeeklyDigest, type WeeklyDigest } from '../api/digest';

const MOOD_COLORS: Record<string, string> = {
  great: 'text-green-600',
  good: 'text-emerald-500',
  okay: 'text-yellow-500',
  needs_attention: 'text-red-500',
};

const DIRECTION_ICONS: Record<string, string> = {
  up: '↑',
  down: '↓',
  stable: '→',
};

export default function WeeklyDigestPage() {
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getWeeklyDigest()
      .then(setDigest)
      .catch((err) => setError(err.message || 'Failed to load digest'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          {error}
        </div>
      </div>
    );
  }

  if (!digest) return null;

  const { period, summary, comparison, categories, daily_spending, upcoming_bills, ai_insights } = digest;
  const maxDaily = Math.max(...daily_spending.map((d) => d.amount), 1);

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Weekly Digest</h1>
          <p className="text-muted-foreground">{period.label}</p>
        </div>
        {ai_insights && (
          <span className={`text-sm font-medium ${MOOD_COLORS[ai_insights.mood] || ''}`}>
            {ai_insights.mood.replace('_', ' ').toUpperCase()}
          </span>
        )}
      </div>

      {/* AI Summary */}
      {ai_insights && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm font-medium text-blue-900 mb-2">AI Summary</p>
          <p className="text-sm text-blue-800">{ai_insights.summary}</p>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-card border rounded-lg p-4">
          <p className="text-xs text-muted-foreground">Income</p>
          <p className="text-xl font-semibold text-green-600">{summary.income.toFixed(2)}</p>
        </div>
        <div className="bg-card border rounded-lg p-4">
          <p className="text-xs text-muted-foreground">Expenses</p>
          <p className="text-xl font-semibold text-red-600">{summary.expenses.toFixed(2)}</p>
        </div>
        <div className="bg-card border rounded-lg p-4">
          <p className="text-xs text-muted-foreground">Net Flow</p>
          <p className={`text-xl font-semibold ${summary.net_flow >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {summary.net_flow.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Week-over-Week */}
      <div className="bg-card border rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-medium">Week-over-Week</p>
          <span className={`text-lg font-bold ${
            comparison.trends.spending_direction === 'down' ? 'text-green-600' :
            comparison.trends.spending_direction === 'up' ? 'text-red-600' : 'text-gray-500'
          }`}>
            {DIRECTION_ICONS[comparison.trends.spending_direction]} {Math.abs(comparison.trends.week_over_week_change_pct)}%
          </span>
        </div>
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Last week: {comparison.previous_week.expenses.toFixed(2)}</span>
          <span>This week: {summary.expenses.toFixed(2)}</span>
        </div>
        {comparison.trends.alerts.length > 0 && (
          <div className="mt-2 space-y-1">
            {comparison.trends.alerts.map((alert, i) => (
              <p key={i} className="text-xs text-amber-600">⚠ {alert}</p>
            ))}
          </div>
        )}
      </div>

      {/* Daily Spending Chart */}
      <div className="bg-card border rounded-lg p-4">
        <p className="text-sm font-medium mb-3">Daily Spending</p>
        <div className="flex items-end gap-1 h-32">
          {daily_spending.map((d) => (
            <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full bg-primary/80 rounded-t"
                style={{ height: `${(d.amount / maxDaily) * 100}%`, minHeight: d.amount > 0 ? '4px' : '0' }}
                title={`${d.date}: ${d.amount}`}
              />
              <span className="text-[10px] text-muted-foreground">
                {d.date.slice(8)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Category Breakdown */}
      {categories.length > 0 && (
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm font-medium mb-3">Top Categories</p>
          <div className="space-y-2">
            {categories.slice(0, 5).map((cat) => (
              <div key={cat.category_id ?? 'uncat'} className="flex items-center gap-2">
                <div className="flex-1">
                  <div className="flex justify-between text-sm">
                    <span>{cat.category_name}</span>
                    <span>{cat.amount.toFixed(2)} ({cat.share_pct}%)</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-1.5 mt-1">
                    <div
                      className="bg-primary rounded-full h-1.5"
                      style={{ width: `${cat.share_pct}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upcoming Bills */}
      {upcoming_bills.length > 0 && (
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm font-medium mb-3">Upcoming Bills (14 days)</p>
          <div className="space-y-2">
            {upcoming_bills.map((bill) => (
              <div key={bill.id} className="flex justify-between items-center text-sm">
                <div>
                  <span className="font-medium">{bill.name}</span>
                  <span className="text-muted-foreground ml-2">
                    due {bill.days_until_due === 0 ? 'today' : `in ${bill.days_until_due}d`}
                  </span>
                </div>
                <span className="font-medium">{bill.amount.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI Tips */}
      {ai_insights && ai_insights.tips.length > 0 && (
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm font-medium mb-2">Tips</p>
          <ul className="space-y-1">
            {ai_insights.tips.map((tip, i) => (
              <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                <span className="text-primary mt-0.5">•</span>
                {tip}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
