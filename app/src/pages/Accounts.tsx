import { useEffect, useState } from "react";
import {
  createAccount,
  deleteAccount,
  getAccountsOverview,
  type AccountsOverview,
  type AccountType,
  type CreateAccountPayload,
  type FinancialAccount,
} from "../api/accounts";

const TYPE_LABELS: Record<AccountType, string> = {
  CHECKING: "Checking",
  SAVINGS: "Savings",
  CREDIT: "Credit",
  CASH: "Cash",
  INVESTMENT: "Investment",
  OTHER: "Other",
};

const TYPE_COLORS: Record<AccountType, string> = {
  CHECKING: "#4CAF50",
  SAVINGS: "#2196F3",
  CREDIT: "#F44336",
  CASH: "#FF9800",
  INVESTMENT: "#9C27B0",
  OTHER: "#607D8B",
};

function formatAmount(amount: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

function AccountCard({
  account,
  onDelete,
}: {
  account: FinancialAccount;
  onDelete: (id: number) => void;
}) {
  const color = account.color ?? TYPE_COLORS[account.account_type] ?? "#607D8B";
  const isNegative = account.current_balance < 0;
  return (
    <div
      style={{
        border: `2px solid ${color}`,
        borderRadius: 12,
        padding: "1rem 1.25rem",
        background: "#1a1a2e",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        position: "relative",
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          color,
          textTransform: "uppercase",
          letterSpacing: 1,
        }}
      >
        {TYPE_LABELS[account.account_type]}
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>
        {account.name}
      </div>
      <div
        style={{
          fontSize: 22,
          fontWeight: 800,
          color: isNegative ? "#F44336" : "#4CAF50",
        }}
      >
        {formatAmount(account.current_balance, account.currency)}
      </div>
      <div style={{ fontSize: 11, color: "#aaa" }}>
        Opening: {formatAmount(account.initial_balance, account.currency)}
      </div>
      <button
        onClick={() => onDelete(account.id)}
        style={{
          position: "absolute",
          top: 10,
          right: 10,
          background: "rgba(244,67,54,0.15)",
          border: "1px solid #F44336",
          borderRadius: 6,
          color: "#F44336",
          cursor: "pointer",
          fontSize: 11,
          padding: "2px 8px",
        }}
      >
        Remove
      </button>
    </div>
  );
}

function NetWorthBanner({ overview }: { overview: AccountsOverview }) {
  return (
    <div
      style={{
        background: "linear-gradient(135deg, #1a237e 0%, #283593 100%)",
        borderRadius: 16,
        padding: "1.5rem 2rem",
        marginBottom: 24,
        color: "#fff",
      }}
    >
      <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 4 }}>
        Total Net Worth
      </div>
      <div style={{ fontSize: 36, fontWeight: 900, letterSpacing: -1 }}>
        {formatAmount(overview.net_worth)}
      </div>
      <div
        style={{
          display: "flex",
          gap: 32,
          marginTop: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div style={{ fontSize: 11, opacity: 0.6 }}>Total Assets</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#69F0AE" }}>
            {formatAmount(overview.total_assets)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, opacity: 0.6 }}>Total Liabilities</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#FF5252" }}>
            {formatAmount(overview.total_liabilities)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, opacity: 0.6 }}>Accounts</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>
            {overview.account_count}
          </div>
        </div>
      </div>
    </div>
  );
}

const EMPTY_FORM: CreateAccountPayload = {
  name: "",
  account_type: "CHECKING",
  currency: "INR",
  initial_balance: 0,
  color: "",
};

export default function Accounts() {
  const [overview, setOverview] = useState<AccountsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreateAccountPayload>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getAccountsOverview();
      setOverview(data);
    } catch {
      setError("Failed to load accounts. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDelete = async (id: number) => {
    if (!confirm("Remove this account?")) return;
    try {
      await deleteAccount(id);
      await load();
    } catch {
      alert("Failed to remove account.");
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await createAccount({
        ...form,
        initial_balance: Number(form.initial_balance ?? 0),
        color: form.color || undefined,
      });
      setForm(EMPTY_FORM);
      setShowForm(false);
      await load();
    } catch {
      alert("Failed to create account. Check the details and try again.");
    } finally {
      setSaving(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "8px 12px",
    borderRadius: 8,
    border: "1px solid #333",
    background: "#16213e",
    color: "#fff",
    fontSize: 14,
    boxSizing: "border-box",
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "2rem 1rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 24,
        }}
      >
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: "#fff" }}>
          My Accounts
        </h1>
        <button
          onClick={() => setShowForm(!showForm)}
          style={{
            background: "#3F51B5",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "10px 20px",
            cursor: "pointer",
            fontWeight: 700,
            fontSize: 14,
          }}
        >
          {showForm ? "Cancel" : "+ Add Account"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          style={{
            background: "#16213e",
            borderRadius: 12,
            padding: "1.5rem",
            marginBottom: 24,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <h3 style={{ margin: 0, color: "#fff" }}>New Account</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, color: "#aaa", marginBottom: 4 }}>
                Account Name *
              </label>
              <input
                style={inputStyle}
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Main Checking"
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, color: "#aaa", marginBottom: 4 }}>
                Account Type
              </label>
              <select
                style={inputStyle}
                value={form.account_type}
                onChange={(e) =>
                  setForm({ ...form, account_type: e.target.value as AccountType })
                }
              >
                {Object.entries(TYPE_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, color: "#aaa", marginBottom: 4 }}>
                Opening Balance
              </label>
              <input
                style={inputStyle}
                type="number"
                step="0.01"
                value={form.initial_balance}
                onChange={(e) =>
                  setForm({ ...form, initial_balance: parseFloat(e.target.value) || 0 })
                }
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, color: "#aaa", marginBottom: 4 }}>
                Currency
              </label>
              <input
                style={inputStyle}
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
                placeholder="INR"
                maxLength={10}
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={saving}
            style={{
              background: saving ? "#555" : "#4CAF50",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "10px 24px",
              cursor: saving ? "not-allowed" : "pointer",
              fontWeight: 700,
              alignSelf: "flex-start",
            }}
          >
            {saving ? "Saving..." : "Create Account"}
          </button>
        </form>
      )}

      {loading && (
        <p style={{ color: "#aaa", textAlign: "center" }}>Loading accounts…</p>
      )}
      {error && (
        <p style={{ color: "#F44336", textAlign: "center" }}>{error}</p>
      )}
      {!loading && !error && overview && (
        <>
          <NetWorthBanner overview={overview} />
          {overview.accounts.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                color: "#aaa",
                padding: "3rem",
                background: "#16213e",
                borderRadius: 12,
              }}
            >
              <p style={{ fontSize: 18, marginBottom: 8 }}>No accounts yet</p>
              <p style={{ fontSize: 13 }}>
                Add your first account to start tracking your finances across
                multiple accounts.
              </p>
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                gap: 16,
              }}
            >
              {overview.accounts.map((a) => (
                <AccountCard key={a.id} account={a} onDelete={handleDelete} />
              ))}
            </div>
          )}
          {Object.keys(overview.by_type).length > 0 && (
            <div style={{ marginTop: 32 }}>
              <h3 style={{ color: "#fff", marginBottom: 12 }}>By Account Type</h3>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {Object.entries(overview.by_type).map(([type, stats]) => (
                  <div
                    key={type}
                    style={{
                      background: "#16213e",
                      borderRadius: 10,
                      padding: "12px 18px",
                      minWidth: 150,
                      borderLeft: `4px solid ${TYPE_COLORS[type as AccountType] ?? "#607D8B"}`,
                    }}
                  >
                    <div style={{ fontSize: 11, color: "#aaa", marginBottom: 4 }}>
                      {TYPE_LABELS[type as AccountType] ?? type} ({stats.count})
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>
                      {formatAmount(stats.total_balance)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
