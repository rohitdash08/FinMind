import { useEffect, useState } from "react";
import { getLifestyleInflation, LifestyleInflationData, InflatedCategory } from "../api/lifestyle";

const WINDOW_OPTIONS = [1, 2, 3, 6];

function TrendBar({ trend }: { trend: { month: string; amount: number }[] }) {
  const max = Math.max(...trend.map((t) => t.amount), 1);
  return (
    <div className="flex items-end gap-0.5 h-10 mt-2">
      {trend.map((t, i) => (
        <div key={t.month} className="flex flex-col items-center flex-1 gap-0.5">
          <div
            className="w-full rounded-sm"
            style={{
              height: `${Math.max(4, (t.amount / max) * 36)}px`,
              background: i >= trend.length / 2 ? "#ef4444" : "#94a3b8",
            }}
            title={`${t.month}: ${t.amount.toFixed(2)}`}
          />
        </div>
      ))}
    </div>
  );
}

function CategoryCard({ cat, currency }: { cat: InflatedCategory; currency: string }) {
  const sign = cat.pct_change >= 0 ? "+" : "";
  const color =
    cat.pct_change >= 50
      ? "bg-red-50 border-red-200"
      : cat.pct_change >= 25
      ? "bg-orange-50 border-orange-200"
      : "bg-yellow-50 border-yellow-200";
  const badge =
    cat.pct_change >= 50
      ? "bg-red-100 text-red-700"
      : cat.pct_change >= 25
      ? "bg-orange-100 text-orange-700"
      : "bg-yellow-100 text-yellow-700";

  return (
    <div className={`rounded-lg border p-4 ${color}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-gray-900">{cat.category_name}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {currency} {cat.previous_avg_monthly.toFixed(2)} → {currency}{" "}
            {cat.recent_avg_monthly.toFixed(2)} /month
          </p>
        </div>
        <span className={`text-xs font-bold px-2 py-1 rounded-full ${badge}`}>
          {sign}{cat.pct_change.toFixed(1)}%
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-gray-700">
        <div>
          <span className="text-gray-500">Extra/month: </span>
          <span className="font-medium">
            {currency} {cat.abs_change_monthly.toFixed(2)}
          </span>
        </div>
        <div>
          <span className="text-gray-500">Extra/year: </span>
          <span className="font-medium text-red-600">
            {currency} {cat.annualised_extra.toFixed(2)}
          </span>
        </div>
      </div>
      <TrendBar trend={cat.trend} />
      <p className="text-xs text-gray-400 mt-1">grey = previous window · red = recent window</p>
    </div>
  );
}

export default function LifestyleInflation() {
  const [data, setData] = useState<LifestyleInflationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [window, setWindow] = useState(3);
  const [threshold, setThreshold] = useState(10);
  const [showStable, setShowStable] = useState(false);

  const currency = "₹";

  useEffect(() => {
    setLoading(true);
    setError(null);
    getLifestyleInflation(window, threshold)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [window, threshold]);

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Lifestyle Inflation</h1>
        <p className="text-gray-500 mt-1">
          Categories where your spending has grown compared to the previous period.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-4 mb-6">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Compare window:</label>
          <div className="flex gap-1">
            {WINDOW_OPTIONS.map((w) => (
              <button
                key={w}
                onClick={() => setWindow(w)}
                className={`px-3 py-1 rounded text-sm font-medium border transition-colors ${
                  window === w
                    ? "bg-indigo-600 text-white border-indigo-600"
                    : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"
                }`}
              >
                {w}mo
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Threshold:</label>
          <select
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="border rounded px-2 py-1 text-sm"
          >
            {[5, 10, 15, 20, 30].map((t) => (
              <option key={t} value={t}>
                {t}%
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && (
        <div className="flex h-40 items-center justify-center text-gray-500">
          Analysing spending patterns…
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700">
          {error}
        </div>
      )}

      {data && !loading && (
        <>
          {/* Summary banner */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-center">
              <p className="text-2xl font-bold text-red-600">
                {data.summary.inflated_count}
              </p>
              <p className="text-xs text-gray-500">Inflated categories</p>
            </div>
            <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-center">
              <p className="text-2xl font-bold text-green-600">
                {data.summary.stable_count}
              </p>
              <p className="text-xs text-gray-500">Stable categories</p>
            </div>
            <div className="rounded-lg bg-orange-50 border border-orange-200 p-3 text-center">
              <p className="text-xl font-bold text-orange-600">
                {currency} {data.summary.total_extra_monthly_spend.toFixed(2)}
              </p>
              <p className="text-xs text-gray-500">Extra spend/month</p>
            </div>
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-center">
              <p className="text-xl font-bold text-red-600">
                {currency} {data.summary.total_extra_annual_spend.toFixed(2)}
              </p>
              <p className="text-xs text-gray-500">Extra spend/year</p>
            </div>
          </div>

          {/* Inflated categories */}
          {data.inflated_categories.length === 0 ? (
            <div className="rounded-lg bg-green-50 border border-green-200 p-6 text-center text-green-700">
              <p className="font-semibold text-lg">No lifestyle inflation detected 🎉</p>
              <p className="text-sm mt-1">
                Your spending is stable or decreasing across all categories.
              </p>
            </div>
          ) : (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-3">
                Inflated Categories ({data.inflated_categories.length})
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {data.inflated_categories.map((cat) => (
                  <CategoryCard key={cat.category_id} cat={cat} currency={currency} />
                ))}
              </div>
            </div>
          )}

          {/* Stable categories (collapsible) */}
          {data.stable_categories.length > 0 && (
            <div className="mt-6">
              <button
                onClick={() => setShowStable((v) => !v)}
                className="text-sm text-indigo-600 hover:underline font-medium"
              >
                {showStable ? "Hide" : "Show"} stable categories (
                {data.stable_categories.length})
              </button>
              {showStable && (
                <div className="grid gap-3 sm:grid-cols-2 mt-3 opacity-70">
                  {data.stable_categories.map((cat) => (
                    <CategoryCard key={cat.category_id} cat={cat} currency={currency} />
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
