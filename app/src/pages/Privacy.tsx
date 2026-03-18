import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';
import { clearToken, clearRefreshToken } from '@/lib/auth';
import { exportData, deleteData, getAuditLog, type AuditLogEntry } from '@/api/pii';
import { Download, Trash2, Shield, AlertTriangle } from 'lucide-react';

const CONFIRMATION_PHRASE = 'DELETE_MY_DATA';

export default function Privacy() {
  const { toast } = useToast();
  const navigate = useNavigate();

  const [exporting, setExporting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [loadingLog, setLoadingLog] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoadingLog(true);
      try {
        const entries = await getAuditLog();
        setAuditLog(entries);
      } catch (error: unknown) {
        const msg = error instanceof Error ? error.message : 'Failed to load audit log';
        toast({ title: 'Failed to load audit log', description: msg });
      } finally {
        setLoadingLog(false);
      }
    };
    void load();
  }, [toast]);

  const handleExport = async () => {
    setExporting(true);
    try {
      await exportData();
      toast({
        title: 'Data exported',
        description: 'Your data download has started.',
      });
      // Refresh audit log
      const entries = await getAuditLog();
      setAuditLog(entries);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Export failed';
      toast({ title: 'Export failed', description: msg });
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async () => {
    if (confirmText !== CONFIRMATION_PHRASE) return;
    setDeleting(true);
    try {
      await deleteData(CONFIRMATION_PHRASE);
      clearToken();
      clearRefreshToken();
      toast({
        title: 'Account deleted',
        description: 'All your personal data has been permanently deleted.',
      });
      navigate('/signin');
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Deletion failed';
      toast({ title: 'Deletion failed', description: msg });
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
      setConfirmText('');
    }
  };

  const formatAction = (action: string) => {
    switch (action) {
      case 'PII_EXPORT':
        return 'Data Export';
      case 'PII_DELETE':
        return 'Account Deletion';
      case 'PII_AUDIT_LOG_VIEW':
        return 'Audit Log Viewed';
      default:
        return action;
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Privacy &amp; Data</h1>
          <p className="page-subtitle">
            Manage your personal data. Export everything or permanently delete
            your account — it&rsquo;s your data, your choice.
          </p>
        </div>
      </div>

      {/* Export Section */}
      <div className="card card-interactive space-y-4 fade-in-up">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Download className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-semibold">Export My Data</h2>
            <p className="text-sm text-muted-foreground">
              Download a complete copy of all your personal data as a JSON file.
              Includes your profile, categories, expenses, bills, reminders, and
              subscriptions.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button
            variant="financial"
            onClick={() => void handleExport()}
            disabled={exporting}
          >
            <Download className="mr-2 h-4 w-4" />
            {exporting ? 'Preparing download...' : 'Export My Data'}
          </Button>
        </div>
      </div>

      {/* Delete Section */}
      <div className="card card-interactive space-y-4 fade-in-up border-destructive/30">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-destructive/10">
            <Trash2 className="h-5 w-5 text-destructive" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-destructive">
              Delete My Account
            </h2>
            <p className="text-sm text-muted-foreground">
              Permanently and irreversibly delete all your personal data.
              This cannot be undone. Your account, expenses, bills, reminders,
              and all associated data will be removed.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button
            variant="destructive"
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete My Account
          </Button>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              Delete Account Permanently
            </DialogTitle>
            <DialogDescription>
              This action is <strong>permanent and irreversible</strong>. All
              your data including expenses, bills, reminders, and account
              information will be permanently deleted.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Label htmlFor="confirm-delete">
              Type <code className="rounded bg-muted px-1.5 py-0.5 text-sm font-mono font-semibold text-destructive">{CONFIRMATION_PHRASE}</code> to confirm:
            </Label>
            <input
              id="confirm-delete"
              type="text"
              className="input"
              placeholder={CONFIRMATION_PHRASE}
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteOpen(false);
                setConfirmText('');
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={confirmText !== CONFIRMATION_PHRASE || deleting}
              onClick={() => void handleDelete()}
            >
              {deleting ? 'Deleting...' : 'Delete Everything'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Audit Log Section */}
      <div className="card card-interactive space-y-4 fade-in-up">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary">
            <Shield className="h-5 w-5 text-secondary-foreground" />
          </div>
          <div>
            <h2 className="text-base font-semibold">Privacy Audit Log</h2>
            <p className="text-sm text-muted-foreground">
              A record of all privacy-related operations performed on your
              account.
            </p>
          </div>
        </div>

        {loadingLog ? (
          <div className="text-sm text-muted-foreground">Loading audit log...</div>
        ) : auditLog.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            No privacy operations recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">Action</th>
                  <th className="pb-2 font-medium">Date &amp; Time</th>
                </tr>
              </thead>
              <tbody>
                {auditLog.map((entry) => (
                  <tr key={entry.id} className="border-b last:border-0">
                    <td className="py-2.5 pr-4 font-medium">
                      {formatAction(entry.action)}
                    </td>
                    <td className="py-2.5 text-muted-foreground">
                      {new Date(entry.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
