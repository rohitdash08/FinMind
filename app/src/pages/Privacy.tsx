import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import {
  requestExport,
  downloadExport,
  deleteAccount,
  getAuditLog,
  type AuditEntry,
} from '@/api/privacy';
import { Download, Trash2, Shield } from 'lucide-react';

export function Privacy() {
  const { toast } = useToast();
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [audit, setAudit] = useState<AuditEntry[]>([]);

  async function loadAudit() {
    try {
      setAudit(await getAuditLog());
    } catch { /* silent */ }
  }

  useEffect(() => { void loadAudit(); }, []);

  async function handleExport() {
    setExporting(true);
    try {
      const { job_id } = await requestExport();
      setExportJobId(job_id);
      toast({ title: 'Export started', description: 'Your data is being prepared.' });
      // Poll until ready
      const poll = setInterval(async () => {
        try {
          await downloadExport(job_id);
          clearInterval(poll);
          setExporting(false);
          setExportJobId(null);
          toast({ title: 'Export ready', description: 'Download started.' });
          void loadAudit();
        } catch {
          // still processing
        }
      }, 2000);
      // Timeout after 30s
      setTimeout(() => { clearInterval(poll); setExporting(false); }, 30000);
    } catch (err: unknown) {
      setExporting(false);
      toast({ title: 'Export failed', description: err instanceof Error ? err.message : 'Unknown error' });
    }
  }

  async function handleDelete() {
    if (deleteConfirm !== 'DELETE') return;
    setDeleting(true);
    try {
      await deleteAccount(deleteConfirm);
      toast({ title: 'Account deletion requested', description: 'Your account has been marked for deletion.' });
      setDeleteConfirm('');
      void loadAudit();
    } catch (err: unknown) {
      toast({ title: 'Failed', description: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-title">Privacy & Data</h1>
          <p className="page-subtitle">Export your data or delete your account. GDPR-ready controls.</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2">
              <Download className="h-4 w-4" /> Export My Data
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Download a ZIP containing your profile, expenses, bills, budgets, and categories as JSON files.
            </p>
            <Button onClick={() => void handleExport()} disabled={exporting}>
              {exporting ? 'Preparing export…' : 'Export My Data'}
            </Button>
            {exportJobId && (
              <p className="text-xs text-muted-foreground">Job ID: {exportJobId}</p>
            )}
          </FinancialCardContent>
        </FinancialCard>

        <FinancialCard variant="financial">
          <FinancialCardHeader>
            <FinancialCardTitle className="flex items-center gap-2 text-destructive">
              <Trash2 className="h-4 w-4" /> Delete My Account
            </FinancialCardTitle>
          </FinancialCardHeader>
          <FinancialCardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              This action is irreversible. Type <strong>DELETE</strong> to confirm.
            </p>
            <Input
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder='Type "DELETE" to confirm'
              aria-label="delete confirmation"
            />
            <Button
              variant="destructive"
              onClick={() => void handleDelete()}
              disabled={deleteConfirm !== 'DELETE' || deleting}
            >
              {deleting ? 'Deleting…' : 'Delete My Account'}
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      </div>

      <FinancialCard variant="financial">
        <FinancialCardHeader>
          <FinancialCardTitle className="flex items-center gap-2">
            <Shield className="h-4 w-4" /> Audit Log
          </FinancialCardTitle>
        </FinancialCardHeader>
        <FinancialCardContent>
          {audit.length === 0 ? (
            <p className="text-sm text-muted-foreground">No privacy requests yet.</p>
          ) : (
            <div className="space-y-2">
              {audit.map((entry, i) => (
                <div key={i} className="flex items-center justify-between rounded-md border p-2 text-sm">
                  <div>
                    <Badge variant="secondary">{entry.action}</Badge>
                    <span className="ml-2 text-muted-foreground">from {entry.ip}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(entry.timestamp).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>
    </div>
  );
}

export default Privacy;
