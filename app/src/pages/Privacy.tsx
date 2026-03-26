import { useEffect, useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import {
  exportData,
  requestDeletion,
  cancelDeletion,
  confirmDeletion,
  deletionStatus,
  anonymizeAccount,
} from '@/api/gdpr';
import type { DeletionStatus } from '@/api/gdpr';
import { clearToken, clearRefreshToken } from '@/lib/auth';

export default function Privacy() {
  const { toast } = useToast();

  // Deletion state
  const [delStatus, setDelStatus] = useState<DeletionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Form state
  const [password, setPassword] = useState('');
  const [reason, setReason] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [anonPassword, setAnonPassword] = useState('');

  // Operation flags
  const [exporting, setExporting] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [anonymizing, setAnonymizing] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const status = await deletionStatus();
      setDelStatus(status);
    } catch {
      // ignore -- user may not be authenticated yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  // --- Export ---
  const handleExport = async () => {
    setExporting(true);
    try {
      const pkg = await exportData();
      // Trigger download as JSON file
      const blob = new Blob([JSON.stringify(pkg, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `finmind-data-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast({
        title: 'Export complete',
        description: 'Your data has been downloaded.',
      });
    } catch (error: unknown) {
      const msg =
        error instanceof Error ? error.message : 'Export failed';
      toast({ title: 'Export failed', description: msg });
    } finally {
      setExporting(false);
    }
  };

  // --- Request Deletion ---
  const handleRequestDeletion = async () => {
    if (!password) {
      toast({
        title: 'Password required',
        description: 'Enter your password to request deletion.',
      });
      return;
    }
    setRequesting(true);
    try {
      const result = await requestDeletion(password, reason || undefined);
      toast({ title: 'Deletion requested', description: result.message });
      setPassword('');
      setReason('');
      await loadStatus();
    } catch (error: unknown) {
      const msg =
        error instanceof Error ? error.message : 'Request failed';
      toast({ title: 'Deletion request failed', description: msg });
    } finally {
      setRequesting(false);
    }
  };

  // --- Cancel Deletion ---
  const handleCancelDeletion = async () => {
    setCancelling(true);
    try {
      const result = await cancelDeletion();
      toast({ title: 'Deletion cancelled', description: result.message });
      await loadStatus();
    } catch (error: unknown) {
      const msg =
        error instanceof Error ? error.message : 'Cancel failed';
      toast({ title: 'Cancel failed', description: msg });
    } finally {
      setCancelling(false);
    }
  };

  // --- Confirm Immediate Deletion ---
  const handleConfirmDeletion = async () => {
    if (!confirmPassword) {
      toast({
        title: 'Password required',
        description: 'Enter your password to confirm deletion.',
      });
      return;
    }
    setConfirming(true);
    try {
      const result = await confirmDeletion(confirmPassword);
      toast({ title: 'Account deleted', description: result.message });
      clearToken();
      clearRefreshToken();
      window.location.href = '/';
    } catch (error: unknown) {
      const msg =
        error instanceof Error ? error.message : 'Deletion failed';
      toast({ title: 'Deletion failed', description: msg });
    } finally {
      setConfirming(false);
    }
  };

  // --- Anonymize ---
  const handleAnonymize = async () => {
    if (!anonPassword) {
      toast({
        title: 'Password required',
        description: 'Enter your password to anonymize your data.',
      });
      return;
    }
    setAnonymizing(true);
    try {
      const result = await anonymizeAccount(anonPassword);
      toast({ title: 'Data anonymized', description: result.message });
      setAnonPassword('');
    } catch (error: unknown) {
      const msg =
        error instanceof Error ? error.message : 'Anonymization failed';
      toast({ title: 'Anonymization failed', description: msg });
    } finally {
      setAnonymizing(false);
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Privacy &amp; Data</h1>
          <p className="page-subtitle">
            Manage your personal data. Export everything, anonymize, or
            permanently delete your account in compliance with GDPR.
          </p>
        </div>
      </div>

      {/* Export Section */}
      <div className="card card-interactive space-y-4 fade-in-up">
        <h2 className="text-lg font-semibold">Export Your Data</h2>
        <p className="text-sm text-muted-foreground">
          Download a JSON file containing all of your personal data including
          profile, expenses, bills, reminders, categories, and subscriptions.
        </p>
        <div className="flex justify-end">
          <Button
            variant="financial"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? 'Exporting...' : 'Download My Data'}
          </Button>
        </div>
      </div>

      {/* Anonymization Section */}
      <div className="card card-interactive space-y-4 fade-in-up">
        <h2 className="text-lg font-semibold">Anonymize Data</h2>
        <p className="text-sm text-muted-foreground">
          Replace your personal information with anonymous placeholders while
          keeping your financial records. Your email and free-text fields will
          be redacted. This action cannot be undone.
        </p>
        <div className="space-y-2">
          <Label htmlFor="anon_password">Confirm Password</Label>
          <Input
            id="anon_password"
            type="password"
            placeholder="Enter your password"
            value={anonPassword}
            onChange={(e) => setAnonPassword(e.target.value)}
          />
        </div>
        <div className="flex justify-end">
          <Button
            variant="destructive"
            onClick={handleAnonymize}
            disabled={anonymizing || !anonPassword}
          >
            {anonymizing ? 'Anonymizing...' : 'Anonymize My Data'}
          </Button>
        </div>
      </div>

      {/* Deletion Section */}
      <div className="card card-interactive space-y-4 fade-in-up border-destructive/30">
        <h2 className="text-lg font-semibold text-destructive">
          Delete Account
        </h2>

        {loading ? (
          <div className="text-sm text-muted-foreground">
            Checking deletion status...
          </div>
        ) : delStatus?.pending ? (
          <div className="space-y-4">
            <div className="rounded-md bg-destructive/10 p-4 text-sm">
              <p className="font-medium text-destructive">
                Deletion is scheduled
              </p>
              <p className="mt-1 text-muted-foreground">
                Your account will be permanently deleted on{' '}
                <strong>
                  {delStatus.scheduled_at
                    ? new Date(delStatus.scheduled_at).toLocaleDateString()
                    : 'N/A'}
                </strong>
                . You can cancel before that date.
              </p>
            </div>
            <div className="flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={handleCancelDeletion}
                disabled={cancelling}
              >
                {cancelling ? 'Cancelling...' : 'Cancel Deletion'}
              </Button>
              <div className="space-y-2 flex-1 max-w-xs">
                <Input
                  type="password"
                  placeholder="Password to confirm now"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
              <Button
                variant="destructive"
                onClick={handleConfirmDeletion}
                disabled={confirming || !confirmPassword}
              >
                {confirming ? 'Deleting...' : 'Delete Now'}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Request permanent deletion of your account and all associated
              data. A 30-day grace period applies -- you can cancel any time
              during that window. Alternatively, confirm to delete immediately.
            </p>
            <div className="space-y-2">
              <Label htmlFor="del_password">Password</Label>
              <Input
                id="del_password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="del_reason">Reason (optional)</Label>
              <Textarea
                id="del_reason"
                placeholder="Tell us why you are leaving..."
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
              />
            </div>
            <div className="flex gap-3 justify-end">
              <Button
                variant="outline"
                onClick={handleRequestDeletion}
                disabled={requesting || !password}
              >
                {requesting
                  ? 'Requesting...'
                  : 'Request Deletion (30-day grace)'}
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  setConfirmPassword(password);
                  if (password) {
                    void handleConfirmDeletion();
                  }
                }}
                disabled={confirming || !password}
              >
                {confirming ? 'Deleting...' : 'Delete Immediately'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
