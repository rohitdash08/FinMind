import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { clearToken, clearRefreshToken } from '@/lib/auth';
import {
  requestExport,
  downloadExport,
  listDataRequests,
  requestDeletion,
  confirmDeletion,
  DataRequestItem,
} from '@/api/privacy';
import { Download, Trash2, Shield, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react';

type DeleteStep = 'idle' | 'confirming' | 'typing' | 'deleting';

export default function Privacy() {
  const { toast } = useToast();
  const navigate = useNavigate();

  const [requests, setRequests] = useState<DataRequestItem[]>([]);
  const [loadingRequests, setLoadingRequests] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [downloading, setDownloading] = useState<number | null>(null);

  // Deletion flow state
  const [deleteStep, setDeleteStep] = useState<DeleteStep>('idle');
  const [deleteRequestId, setDeleteRequestId] = useState<number | null>(null);
  const [deleteToken, setDeleteToken] = useState<string | null>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  const loadRequests = useCallback(async () => {
    setLoadingRequests(true);
    try {
      const data = await listDataRequests();
      setRequests(data);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to load requests';
      toast({ title: 'Error', description: message });
    } finally {
      setLoadingRequests(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadRequests();
  }, [loadRequests]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const result = await requestExport();
      toast({ title: 'Export Ready', description: result.message });
      await loadRequests();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Export failed';
      toast({ title: 'Export Failed', description: message });
    } finally {
      setExporting(false);
    }
  };

  const handleDownload = async (requestId: number) => {
    setDownloading(requestId);
    try {
      await downloadExport(requestId);
      toast({ title: 'Download Started', description: 'Your data export is downloading.' });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Download failed';
      toast({ title: 'Download Failed', description: message });
    } finally {
      setDownloading(null);
    }
  };

  const handleDeleteRequest = async () => {
    setDeleteStep('confirming');
    try {
      const result = await requestDeletion();
      setDeleteRequestId(result.request_id);
      setDeleteToken(result.confirmation_token);
      setDeleteStep('typing');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Request failed';
      toast({ title: 'Deletion Request Failed', description: message });
      setDeleteStep('idle');
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteRequestId || !deleteToken) return;
    setDeleteStep('deleting');
    try {
      await confirmDeletion(deleteRequestId, deleteToken);
      toast({
        title: 'Account Deleted',
        description: 'Your account and all associated data have been permanently deleted.',
      });
      clearToken();
      clearRefreshToken();
      navigate('/signin');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Deletion failed';
      toast({ title: 'Deletion Failed', description: message });
      setDeleteStep('idle');
      setDeleteConfirmText('');
      setDeleteRequestId(null);
      setDeleteToken(null);
    }
  };

  const handleCancelDelete = () => {
    setDeleteStep('idle');
    setDeleteConfirmText('');
    setDeleteRequestId(null);
    setDeleteToken(null);
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'FAILED':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'PROCESSING':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      default:
        return <Clock className="h-4 w-4 text-yellow-500" />;
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Privacy & Data</h1>
          <p className="page-subtitle">
            Manage your personal data. Export everything or permanently delete your account.
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
            <h2 className="text-lg font-semibold">Your Data</h2>
            <p className="text-sm text-muted-foreground">
              Download a complete copy of all your data as JSON.
            </p>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">
          Your export will include: profile information, expenses, bills, reminders,
          categories, accounts, savings goals, subscriptions, and activity logs.
          The download link expires after 24 hours.
        </p>
        <div className="flex justify-end">
          <Button
            variant="financial"
            onClick={() => { void handleExport(); }}
            disabled={exporting}
          >
            {exporting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                Export My Data
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Delete Account Section */}
      <div className="card card-interactive space-y-4 fade-in-up border-red-200">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-100">
            <Trash2 className="h-5 w-5 text-red-500" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-red-700">Delete Account</h2>
            <p className="text-sm text-muted-foreground">
              Permanently delete your account and all associated data.
            </p>
          </div>
        </div>

        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 space-y-2">
          <p className="font-medium">Warning: This action is irreversible.</p>
          <p>Deleting your account will permanently remove:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Your profile and login credentials</li>
            <li>All expenses and transaction history</li>
            <li>All bills and reminders</li>
            <li>All categories and accounts</li>
            <li>All savings goals and contributions</li>
            <li>All subscription data</li>
          </ul>
          <p>We recommend exporting your data before proceeding.</p>
        </div>

        {deleteStep === 'idle' && (
          <div className="flex justify-end">
            <Button
              variant="destructive"
              onClick={() => { void handleDeleteRequest(); }}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete My Account
            </Button>
          </div>
        )}

        {deleteStep === 'confirming' && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-red-500" />
            <span className="ml-2 text-sm text-muted-foreground">Preparing deletion...</span>
          </div>
        )}

        {deleteStep === 'typing' && (
          <div className="space-y-3 rounded-lg border border-red-300 p-4">
            <p className="text-sm font-medium">
              Type <span className="font-mono font-bold text-red-600">DELETE</span> to confirm account deletion:
            </p>
            <input
              type="text"
              className="input border-red-300 focus:border-red-500"
              placeholder='Type "DELETE" to confirm'
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={handleCancelDelete}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                disabled={deleteConfirmText !== 'DELETE'}
                onClick={() => { void handleDeleteConfirm(); }}
              >
                Permanently Delete Account
              </Button>
            </div>
          </div>
        )}

        {deleteStep === 'deleting' && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-red-500" />
            <span className="ml-2 text-sm text-muted-foreground">Deleting your account...</span>
          </div>
        )}
      </div>

      {/* Past Requests */}
      <div className="card card-interactive space-y-4 fade-in-up">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted">
            <Shield className="h-5 w-5 text-muted-foreground" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Request History</h2>
            <p className="text-sm text-muted-foreground">
              Past data export and deletion requests.
            </p>
          </div>
        </div>

        {loadingRequests ? (
          <div className="text-sm text-muted-foreground">Loading requests...</div>
        ) : requests.length === 0 ? (
          <div className="text-sm text-muted-foreground py-4 text-center">
            No data requests yet.
          </div>
        ) : (
          <div className="space-y-2">
            {requests.map((req) => (
              <div
                key={req.id}
                className="flex items-center justify-between rounded-lg border p-3"
              >
                <div className="flex items-center gap-3">
                  {statusIcon(req.status)}
                  <div>
                    <p className="text-sm font-medium">
                      {req.request_type === 'EXPORT' ? 'Data Export' : 'Account Deletion'}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {req.created_at
                        ? new Date(req.created_at).toLocaleDateString(undefined, {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : 'Unknown date'}
                      {' '}&middot;{' '}{req.status}
                    </p>
                  </div>
                </div>
                {req.has_download && req.status === 'COMPLETED' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => { void handleDownload(req.id); }}
                    disabled={downloading === req.id}
                  >
                    {downloading === req.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        <Download className="mr-1 h-3 w-3" />
                        Download
                      </>
                    )}
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
