import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { useToast } from '@/hooks/use-toast';
import { me, updateMe } from '@/api/auth';
import { deletePersonalData, exportPersonalData } from '@/api/privacy';
import { clearRefreshToken, clearToken, setCurrency } from '@/lib/auth';

const SUPPORTED_CURRENCIES = [
  { code: 'INR', label: 'Indian Rupee (INR)' },
  { code: 'USD', label: 'US Dollar (USD)' },
  { code: 'EUR', label: 'Euro (EUR)' },
  { code: 'GBP', label: 'British Pound (GBP)' },
  { code: 'AED', label: 'UAE Dirham (AED)' },
  { code: 'SGD', label: 'Singapore Dollar (SGD)' },
  { code: 'AUD', label: 'Australian Dollar (AUD)' },
  { code: 'CAD', label: 'Canadian Dollar (CAD)' },
  { code: 'JPY', label: 'Japanese Yen (JPY)' },
];

export default function Account() {
  const { toast } = useToast();
  const [email, setEmail] = useState('');
  const [currency, setCurrencyState] = useState('INR');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await me();
        setEmail(data.email);
        setCurrencyState(data.preferred_currency || 'INR');
      } catch (error: unknown) {
        const message =
          error instanceof Error ? error.message : 'Failed to load account';
        toast({ title: 'Failed to load account', description: message });
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [toast]);

  const onSave = async () => {
    setSaving(true);
    try {
      const updated = await updateMe({ preferred_currency: currency });
      setCurrency(updated.preferred_currency);
      toast({
        title: 'Account updated',
        description: `Default currency set to ${updated.preferred_currency}.`,
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to update account';
      toast({ title: 'Failed to update account', description: message });
    } finally {
      setSaving(false);
    }
  };

  const onExport = async () => {
    setExporting(true);
    try {
      const data = await exportPersonalData();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `finmind-personal-data-${new Date()
        .toISOString()
        .slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast({
        title: 'Export ready',
        description: 'Your personal data package has been downloaded.',
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to export data';
      toast({ title: 'Failed to export data', description: message });
    } finally {
      setExporting(false);
    }
  };

  const onDelete = async () => {
    if (!deletePassword) {
      toast({
        title: 'Password required',
        description: 'Enter your password before deleting your account data.',
      });
      return;
    }
    setDeleting(true);
    try {
      await deletePersonalData(deletePassword);
      clearToken();
      clearRefreshToken();
      toast({
        title: 'Personal data deleted',
        description: 'Your account data has been permanently removed.',
      });
      window.location.href = '/';
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to delete data';
      toast({ title: 'Failed to delete data', description: message });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Account Settings</h1>
          <p className="page-subtitle">
            Manage your profile defaults. Currency stays fixed until you change
            it again.
          </p>
        </div>
      </div>

      <div className="card card-interactive space-y-5 fade-in-up">
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading account...</div>
        ) : (
          <>
            <div className="space-y-2">
              <Label>Email</Label>
              <div className="input bg-muted/30">{email}</div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="preferred_currency">Preferred Currency</Label>
              <select
                id="preferred_currency"
                className="input"
                value={currency}
                onChange={(e) => setCurrencyState(e.target.value)}
              >
                {SUPPORTED_CURRENCIES.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end">
              <Button
                variant="financial"
                onClick={onSave}
                disabled={saving || loading}
              >
                {saving ? 'Saving...' : 'Save Preferences'}
              </Button>
            </div>
          </>
        )}
      </div>

      <div className="card card-interactive space-y-5 fade-in-up">
        <div>
          <h2 className="text-lg font-semibold">Privacy Controls</h2>
          <p className="text-sm text-muted-foreground">
            Export your personal data or permanently remove it from FinMind.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Label>Personal data export</Label>
            <p className="text-sm text-muted-foreground">
              Download a JSON package with your profile and financial records.
            </p>
          </div>
          <Button variant="outline" onClick={onExport} disabled={exporting}>
            {exporting ? 'Exporting...' : 'Export Data'}
          </Button>
        </div>
        <div className="space-y-3 border-t pt-4">
          <div>
            <Label htmlFor="delete_password">Delete personal data</Label>
            <p className="text-sm text-muted-foreground">
              This removes your account and all user-owned financial records.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Input
              id="delete_password"
              type="password"
              placeholder="Confirm with password"
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
            />
            <Button
              variant="destructive"
              onClick={onDelete}
              disabled={deleting}
            >
              {deleting ? 'Deleting...' : 'Delete Data'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
