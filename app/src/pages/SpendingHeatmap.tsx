/**
 * Calendar Heatmap Page — spending intensity visualization.
 */

import React, { useEffect, useState } from "react";
import { fetchHeatmap, HeatmapData, HeatmapDay } from "../api/heatmap";

const COLORS = ["#1a1a2e", "#16213e", "#0f3460", "#533483", "#e94560"];

const HeatmapSquare: React.FC<{ day: HeatmapDay; size?: number }> = ({ day, size = 14 }) => (
  <div
    title={`${day.date}: $${day.amount.toFixed(2)} (${day.count} txns)`}
    style={{
      width: size,
      height: size,
      backgroundColor: COLORS[day.intensity],
      borderRadius: 2,
      margin: 1,
      display: "inline-block",
    }}
  />
);

const MonthRow: React.FC<{
  days: HeatmapDay[];
  label: string;
  daySize?: number;
}> = ({ days, label, daySize = 14 }) => (
  <div style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
    <span style={{ width: 40, fontSize: 12, color: "#aaa" }}>{label}</span>
    <div style={{ display: "flex", flexWrap: "wrap" }}>
      {days.map((d) => (
        <HeatmapSquare key={d.date} day={d} size={daySize} />
      ))}
    </div>
  </div>
);

export const SpendingHeatmap: React.FC = () => {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [month, setMonth] = useState<number | null>(null);
  const [data, setData] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchHeatmap(year, month)
      .then(setData)
      .finally(() => setLoading(false));
  }, [year, month]);

  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // Group days by month
  const byMonth: Record<number, HeatmapDay[]> = {};
  if (data) {
    for (const d of data.days) {
      const m = new Date(d.date).getMonth();
      if (!byMonth[m]) byMonth[m] = [];
      byMonth[m].push(d);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 900 }}>
      <h2>Spending Heatmap</h2>

      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <select value={year} onChange={(e) => setYear(+e.target.value)}>
          {[currentYear, currentYear - 1, currentYear - 2].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        <select value={month ?? "all"} onChange={(e) => setMonth(e.target.value === "all" ? null : +e.target.value)}>
          <option value="all">Full Year</option>
          {monthNames.map((n, i) => (
            <option key={i} value={i + 1}>{n}</option>
          ))}
        </select>
      </div>

      {loading && <p>Loading...</p>}

      {data && (
        <>
          <div style={{ display: "flex", gap: 24, marginBottom: 20 }}>
            <div style={{ background: "#1a1a2e", padding: 16, borderRadius: 8, flex: 1 }}>
              <div style={{ color: "#aaa", fontSize: 12 }}>Total</div>
              <div style={{ fontSize: 24, fontWeight: "bold" }}>${data.total_spending.toFixed(2)}</div>
            </div>
            <div style={{ background: "#1a1a2e", padding: 16, borderRadius: 8, flex: 1 }}>
              <div style={{ color: "#aaa", fontSize: 12 }}>Active Days</div>
              <div style={{ fontSize: 24, fontWeight: "bold" }}>{data.active_days}</div>
            </div>
            <div style={{ background: "#1a1a2e", padding: 16, borderRadius: 8, flex: 1 }}>
              <div style={{ color: "#aaa", fontSize: 12 }}>Avg/Day</div>
              <div style={{ fontSize: 24, fontWeight: "bold" }}>${data.avg_daily.toFixed(2)}</div>
            </div>
            <div style={{ background: "#1a1a2e", padding: 16, borderRadius: 8, flex: 1 }}>
              <div style={{ color: "#aaa", fontSize: 12 }}>Streak</div>
              <div style={{ fontSize: 24, fontWeight: "bold" }}>{data.current_streak} days</div>
            </div>
          </div>

          <div style={{ background: "#0d1117", padding: 16, borderRadius: 8 }}>
            {Object.entries(byMonth).map(([m, days]) => (
              <MonthRow key={m} days={days} label={monthNames[+m]} />
            ))}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
            <span style={{ fontSize: 12, color: "#aaa" }}>Less</span>
            {COLORS.map((c, i) => (
              <div key={i} style={{ width: 14, height: 14, backgroundColor: c, borderRadius: 2, margin: 1 }} />
            ))}
            <span style={{ fontSize: 12, color: "#aaa" }}>More</span>
          </div>
        </>
      )}
    </div>
  );
};

export default SpendingHeatmap;
