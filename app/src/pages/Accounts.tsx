import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { Wallet, CreditCard, PiggyBank, TrendingUp, Plus, Trash2, DollarSign } from 'lucide-react';

interface Account {
  id: number;
  name: string;
  account_type: string;
  balance: number;
  currency: string;
  color: string;
  icon?: string;
}

const accountTypes = [
  { value: 'bank', label: 'Bank Account', icon: Wallet },
  { value: 'credit_card', label: 'Credit Card', icon: CreditCard },
  { value: 'cash', label: 'Cash', icon: DollarSign },
  { value: 'investment', label: 'Investment', icon: TrendingUp },
  { value: 'savings', label: 'Savings', icon: PiggyBank },
];

const colorOptions = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    account_type: 'bank',
    balance: 0,
    currency: 'USD',
    color: '#3B82F6'
  });
  const [loading, setLoading] = useState(true);

  const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

  const fetchAccounts = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/accounts/summary`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setAccounts(data.accounts || []);
      }
    } catch (error) {
      console.error('Failed to fetch accounts:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  const handleSubmit = async () => {
    try {
      const token = localStorage.getItem('token');
      const url = editingAccount 
        ? `${API_BASE}/accounts/${editingAccount.id}`
        : `${API_BASE}/accounts`;
      const method = editingAccount ? 'PUT' : 'POST';
      
      const res = await fetch(url, {
        method,
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });
      
      if (res.ok) {
        setIsOpen(false);
        setFormData({ name: '', account_type: 'bank', balance: 0, currency: 'USD', color: '#3B82F6' });
        setEditingAccount(null);
        fetchAccounts();
      }
    } catch (error) {
      console.error('Failed to save account:', error);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/accounts/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        fetchAccounts();
      }
    } catch (error) {
      console.error('Failed to delete account:', error);
    }
  };

  const openEdit = (account: Account) => {
    setEditingAccount(account);
    setFormData({
      name: account.name,
      account_type: account.account_type,
      balance: account.balance,
      currency: account.currency,
      color: account.color
    });
    setIsOpen(true);
  };

  const totalByCurrency = accounts.reduce((acc, a) => {
    acc[a.currency] = (acc[a.currency] || 0) + a.balance;
    return acc;
  }, {} as Record<string, number>);

  if (loading) {
    return <div className="p-6">Loading...</div>;
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Wallet className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Accounts</h1>
        </div>
        <Button onClick={() => { setEditingAccount(null); setFormData({ name: '', account_type: 'bank', balance: 0, currency: 'USD', color: '#3B82F6' }); setIsOpen(true); }}>
          <Plus className="h-4 w-4 mr-2" />Add Account
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {Object.entries(totalByCurrency).map(([currency, total]) => (
          <Card key={currency}>
            <CardHeader className="pb-2">
              <CardDescription>Total {currency}</CardDescription>
              <CardTitle className="text-2xl">{currency} {total.toLocaleString()}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      {accounts.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <Wallet className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">No accounts yet. Add your first account!</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {accounts.map((account) => {
            const typeInfo = accountTypes.find(t => t.value === account.account_type);
            const Icon = typeInfo?.icon || Wallet;
            
            return (
              <Card key={account.id} className="hover:bg-accent/50">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <div className="flex items-center gap-3">
                    <div 
                      className="h-10 w-10 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: account.color + '20' }}
                    >
                      <Icon className="h-5 w-5" style={{ color: account.color }} />
                    </div>
                    <div>
                      <CardTitle className="text-lg">{account.name}</CardTitle>
                      <CardDescription>{typeInfo?.label || account.account_type}</CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xl font-bold">
                      {account.currency} {account.balance.toLocaleString()}
                    </span>
                    <Button variant="ghost" size="icon" onClick={() => openEdit(account)}>
                      <TrendingUp className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => handleDelete(account.id)}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </CardHeader>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingAccount ? 'Edit Account' : 'Add New Account'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label>Account Name</Label>
              <Input 
                value={formData.name}
                onChange={(e) => setFormData({...formData, name: e.target.value})}
                placeholder="e.g., Chase Bank"
                className="mt-1"
              />
            </div>
            <div>
              <Label>Account Type</Label>
              <select 
                value={formData.account_type}
                onChange={(e) => setFormData({...formData, account_type: e.target.value})}
                className="w-full mt-1 p-2 border rounded"
              >
                {accountTypes.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Balance</Label>
                <Input 
                  type="number"
                  value={formData.balance}
                  onChange={(e) => setFormData({...formData, balance: parseFloat(e.target.value) || 0})}
                  className="mt-1"
                />
              </div>
              <div>
                <Label>Currency</Label>
                <select 
                  value={formData.currency}
                  onChange={(e) => setFormData({...formData, currency: e.target.value})}
                  className="w-full mt-1 p-2 border rounded"
                >
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                  <option value="GBP">GBP</option>
                  <option value="INR">INR</option>
                  <option value="CNY">CNY</option>
                </select>
              </div>
            </div>
            <div>
              <Label>Color</Label>
              <div className="flex gap-2 mt-2">
                {colorOptions.map(color => (
                  <button
                    key={color}
                    className={`h-8 w-8 rounded-full ${formData.color === color ? 'ring-2 ring-offset-2 ring-primary' : ''}`}
                    style={{ backgroundColor: color }}
                    onClick={() => setFormData({...formData, color})}
                  />
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmit}>{editingAccount ? 'Update' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
