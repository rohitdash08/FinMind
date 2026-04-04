import { useEffect, useState } from 'react';
import { getWeeklyDigest, type WeeklyDigest as DigestData } from '@/api/digest';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function WeeklyDigest() {
  const [data, setData] = useState<DigestData | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getWeeklyDigest()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 text-center text-muted-foreground">Loading digest…</div>;
  if (error) return <div className="p-6 text-center text-destructive">{error}</div>;
  if (!data) return null;

  const changeColor = data.pct_change > 0 ? 'text-destructive' : 'text-green-600';
  const changeSign = data.pct_change > 0 ? '+' : '';

  return (
    <div className="container-financial py-8 space-y-6">
      <h1 className="text-2xl font-bold">Weekly Digest</h1>
      <p className="text-sm text-muted-foreground">{data.week_start} — {data.week_end}</p>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Total Spent</CardTitle></CardHeader>
          <CardContent><p className="text-2xl font-bold">${data.total_spent.toFixed(2)}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">vs Last Week</CardTitle></CardHeader>
          <CardContent><p className={`text-2xl font-bold ${changeColor}`}>{changeSign}{data.pct_change}%</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Savings Rate</CardTitle></CardHeader>
          <CardContent><p className="text-2xl font-bold">{data.savings_rate}%</p></CardContent>
        </Card>
        {data.biggest_expense && (
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Biggest Expense</CardTitle></CardHeader>
            <CardContent>
              <p className="text-lg font-bold">${data.biggest_expense.amount.toFixed(2)}</p>
              <p className="text-xs text-muted-foreground">{data.biggest_expense.description}</p>
            </CardContent>
          </Card>
        )}
      </div>

      {data.top_categories.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Top Spending Categories</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={data.top_categories}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="amount" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="pt-6">
          <p className="text-center text-lg italic text-muted-foreground">💡 {data.insight}</p>
        </CardContent>
      </Card>
    </div>
  );
}
