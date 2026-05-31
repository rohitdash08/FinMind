import { useState, useEffect, useCallback } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardFooter, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { CreditCard, Plus, AlertTriangle, CheckCircle, Clock, DollarSign, Filter, Search, Bell } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { listBills, createBill, markBillPaid, deleteBill, type Bill } from '@/api/bills';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dailog';
import { Link } from 'react-router-dom';
import { formatMoney } from '@/lib/currency';

const upcomingBills = [
  {
    id: 1,
    name: 'Rent Payment',
    amount: 1200.00,
    dueDate: '2025-01-01',
    category: 'Housing',
    status: 'upcoming',
    autopay: true,
    recurring: 'monthly',
    provider: 'Property Management Co.'
  },
  {
    id: 2,
    name: 'Internet Service',
    amount: 79.99,
    dueDate: '2025-01-03',
    category: 'Utilities',
    status: 'upcoming',
    autopay: true,
    recurring: 'monthly',
    provider: 'FastNet ISP'
  },
  {
    id: 3,
    name: 'Phone Bill',
    amount: 65.00,
    dueDate: '2025-01-05',
    category: 'Utilities',
    status: 'overdue',
    autopay: false,
    recurring: 'monthly',
    provider: 'Mobile Connect'
  },
  {
    id: 4,
    name: 'Car Insurance',
    amount: 125.50,
    dueDate: '2025-01-08',
    category: 'Insurance',
    status: 'upcoming',
    autopay: true,
    recurring: 'monthly',
    provider: 'SafeDrive Insurance'
  },
  {
    id: 5,
    name: 'Netflix Subscription',
    amount: 15.99,
    dueDate: '2025-01-12',
    category: 'Entertainment',
    status: 'upcoming',
    autopay: true,
    recurring: 'monthly',
    provider: 'Netflix'
  },
  {
    id: 6,
    name: 'Gym Membership',
    amount: 49.99,
    dueDate: '2025-01-15',
    category: 'Health',
    status: 'upcoming',
    autopay: false,
    recurring: 'monthly',
    provider: 'FitLife Gym'
  }
];

const recentPayments = [
  {
    id: 1,
    name: 'Electricity Bill',
    amount: 89.32,
    paidDate: '2024-12-28',
    method: 'Auto-pay',
    status: 'paid'
  },
  {
    id: 2,
    name: 'Water & Sewer',
    amount: 45.67,
    paidDate: '2024-12-25',
    method: 'Manual',
    status: 'paid'
  },
  {
    id: 3,
    name: 'Spotify Premium',
    amount: 9.99,
    paidDate: '2024-12-22',
    method: 'Auto-pay',
    status: 'paid'
  },
  {
    id: 4,
    name: 'Credit Card Payment',
    amount: 387.50,
    paidDate: '2024-12-20',
    method: 'Manual',
    status: 'paid'
  }
];

const billCategories = [
  { name: 'Housing', count: 2, amount: 1289.99, color: 'bg-primary' },
  { name: 'Utilities', count: 3, amount: 215.65, color: 'bg-success' },
  { name: 'Insurance', count: 2, amount: 245.00, color: 'bg-warning' },
  { name: 'Entertainment', count: 4, amount: 67.96, color: 'bg-accent' },
  { name: 'Health', count: 1, amount: 49.99, color: 'bg-secondary' }
];

export function Bills() {
  // const [selectedFilter, setSelectedFilter] = useState('all');
  // Live data wiring
  const { toast } = useToast();
  const [items, setItems] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [amount, setAmount] = useState('');
  const [due, setDue] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);

  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listBills();
      setItems(data);
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to load bills');
      setError(message);
      toast({ title: 'Failed to load bills', description: message || 'Please try again.' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate() {
    if (!name.trim() || !amount) return;
    setSaving(true);
    try {
      await createBill({ name: name.trim(), amount: Number(amount), next_due_date: due });
      await refresh();
      setOpen(false);
      setName('');
      setAmount('');
      setDue(new Date().toISOString().slice(0, 10));
      toast({ title: 'Bill created' });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to create bill');
      setError(message);
      toast({ title: 'Failed to create bill', description: message || 'Please try again.' });
    } finally {
      setSaving(false);
    }
  }

  async function onMarkPaid(id: number) {
    try {
      await markBillPaid(id);
      toast({ title: 'Marked as paid' });
      refresh();
    } catch (error: unknown) {
      toast({ title: 'Failed to mark paid', description: getErrorMessage(error, 'Please try again.') });
    }
  }

  const totalUpcoming = upcomingBills.reduce((sum, bill) => sum + bill.amount, 0);
  const overdueBills = upcomingBills.filter(bill => bill.status === 'overdue');
  const autoPaidBills = upcomingBills.filter(bill => bill.autopay);

  return (
    <div className="page-wrap">
        {/* Live Bills (wired to backend) */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xl font-semibold">Your Bills</h2>
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button variant="financial" size="sm">
                  <Plus className="w-4 h-4" />
                  Add Bill
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>New Bill</DialogTitle>
                  <DialogDescription>Create a bill to track upcoming payments.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm mb-1">Name</label>
                    <input className="input w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="Internet" />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm mb-1">Amount</label>
                      <input className="input w-full" type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
                    </div>
                    <div>
                      <label className="block text-sm mb-1">Next Due Date</label>
                      <input className="input w-full" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
                    </div>
                  </div>
                </div>
                {error && <div className="error mt-2">{error}</div>}
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
                  <Button onClick={onCreate} disabled={saving || !name.trim() || !amount}>Create</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
          <div className="card fade-in-up">
            {loading ? (
              <div>Loading…</div>
            ) : items.length === 0 ? (
              <div className="text-sm text-muted-foreground">No bills yet. Add your first bill.</div>
            ) : (
              <div className="space-y-2">
                {items.map((b) => (
                  <div key={b.id} className="interactive-row flex items-center justify-between border-b py-2">
                    <div>
                      <div className="font-medium">{b.name}</div>
                      <div className="text-xs text-muted-foreground">
                        Due {b.next_due_date || '—'} • {formatMoney(Number(b.amount || 0), b.currency)}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => onMarkPaid(b.id)}>Mark Paid</Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="sm">Delete</Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Delete bill?</AlertDialogTitle>
                            <AlertDialogDescription>This action cannot be undone.</AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={async () => {
                                try {
                                  await deleteBill(b.id);
                                  setItems((prev) => prev.filter((x) => x.id !== b.id));
                                  toast({ title: 'Bill deleted' });
                                } catch (error: unknown) {
                                  toast({ title: 'Failed to delete bill', description: getErrorMessage(error, 'Please try again.') });
                                }
                              }}
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        {/* Header */}
        <div className="page-header">
          <div className="relative flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="page-title">Bill Management</h1>
            <p className="page-subtitle">
              Stay on top of your bills and never miss a payment
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" size="sm" asChild>
              <Link to="/reminders">
                <Bell className="w-4 h-4" />
                Reminders
              </Link>
            </Button>
            <Button variant="financial" size="sm">
              <Plus className="w-4 h-4" />
              Add Bill
            </Button>
          </div>
          </div>
        </div>

        {/* Bills Overview */}
        <div className="grid gap-4 md:grid-cols-4 mb-8">
          <FinancialCard variant="financial">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Upcoming Bills
                </FinancialCardTitle>
                <Clock className="w-5 h-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                ${totalUpcoming.toLocaleString()}
              </div>
              <div className="text-sm text-muted-foreground">
                {upcomingBills.length} bills this month
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant={overdueBills.length > 0 ? "destructive" : "success"}>
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium">
                  Overdue Bills
                </FinancialCardTitle>
                <AlertTriangle className="w-5 h-5" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value mb-1">
                {overdueBills.length}
              </div>
              <div className="text-sm opacity-80">
                {overdueBills.length > 0 ? 'Needs attention' : 'All caught up!'}
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Auto-Pay Enabled
                </FinancialCardTitle>
                <CheckCircle className="w-5 h-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                {autoPaidBills.length}
              </div>
              <div className="text-sm text-muted-foreground">
                of {upcomingBills.length} bills
              </div>
            </FinancialCardContent>
          </FinancialCard>

          <FinancialCard variant="financial">
            <FinancialCardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <FinancialCardTitle className="text-sm font-medium text-muted-foreground">
                  Monthly Average
                </FinancialCardTitle>
                <DollarSign className="w-5 h-5 text-muted-foreground" />
              </div>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="metric-value text-foreground mb-1">
                ${(totalUpcoming * 0.92).toLocaleString()}
              </div>
              <div className="text-sm text-muted-foreground">
                Last 6 months
              </div>
            </FinancialCardContent>
          </FinancialCard>
        </div>

        {/* Main Content */}
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Upcoming Bills */}
          <div className="lg:col-span-2">
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="section-title">Upcoming Bills</FinancialCardTitle>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm">
                      <Filter className="w-4 h-4" />
                    </Button>
                    <Button variant="ghost" size="sm">
                      <Search className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
                <FinancialCardDescription>
                  Bills due in the next 30 days
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-4">
                  {upcomingBills.map((bill) => (
                    <div key={bill.id} className="interactive-row flex items-center justify-between p-4 rounded-lg border border-border">
                      <div className="flex items-center space-x-4">
                        <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                          bill.status === 'overdue' 
                            ? 'bg-destructive-light text-destructive' 
                            : bill.autopay 
                              ? 'bg-success-light text-success'
                              : 'bg-warning-light text-warning'
                        }`}>
                          {bill.status === 'overdue' ? (
                            <AlertTriangle className="w-6 h-6" />
                          ) : bill.autopay ? (
                            <CheckCircle className="w-6 h-6" />
                          ) : (
                            <CreditCard className="w-6 h-6" />
                          )}
                        </div>
                        <div>
                          <div className="font-medium text-foreground">
                            {bill.name}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {bill.provider} • Due {new Date(bill.dueDate).toLocaleDateString()}
                          </div>
                          <div className="flex items-center space-x-2 mt-1">
                            <Badge variant="outline" className="text-xs">
                              {bill.category}
                            </Badge>
                            {bill.autopay && (
                              <Badge variant="secondary" className="text-xs">
                                Auto-pay
                              </Badge>
                            )}
                            {bill.status === 'overdue' && (
                              <Badge variant="destructive" className="text-xs">
                                Overdue
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-semibold text-foreground">
                          ${bill.amount.toFixed(2)}
                        </div>
                        <Button variant="ghost" size="sm" className="mt-1">
                          Pay Now
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Categories */}
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <FinancialCardTitle className="section-title">Categories</FinancialCardTitle>
                <FinancialCardDescription>
                  Bills by category
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-3">
                  {billCategories.map((category, index) => (
                    <div key={index} className="interactive-row flex items-center justify-between p-3 rounded-lg">
                      <div className="flex items-center space-x-3">
                        <div className={`w-4 h-4 rounded-full ${category.color}`}></div>
                        <div>
                          <div className="font-medium text-foreground text-sm">
                            {category.name}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {category.count} bills
                          </div>
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-foreground">
                        ${category.amount.toFixed(2)}
                      </div>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
            </FinancialCard>

            {/* Recent Payments */}
            <FinancialCard variant="financial" className="fade-in-up">
              <FinancialCardHeader>
                <FinancialCardTitle className="section-title">Recent Payments</FinancialCardTitle>
                <FinancialCardDescription>
                  Recently paid bills
                </FinancialCardDescription>
              </FinancialCardHeader>
              <FinancialCardContent>
                <div className="space-y-3">
                  {recentPayments.map((payment) => (
                    <div key={payment.id} className="interactive-row flex items-center justify-between p-3 rounded-lg">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 rounded-lg bg-success-light text-success flex items-center justify-center">
                          <CheckCircle className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="font-medium text-foreground text-sm">
                            {payment.name}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {new Date(payment.paidDate).toLocaleDateString()} • {payment.method}
                          </div>
                        </div>
                      </div>
                      <div className="text-sm font-semibold text-foreground">
                        ${payment.amount.toFixed(2)}
                      </div>
                    </div>
                  ))}
                </div>
              </FinancialCardContent>
              <FinancialCardFooter>
                <Button variant="ghost" size="sm" className="w-full">
                  View All Payments
                </Button>
              </FinancialCardFooter>
            </FinancialCard>
          </div>
        </div>
    </div>
  );
}
