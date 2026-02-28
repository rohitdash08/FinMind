import { useEffect, useState } from 'react';
import { useToast } from '@/hooks/use-toast';

interface AccountSummary {
  user_id: number;
  email: string;
  net_flow: number;
  monthly_income: number;
  monthly_expenses: number;
}

export default function MultiAccountDashboard() {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Demo data - in production this would fetch from API
    setAccounts([
      { user_id: 1, email: 'user1@example.com', net_flow: 500, monthly_income: 3000, monthly_expenses: 2500 },
      { user_id: 2, email: 'user2@example.com', net_flow: -200, monthly_income: 2500, monthly_expenses: 2700 },
    ]);
    setLoading(false);
  }, []);

  const totalNetFlow = accounts.reduce((sum, acc) => sum + acc.net_flow, 0);
  const totalIncome = accounts.reduce((sum, acc) => sum + acc.monthly_income, 0);
  const totalExpenses = accounts.reduce((sum, acc) => sum + acc.monthly_expenses, 0);

  if (loading) return <div>Loading...</div>;

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <h1 className="page-title">Multi-Account Financial Overview</h1>
        <p className="page-subtitle">View all your household accounts in one place.</p>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="card p-4">
          <div className="text-sm text-muted-foreground">Total Net Flow</div>
          <div className={`text-2xl font-bold ${totalNetFlow >= 0 ? 'text-success' : 'text-destructive'}`}>
            ${totalNetFlow}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-muted-foreground">Total Income</div>
          <div className="text-2xl font-bold text-success">${totalIncome}</div>
        </div>
        <div className="card p-4">
          <div className="text-sm text-muted-foreground">Total Expenses</div>
          <div className="text-2xl font-bold text-destructive">${totalExpenses}</div>
        </div>
      </div>

      {/* Account List */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Household Accounts</h2>
        </div>
        <div className="card-content">
          {accounts.length === 0 ? (
            <div className="text-muted-foreground">No accounts found.</div>
          ) : (
            <div className="space-y-4">
              {accounts.map((account) => (
                <div key={account.user_id} className="flex items-center justify-between p-4 border rounded-lg">
                  <div>
                    <div className="font-medium">{account.email}</div>
                    <div className="text-sm text-muted-foreground">ID: {account.user_id}</div>
                  </div>
                  <div className="text-right">
                    <div className={`font-bold ${account.net_flow >= 0 ? 'text-success' : 'text-destructive'}`}>
                      ${account.net_flow}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Income: ${account.monthly_income} | Expenses: ${account.monthly_expenses}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
