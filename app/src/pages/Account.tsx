import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { me, updateMe } from '@/api/auth';
import { setCurrency } from '@/lib/auth';
import { exportPII, requestDeletion, confirmDeletion, cancelDeletion, getDeletionStatus } from '@/api/gdpr';

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

  // GDPR state
  const [exporting, setExporting] = useState(false);
  const [deletionStatus, setDeletionStatus] = useState<string | null>(null);
  const [confirmToken, setConfirmToken] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteReason, setDeleteReason] = useState('');
  const [gdprLoading, setGdprLoading] = useState(false);

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

  useEffect(() => {
    getDeletionStatus().then((s) => setDeletionStatus(s.status ?? null)).catch(() => null);
  }, []);

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await exportPII();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `finmind-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast({ title: 'Export downloaded', description: 'Your data has been exported.' });
    } catch {
      toast({ title: 'Export failed', variant: 'destructive' });
    } finally {
      setExporting(false);
    }
  };

  const handleRequestDeletion = async () => {
    setGdprLoading(true);
    try {
      const res = await requestDeletion(deleteReason || undefined);
      setConfirmToken(res.confirmation_token);
      setDeletionStatus('PENDING');
      setShowDeleteConfirm(false);
      toast({ title: 'Deletion requested', description: `Token: ${res.confirmation_token}` });
    } catch {
      toast({ title: 'Request failed', variant: 'destructive' });
    } finally {
      setGdprLoading(false);
    }
  };

  const handleConfirmDeletion = async () => {
    if (!confirmToken) return;
    setGdprLoading(true);
    try {
      await confirmDeletion(confirmToken);
      toast({ title: 'Account deleted', description: 'All your data has been permanently removed.' });
    } catch {
      toast({ title: 'Confirmation failed', variant: 'destructive' });
    } finally {
      setGdprLoading(false);
    }
  };

  const handleCancelDeletion = async () => {
    setGdprLoading(true);
    try {
      await cancelDeletion();
      setDeletionStatus(null);
      setConfirmToken('');
      toast({ title: 'Deletion cancelled' });
    } catch {
      toast({ title: 'Cancel failed', variant: 'destructive' });
    } finally {
      setGdprLoading(false);
    }
  };

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

      {/* GDPR / Privacy */}
      <div className="card card-interactive space-y-5 fade-in-up">
        <div>
          <h2 className="text-base font-semibold">Privacy & Data</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Export or permanently delete your personal data (GDPR Article 17).
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <Button
            variant="outline"
            onClick={() => { void handleExport(); }}
            disabled={exporting}
            className="w-full sm:w-auto"
          >
            {exporting ? 'Preparing export...' : 'Download My Data'}
          </Button>

          {deletionStatus === 'PENDING' ? (
            <div className="space-y-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
              <p className="text-sm font-medium text-destructive">Deletion request pending</p>
              <p className="text-xs text-muted-foreground">
                Paste your confirmation token below to permanently delete your account and all data.
                This cannot be undone.
              </p>
              <input
                className="input text-sm"
                placeholder="Confirmation token"
                value={confirmToken}
                onChange={(e) => setConfirmToken(e.target.value)}
              />
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={!confirmToken || gdprLoading}
                  onClick={() => { void handleConfirmDeletion(); }}
                >
                  Permanently Delete Account
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={gdprLoading}
                  onClick={() => { void handleCancelDeletion(); }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : !deletionStatus ? (
            showDeleteConfirm ? (
              <div className="space-y-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
                <p className="text-sm font-medium text-destructive">Request account deletion</p>
                <input
                  className="input text-sm"
                  placeholder="Reason (optional)"
                  value={deleteReason}
                  onChange={(e) => setDeleteReason(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={gdprLoading}
                    onClick={() => { void handleRequestDeletion(); }}
                  >
                    {gdprLoading ? 'Processing...' : 'Request Deletion'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setShowDeleteConfirm(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="outline"
                className="w-full sm:w-auto border-destructive/50 text-destructive hover:bg-destructive/10"
                onClick={() => setShowDeleteConfirm(true)}
              >
                Delete My Account
              </Button>
            )
          ) : null}
        </div>
      </div>
    </div>
  );
}
