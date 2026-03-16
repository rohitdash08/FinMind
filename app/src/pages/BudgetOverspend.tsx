import { useEffect, useState } from "react";
import {
  createBudget,
  deleteBudget,
  getBudgets,
  getOverspendWarnings,
  type CategoryBudget,
  type CreateBudgetPayload,
  type OverspendWarning,
} from "../api/budgets";

interface Category {
  id: number;
  name: string;
}

const LEVEL_CONFIG = {
  CRITICAL: { color: "#F44336", bg: "rgba(244,67,54,0.15)", label: "OVER BUDGET" },
  HIGH: { color: "#FF5722", bg: "rgba(255,87,34,0.15)", label: "ALMOST OVER" },
  MEDIUM: { color: "#FF9800", bg: "rgba(255,152,0,0.15)", label: "WARNING" },
  OK: { color: "#4CAF50", bg: "rgba(76,175,80,0.1)", label: "ON TRACK" },
};

function ProgressBar({ pct, level }: { pct: number; level: OverspendWarning["warning_level"] }) {
  const cfg = LEVEL_CONFIG[level];
  const capped = Math.min(pct, 100);
  return (
    <div style={{ background: "#333", borderRadius: 4, height: 8, overflow: "hidden" }}>
      <div
        style={{
          width: `${capped}%`,
          height: "100%",
          background: cfg.color,
          transition: "width 0.3s",
          borderRadius: 4,
        }}
      />
    </div>
  );
}

function WarningCard({ w }: { w: OverspendWarning }) {
  const cfg = LEVEL_CONFIG[w.warning_level];
  return (
    <div
      style={{
        background: cfg.bg,
        border: `1px solid ${cfg.color}`,
        borderRadius: 10,
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontWeight: 700, color: "#fff", fontSize: 15 }}>
          {w.category_name ?? `Category #${w.category_id}`}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 800,
            color: cfg.color,
            background: cfg.bg,
            border: `1px solid ${cfg.color}`,
            borderRadius: 4,
            padding: "2px 8px",
            letterSpacing: 0.5,
          }}
        >
          {cfg.label}
        </span>
      </div>
      <ProgressBar pct={w.pct_used} level={w.warning_level} />
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#bbb" }}>
        <span>
          Spent: <strong style={{ color: "#fff" }}>₹{w.spent.toLocaleString()}</strong>
        </span>
        <span>
          {w.pct_used.toFixed(1)}% of ₹{w.budget_limit.toLocaleString()}
        </span>
        <span style={{ color: w.remaining < 0 ? "#F44336" : "#4CAF50" }}>
          {w.remaining < 0
            ? `₹${Math.abs(w.remaining).toLocaleString()} over`
            : `₹${w.remaining.toLocaleString()} left`}
        </span>
      </div>
    </div>
  );
}

function SummaryPill({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div
      style={{
        background: "#1a1a2e",
        border: `1px solid ${color}`,
        borderRadius: 8,
        padding: "8px 14px",
        textAlign: "center",
        minWidth: 80,
      }}
    >
      <div style={{ fontSize: 22, fontWeight: 900, color }}>{count}</div>
      <div style={{ fontSize: 11, color: "#aaa" }}>{label}</div>
    </div>
  );
}

export default function BudgetOverspend() {
  const [report, setReport] = useState<Awaited<ReturnType<typeof getOverspendWarnings>> | null>(null);
  const [budgets, setBudgets] = useState<CategoryBudget[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [onlyWarnings, setOnlyWarnings] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreateBudgetPayload>({ category_id: 0, budget_limit: 0 });
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      const [rep, blist] = await Promise.all([
        getOverspendWarnings(undefined, onlyWarnings),
        getBudgets(),
      ]);
      setReport(rep);
      setBudgets(blist);
    } finally {
      setLoading(false);
    }
  };

  // Load categories for the create form
  const loadCategories = async () => {
    try {
      const { default: api } = await import("../api/index");
      const r = await api.get("/categories");
      setCategories(r.data || []);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    load();
    loadCategories();
  }, [onlyWarnings]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await createBudget({ ...form, budget_limit: Number(form.budget_limit) });
      setShowForm(false);
      setForm({ category_id: 0, budget_limit: 0 });
      await load();
    } catch {
      alert("Failed to create budget. Check the details.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Remove this budget limit?")) return;
    await deleteBudget(id);
    await load();
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "7px 11px",
    borderRadius: 7,
    border: "1px solid #444",
    background: "#16213e",
    color: "#fff",
    fontSize: 13,
    boxSizing: "border-box",
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "2rem 1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: "#fff" }}>
          Budget & Overspend Warnings
        </h1>
        <div style={{ display: "flex", gap: 10 }}>
          <button
            onClick={() => setOnlyWarnings(!onlyWarnings)}
            style={{
              background: onlyWarnings ? "#FF9800" : "#2a2a3e",
              color: "#fff",
              border: "1px solid #FF9800",
              borderRadius: 7,
              padding: "8px 14px",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {onlyWarnings ? "Show All" : "Warnings Only"}
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            style={{
              background: "#3F51B5",
              color: "#fff",
              border: "none",
              borderRadius: 7,
              padding: "8px 16px",
              cursor: "pointer",
              fontWeight: 700,
              fontSize: 13,
            }}
          >
            {showForm ? "Cancel" : "+ Set Budget"}
          </button>
        </div>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          style={{
            background: "#16213e",
            borderRadius: 12,
            padding: "1.25rem",
            marginBottom: 20,
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
            alignItems: "flex-end",
          }}
        >
          <div style={{ flex: "1 1 160px" }}>
            <label style={{ display: "block", fontSize: 11, color: "#aaa", marginBottom: 4 }}>
              Category
            </label>
            <select
              style={inputStyle}
              required
              value={form.category_id || ""}
              onChange={(e) => setForm({ ...form, category_id: Number(e.target.value) })}
            >
              <option value="">Select…</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ flex: "1 1 120px" }}>
            <label style={{ display: "block", fontSize: 11, color: "#aaa", marginBottom: 4 }}>
              Monthly Limit (₹)
            </label>
            <input
              style={inputStyle}
              type="number"
              min={1}
              step="0.01"
              required
              value={form.budget_limit || ""}
              onChange={(e) => setForm({ ...form, budget_limit: parseFloat(e.target.value) })}
            />
          </div>
          <div style={{ flex: "1 1 100px" }}>
            <label style={{ display: "block", fontSize: 11, color: "#aaa", marginBottom: 4 }}>
              Warn at %
            </label>
            <input
              style={inputStyle}
              type="number"
              min={1}
              max={100}
              value={form.warning_threshold_pct ?? 80}
              onChange={(e) =>
                setForm({ ...form, warning_threshold_pct: Number(e.target.value) })
              }
            />
          </div>
          <button
            type="submit"
            disabled={saving}
            style={{
              background: saving ? "#555" : "#4CAF50",
              color: "#fff",
              border: "none",
              borderRadius: 7,
              padding: "9px 20px",
              cursor: saving ? "not-allowed" : "pointer",
              fontWeight: 700,
              fontSize: 13,
              height: 36,
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </form>
      )}

      {report && (
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          <SummaryPill label="Over Budget" count={report.summary.critical} color="#F44336" />
          <SummaryPill label="Almost Over" count={report.summary.high} color="#FF5722" />
          <SummaryPill label="Warning" count={report.summary.medium} color="#FF9800" />
          <SummaryPill label="On Track" count={report.summary.ok} color="#4CAF50" />
        </div>
      )}

      {loading && <p style={{ color: "#aaa", textAlign: "center" }}>Loading…</p>}

      {!loading && report && (
        <>
          {report.warnings.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                background: "#16213e",
                borderRadius: 12,
                padding: "3rem",
                color: "#aaa",
              }}
            >
              {budgets.length === 0
                ? "No budget limits set yet. Click '+ Set Budget' to add one."
                : "All categories are within budget. Keep it up!"}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {report.warnings.map((w) => (
                <WarningCard key={w.budget_id} w={w} />
              ))}
            </div>
          )}

          {budgets.length > 0 && (
            <div style={{ marginTop: 32 }}>
              <h3 style={{ color: "#fff", marginBottom: 10, fontSize: 15 }}>Configured Budget Limits</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {budgets.map((b) => {
                  const cat = categories.find((c) => c.id === b.category_id);
                  return (
                    <div
                      key={b.id}
                      style={{
                        background: "#16213e",
                        borderRadius: 8,
                        padding: "10px 14px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: 13,
                      }}
                    >
                      <span style={{ color: "#fff", fontWeight: 600 }}>
                        {cat?.name ?? `Category #${b.category_id}`}
                      </span>
                      <span style={{ color: "#aaa" }}>
                        ₹{b.budget_limit.toLocaleString()} / {b.month ?? "every month"} · warn @{b.warning_threshold_pct}%
                      </span>
                      <button
                        onClick={() => handleDelete(b.id)}
                        style={{
                          background: "none",
                          border: "1px solid #F44336",
                          color: "#F44336",
                          borderRadius: 5,
                          cursor: "pointer",
                          fontSize: 11,
                          padding: "3px 10px",
                        }}
                      >
                        Remove
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
