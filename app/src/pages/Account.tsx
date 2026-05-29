import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { deleteAccount, exportPrivacyData, me, updateMe } from '@/api/auth';
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
  const [deleting, setDeleting] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');

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
      const blob = await exportPrivacyData();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      link.href = url;
      link.download = `finmind-data-export-${timestamp}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast({
        title: 'Export ready',
        description: 'Your personal data export has been downloaded.',
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to export account data';
      toast({ title: 'Export failed', description: message });
    } finally {
      setExporting(false);
    }
  };

  const onDelete = async () => {
    if (deleteConfirmation !== 'DELETE_MY_DATA') {
      toast({
        title: 'Confirmation required',
        description: 'Enter DELETE_MY_DATA before deleting this account.',
      });
      return;
    }
    setDeleting(true);
    try {
      await deleteAccount(deleteConfirmation);
      clearToken();
      clearRefreshToken();
      toast({
        title: 'Account deleted',
        description: 'Your FinMind account and personal data were deleted.',
      });
      window.location.assign('/');
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to delete account';
      toast({ title: 'Delete failed', description: message });
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
            Download a ZIP export of your account data or permanently delete the
            account.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Label>Personal data export</Label>
            <p className="text-sm text-muted-foreground">
              Includes profile, expenses, bills, reminders, subscriptions, and
              audit entries.
            </p>
          </div>
          <Button variant="outline" onClick={onExport} disabled={exporting || loading}>
            {exporting ? 'Exporting...' : 'Download Export'}
          </Button>
        </div>
        <div className="space-y-3 border-t border-border pt-4">
          <div>
            <Label htmlFor="delete_confirmation">Delete account</Label>
            <p className="text-sm text-muted-foreground">
              Enter DELETE_MY_DATA to remove your profile and owned records.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              id="delete_confirmation"
              className="input"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              disabled={deleting || loading}
            />
            <Button
              variant="destructive"
              onClick={onDelete}
              disabled={deleting || loading}
            >
              {deleting ? 'Deleting...' : 'Delete Account'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
