import { useQuery } from "@tanstack/react-query";
import { getWeeklyDigest, type WeeklyDigest } from "@/api/insights";

export const WeeklyDigest = () => {
  const { data, isLoading, error } = useQuery<WeeklyDigest>({
    queryKey: ["weekly-digest"],
    queryFn: () => getWeeklyDigest(),
  });

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-1/3"></div>
          <div className="h-32 bg-gray-200 rounded"></div>
          <div className="h-32 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">Failed to load weekly digest</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const formatCurrency = (amount: number) => 
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);

  const formatDate = (dateStr: string) => 
    new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

  const changeColor = data.analytics.week_over_week_change_pct > 0 
    ? "text-red-600" 
    : "text-green-600";

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Weekly Digest</h1>
        <span className="text-sm text-gray-500">
          {formatDate(data.week_start)} - {formatDate(data.week_end)}
        </span>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-6 rounded-lg shadow border">
          <p className="text-sm text-gray-500 mb-1">Income</p>
          <p className="text-2xl font-bold text-green-600">{formatCurrency(data.income)}</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow border">
          <p className="text-sm text-gray-500 mb-1">Expenses</p>
          <p className="text-2xl font-bold text-red-600">{formatCurrency(data.expenses)}</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow border">
          <p className="text-sm text-gray-500 mb-1">Net Flow</p>
          <p className={`text-2xl font-bold ${data.net_flow >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {formatCurrency(data.net_flow)}
          </p>
        </div>
      </div>

      {/* Week over Week Change */}
      <div className="bg-white p-6 rounded-lg shadow border">
        <h2 className="text-lg font-semibold mb-4">Week over Week</h2>
        <div className="flex items-center gap-2">
          <span className={`text-3xl font-bold ${changeColor}`}>
            {data.analytics.week_over_week_change_pct > 0 ? '+' : ''}
            {data.analytics.week_over_week_change_pct}%
          </span>
          <span className="text-gray-500">vs last week</span>
        </div>
        <p className="text-sm text-gray-500 mt-2">
          {formatCurrency(data.analytics.previous_week_expenses)} → {formatCurrency(data.analytics.current_week_expenses)}
        </p>
      </div>

      {/* Top Categories */}
      <div className="bg-white p-6 rounded-lg shadow border">
        <h2 className="text-lg font-semibold mb-4">Top Spending Categories</h2>
        <div className="space-y-3">
          {data.analytics.top_categories.map((cat, i) => (
            <div key={i} className="flex justify-between items-center">
              <span className="capitalize">{cat.category_id}</span>
              <span className="font-medium">{formatCurrency(cat.amount)}</span>
            </div>
          ))}
          {data.analytics.top_categories.length === 0 && (
            <p className="text-gray-500">No expenses this week</p>
          )}
        </div>
      </div>

      {/* Tips */}
      {data.tips && data.tips.length > 0 && (
        <div className="bg-blue-50 p-6 rounded-lg border border-blue-200">
          <h2 className="text-lg font-semibold mb-4">Tips</h2>
          <ul className="space-y-2">
            {data.tips.map((tip, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-blue-600">•</span>
                <span>{tip}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* AI Summary */}
      {data.summary && (
        <div className="bg-purple-50 p-6 rounded-lg border border-purple-200">
          <h2 className="text-lg font-semibold mb-2">AI Summary</h2>
          <p className="text-gray-700">{data.summary}</p>
        </div>
      )}

      {/* Method Badge */}
      <div className="text-center">
        <span className="inline-block px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">
          Generated via {data.method}
        </span>
      </div>
    </div>
  );
};

export default WeeklyDigest;
