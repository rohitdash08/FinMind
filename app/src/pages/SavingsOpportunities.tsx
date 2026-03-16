import { useEffect, useState } from "react";
import {
  getSavingsOpportunities,
  type SavingsOpportunity,
  type SavingsReport,
  type TopSpenderCategory,
} from "../api/savings";

const TYPE_CONFIG = {
  consistent_underspend: {
    icon: "📉",
    color: "#4CAF50",
    bg: "rgba(76,175,80,0.1)",
    label: "Cut Budget",
  },
  recurring_subscription: {
    icon: "🔄",
    color: "#FF9800",
    bg: "rgba(255,152,0,0.1)",
    label: "Subscription",
  },
  irregular_big_spend: {
    icon: "⚡",
    color: "#F44336",
    bg: "rgba(244,67,54,0.1)",
    label: "Big Spend",
  },
};

function fmt(n: number) {
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function OpportunityCard({ op }: { op: SavingsOpportunity }) {
  const cfg = TYPE_CONFIG[op.type];
  return (
    <div
      style={{
        background: cfg.bg,
        border: `1px solid ${cfg.color}`,
        borderRadius: 10,
        padding: "1rem 1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "#fff" }}>
          {cfg.icon} {op.category_name}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 800,
            color: cfg.color,
            border: `1px solid ${cfg.color}`,
            borderRadius: 4,
            padding: "2px 8px",
          }}
        >
          {cfg.label}
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: "#ccc", lineHeight: 1.5 }}>
        {op.message}
      </p>
      {op.type === "consistent_underspend" && op.estimated_monthly_saving != null && (
        <div
          style={{
            background: "rgba(76,175,80,0.15)",
            borderRadius: 6,
            padding: "6px 12px",
            display: "inline-flex",
            gap: 16,
            fontSize: 12,
          }}
        >
          <span style={{ color: "#aaa" }}>
            Avg: <strong style={{ color: "#fff" }}>{fmt(op.avg_monthly_spend!)}</strong>
          </span>
          <span style={{ color: "#aaa" }}>
            Recent: <strong style={{ color: "#fff" }}>{fmt(op.recent_spend!)}</strong>
          </span>
          <span style={{ color: "#4CAF50", fontWeight: 700 }}>
            Save {fmt(op.estimated_monthly_saving)}/mo
          </span>
        </div>
      )}
      {op.type === "recurring_subscription" && op.estimated_annual_cost != null && (
        <div style={{ fontSize: 12, color: "#FF9800" }}>
          Annual cost: <strong>{fmt(op.estimated_annual_cost)}</strong> ·{" "}
          {op.months_detected?.length} months detected
        </div>
      )}
      {op.type === "irregular_big_spend" && op.amount != null && (
        <div style={{ fontSize: 12, color: "#aaa" }}>
          Spend: <strong style={{ color: "#F44336" }}>{fmt(op.amount)}</strong> vs avg{" "}
          <strong style={{ color: "#fff" }}>{fmt(op.category_avg!)}</strong>
          {op.spent_at && ` — ${op.spent_at}`}
        </div>
      )}
    </div>
  );
}

function TopSpenderRow({ t }: { t: TopSpenderCategory }) {
  return (
    <div
      style={{
        background: "#16213e",
        borderRadius: 8,
        padding: "10px 14px",
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}
    >
      <div
        style={{
          width: 40,
          textAlign: "right",
          fontWeight: 800,
          fontSize: 15,
          color: "#fff",
        }}
      >
        {t.pct_of_total_spend}%
      </div>
      <div style={{ flex: 1 }}>
        <div
          style={{
            height: 6,
            borderRadius: 3,
            background: "#333",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${t.pct_of_total_spend}%`,
              height: "100%",
              background: "#3F51B5",
              borderRadius: 3,
            }}
          />
        </div>
        <div style={{ marginTop: 4, fontSize: 12, color: "#ccc" }}>
          {t.category_name} · avg {fmt(t.avg_monthly_spend)}/mo
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div
      style={{
        background: "#16213e",
        border: `1px solid ${color}`,
        borderRadius: 8,
        padding: "10px 16px",
        textAlign: "center",
        flex: "1 1 120px",
      }}
    >
      <div style={{ fontSize: 22, fontWeight: 900, color }}>{value}</div>
      <div style={{ fontSize: 11, color: "#aaa" }}>{label}</div>
    </div>
  );
}

export default function SavingsOpportunities() {
  const [report, setReport] = useState<SavingsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [months, setMonths] = useState(3);
  const [filter, setFilter] = useState<string>("all");

  const load = async () => {
    setLoading(true);
    try {
      const data = await getSavingsOpportunities(months);
      setReport(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [months]);

  const filtered = report?.opportunities.filter(
    (o) => filter === "all" || o.type === filter
  ) ?? [];

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "2rem 1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: "#fff" }}>
          💡 Savings Opportunities
        </h1>
        <select
          value={months}
          onChange={(e) => setMonths(Number(e.target.value))}
          style={{
            background: "#16213e",
            color: "#fff",
            border: "1px solid #444",
            borderRadius: 7,
            padding: "7px 12px",
            fontSize: 13,
          }}
        >
          {[1, 3, 6, 12].map((m) => (
            <option key={m} value={m}>
              Last {m} month{m > 1 ? "s" : ""}
            </option>
          ))}
        </select>
      </div>

      {report && (
        <>
          {/* Potential saving banner */}
          {report.total_estimated_monthly_saving > 0 && (
            <div
              style={{
                background: "linear-gradient(135deg, #1B5E20, #2E7D32)",
                borderRadius: 12,
                padding: "1.25rem 1.75rem",
                marginBottom: 20,
                color: "#fff",
              }}
            >
              <div style={{ fontSize: 12, opacity: 0.75 }}>Estimated monthly savings if acted on</div>
              <div style={{ fontSize: 32, fontWeight: 900 }}>
                {fmt(report.total_estimated_monthly_saving)}
                <span style={{ fontSize: 14, opacity: 0.7 }}>/month</span>
              </div>
              <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
                ≈ {fmt(report.total_estimated_monthly_saving * 12)} per year
              </div>
            </div>
          )}

          {/* Summary pills */}
          <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
            <SummaryCard label="Cut Budget" value={report.summary.consistent_underspend} color="#4CAF50" />
            <SummaryCard label="Subscriptions" value={report.summary.recurring_subscriptions} color="#FF9800" />
            <SummaryCard label="Big Spends" value={report.summary.irregular_big_spends} color="#F44336" />
          </div>

          {/* Filter tabs */}
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            {["all", "consistent_underspend", "recurring_subscription", "irregular_big_spend"].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  background: filter === f ? "#3F51B5" : "#1a1a2e",
                  color: "#fff",
                  border: "1px solid #3F51B5",
                  borderRadius: 6,
                  padding: "6px 14px",
                  cursor: "pointer",
                  fontSize: 12,
                  fontWeight: filter === f ? 700 : 400,
                }}
              >
                {f === "all"
                  ? `All (${report.summary.total_opportunities})`
                  : f === "consistent_underspend"
                  ? "📉 Cut Budget"
                  : f === "recurring_subscription"
                  ? "🔄 Subscriptions"
                  : "⚡ Big Spends"}
              </button>
            ))}
          </div>
        </>
      )}

      {loading && <p style={{ color: "#aaa", textAlign: "center" }}>Analysing your spending…</p>}

      {!loading && report && (
        <>
          {filtered.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                background: "#16213e",
                borderRadius: 12,
                padding: "3rem",
                color: "#aaa",
              }}
            >
              {report.summary.total_opportunities === 0
                ? "No saving opportunities detected yet. Keep tracking your expenses!"
                : "No items in this category."}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {filtered.map((op, i) => (
                <OpportunityCard key={i} op={op} />
              ))}
            </div>
          )}

          {report.top_spender_categories.length > 0 && (
            <div style={{ marginTop: 32 }}>
              <h3 style={{ color: "#fff", marginBottom: 12, fontSize: 15 }}>
                Where your money goes
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {report.top_spender_categories.map((t) => (
                  <TopSpenderRow key={t.category_id} t={t} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
