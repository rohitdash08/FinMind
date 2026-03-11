import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listRecurringExpenses } from '@/api/expenses';
import { listBills } from '@/api/bills';
import { generateForecast, aggregateByWeek, computeSummary } from '@/api/cashflow';
import { formatMoney } from '@/lib/currency';
import { Button } from '@/components/ui/button';
import {
  FinancialCard,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardContent,
} from '@/components/ui/financial-card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { format, parseISO } from 'date-fns';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { RefreshCw, TrendingDown, TrendingUp, Wallet, ArrowRightLeft } from 'lucide-react';

export function CashflowForecast() {
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);

  const { data: expenses, isLoading: loadingExpenses, isError: errorExpenses, refetch: refetchExpenses } = useQuery({
    queryKey: ['recurringExpenses'],
    queryFn: () => listRecurringExpenses(),
  });

  const { data: bills, isLoading: loadingBills, isError: errorBills, refetch: refetchBills } = useQuery({
    queryKey: ['bills'],
    queryFn: () => listBills(),
  });

  const handleRefresh = () => {
    void refetchExpenses();
    void refetchBills();
  };

  const isLoading = loadingExpenses || loadingBills;
  const isError = errorExpenses || errorBills;

  const { forecast, weeklyForecast, summary, allItems } = useMemo(() => {
    if (!expenses || !bills) {
      return { forecast: [], weeklyForecast: [], summary: null, allItems: [] };
    }

    const today = new Date();
    const dailyPoints = generateForecast(expenses, bills, horizon, today);
    const weeklyPoints = aggregateByWeek(dailyPoints);
    const stats = computeSummary(dailyPoints);

    const itemsList = dailyPoints.flatMap((p) =>
      p.items.map((item) => ({ ...item, date: p.date }))
    );

    return {
      forecast: dailyPoints,
      weeklyForecast: weeklyPoints,
      summary: stats,
      allItems: itemsList,
    };
  }, [expenses, bills, horizon]);

  const horizons = [30, 60, 90] as const;

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="page-title">Cash-flow Forecast</h1>
          <p className="page-subtitle">Predict your future balances and view scheduled transactions.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-muted p-1 rounded-lg">
            {horizons.map((days) => (
              <Button
                key={days}
                variant={horizon === days ? 'financial' : 'outline'}
                size="sm"
                className={`rounded-md px-4 ${horizon !== days ? 'text-muted-foreground' : ''}`}
                onClick={() => setHorizon(days)}
              >
                {days} Days
              </Button>
            ))}
          </div>
          <Button variant="outline" size="icon" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {isError && (
        <div className="error text-destructive p-4 border border-destructive/20 rounded-md bg-destructive/10">
          Failed to load forecast data. Please try again.
        </div>
      )}

      {(isLoading || !summary) && !isError ? (
        <div className="card p-8 text-center text-muted-foreground animate-pulse">
          Loading forecast data...
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FinancialCard variant="success">
              <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <FinancialCardTitle className="text-sm font-medium">Total Inflow</FinancialCardTitle>
                <TrendingUp className="h-4 w-4" />
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">{formatMoney(summary.totalInflow)}</div>
                <p className="text-xs opacity-80 mt-1">Expected incoming</p>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant="destructive">
              <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <FinancialCardTitle className="text-sm font-medium">Total Outflow</FinancialCardTitle>
                <TrendingDown className="h-4 w-4" />
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">{formatMoney(summary.totalOutflow)}</div>
                <p className="text-xs opacity-80 mt-1">Scheduled payments</p>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard variant={summary.netFlow >= 0 ? 'financial' : 'warning'}>
              <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <FinancialCardTitle className="text-sm font-medium">Net Flow</FinancialCardTitle>
                <Wallet className="h-4 w-4" />
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">{formatMoney(summary.netFlow)}</div>
                <p className="text-xs opacity-80 mt-1">For next {horizon} days</p>
              </FinancialCardContent>
            </FinancialCard>

            <FinancialCard>
              <FinancialCardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <FinancialCardTitle className="text-sm font-medium">Items Count</FinancialCardTitle>
                <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="text-2xl font-bold">{allItems.length}</div>
                <p className="text-xs text-muted-foreground mt-1">Scheduled transactions</p>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          <FinancialCard className="p-0 overflow-hidden border-border/50">
            <div className="p-6 pb-2">
              <h3 className="text-lg font-semibold">Cash-flow Trend</h3>
              <p className="text-sm text-muted-foreground">
                {horizon > 30 ? 'Weekly aggregated view' : 'Daily forecast view'}
              </p>
            </div>
            <div className="h-[350px] w-full p-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={horizon > 30 ? weeklyForecast : forecast} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />
                  <XAxis 
                    dataKey="date" 
                    tickFormatter={(val: string) => format(parseISO(val), 'MMM d')} 
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    dy={10}
                  />
                  <YAxis 
                    tickFormatter={(val: number) => `$${val}`} 
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    dx={-10}
                  />
                  <Tooltip 
                    cursor={{ fill: 'hsl(var(--muted))', opacity: 0.4 }}
                    contentStyle={{ borderRadius: '8px', border: '1px solid hsl(var(--border))', backgroundColor: 'hsl(var(--card))', color: 'hsl(var(--foreground))' }}
                    labelFormatter={(val: string) => format(parseISO(val), 'MMM d, yyyy')}
                    formatter={(value: number) => [formatMoney(value), 'Amount']}
                  />
                  <Legend wrapperStyle={{ paddingTop: '10px' }} />
                  <Bar dataKey="inflow" name="Inflow" fill="hsl(var(--success))" radius={[4, 4, 0, 0]} maxBarSize={40} />
                  <Bar dataKey="outflow" name="Outflow" fill="hsl(var(--destructive))" radius={[4, 4, 0, 0]} maxBarSize={40} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </FinancialCard>

          <FinancialCard className="p-0 overflow-hidden border-border/50">
            <div className="p-6 pb-4 border-b border-border/50">
              <h3 className="text-lg font-semibold">Scheduled Transactions</h3>
              <p className="text-sm text-muted-foreground">All upcoming items in the next {horizon} days.</p>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="bg-muted/30">
                  <TableRow>
                    <TableHead className="w-[120px]">Date</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allItems.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                        No scheduled transactions found.
                      </TableCell>
                    </TableRow>
                  ) : (
                    allItems.slice().sort((a, b) => a.date.localeCompare(b.date)).map((item, idx) => (
                      <TableRow key={`${item.id}-${item.date}-${idx}`}>
                        <TableCell className="font-medium text-muted-foreground">
                          {format(parseISO(item.date), 'MMM d, yyyy')}
                        </TableCell>
                        <TableCell className="font-semibold">{item.name}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-[10px] capitalize">
                              {item.type}
                            </Badge>
                            {item.isIncome ? (
                              <Badge variant="secondary" className="bg-success/10 text-success hover:bg-success/20">Income</Badge>
                            ) : (
                              <Badge variant="secondary" className="bg-destructive/10 text-destructive hover:bg-destructive/20">Expense</Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className={`text-right font-bold ${item.isIncome ? 'text-success' : ''}`}>
                          {item.isIncome ? '+' : '-'}{formatMoney(item.amount, item.currency)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </FinancialCard>
        </>
      )}
    </div>
  );
}
