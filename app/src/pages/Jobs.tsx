import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';
import {
  listJobs,
  createJob,
  retryJob,
  getJobStats,
  getDeadLetterQueue,
  type Job,
  type JobStatus,
  type JobType,
  type JobStats,
  type JobCreate,
} from '@/api/jobs';

const STATUS_STYLES: Record<JobStatus, { label: string; className: string }> = {
  PENDING: {
    label: 'Pending',
    className: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  },
  RUNNING: {
    label: 'Running',
    className: 'bg-blue-100 text-blue-800 border-blue-200',
  },
  COMPLETED: {
    label: 'Completed',
    className: 'bg-green-100 text-green-800 border-green-200',
  },
  FAILED: {
    label: 'Failed',
    className: 'bg-red-100 text-red-800 border-red-200',
  },
  DEAD: {
    label: 'Dead Letter',
    className: 'bg-gray-800 text-gray-100 border-gray-700',
  },
};

const JOB_TYPE_LABELS: Record<JobType, string> = {
  DATA_SYNC: 'Data Sync',
  REPORT_GENERATION: 'Report Generation',
  EMAIL_NOTIFICATION: 'Email Notification',
};

function StatusBadge({ status }: { status: JobStatus }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.PENDING;
  return (
    <Badge variant="outline" className={style.className}>
      {style.label}
    </Badge>
  );
}

function StatsCard({ label, count, active }: { label: string; count: number; active?: boolean }) {
  return (
    <button
      className={`card card-interactive flex flex-col items-center justify-center p-4 text-center transition ${
        active ? 'ring-2 ring-primary' : ''
      }`}
    >
      <div className="text-2xl font-bold">{count}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </button>
  );
}

function TimelineEntry({ job }: { job: Job }) {
  const parsePayload = (raw: string | null) => {
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  };

  const payload = parsePayload(job.payload);
  const result = parsePayload(job.result);

  return (
    <div className="relative pl-6 pb-6 border-l-2 border-border last:border-l-0 last:pb-0">
      <div className="absolute -left-[9px] top-0 h-4 w-4 rounded-full border-2 border-background bg-border" />
      <div className="space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{job.name}</span>
          <StatusBadge status={job.status} />
          <span className="text-xs text-muted-foreground">
            {JOB_TYPE_LABELS[job.job_type] ?? job.job_type}
          </span>
        </div>
        <div className="text-xs text-muted-foreground space-x-3">
          <span>Attempt {job.attempts}/{job.max_retries}</span>
          {job.created_at && <span>Created {new Date(job.created_at).toLocaleString()}</span>}
          {job.completed_at && <span>Completed {new Date(job.completed_at).toLocaleString()}</span>}
          {job.next_retry_at && job.status === 'FAILED' && (
            <span>Retry at {new Date(job.next_retry_at).toLocaleString()}</span>
          )}
        </div>
        {job.last_error && (
          <div className="text-xs text-destructive bg-destructive/10 rounded px-2 py-1 mt-1">
            {job.last_error}
          </div>
        )}
        {payload && (
          <details className="text-xs mt-1">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              Payload
            </summary>
            <pre className="bg-muted rounded p-2 mt-1 overflow-x-auto text-[11px]">
              {JSON.stringify(payload, null, 2)}
            </pre>
          </details>
        )}
        {result && (
          <details className="text-xs mt-1">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              Result
            </summary>
            <pre className="bg-muted rounded p-2 mt-1 overflow-x-auto text-[11px]">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

export function Jobs() {
  const { toast } = useToast();
  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [typeFilter, setTypeFilter] = useState<JobType | ''>('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const perPage = 20;

  // New job dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState<JobType>('DATA_SYNC');
  const [newMaxRetries, setNewMaxRetries] = useState('5');
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [jobsRes, statsRes] = await Promise.all([
        listJobs({
          status: statusFilter || undefined,
          job_type: typeFilter || undefined,
          page,
          per_page: perPage,
        }),
        getJobStats(),
      ]);
      setJobs(jobsRes.jobs);
      setTotal(jobsRes.total);
      setStats(statsRes);
    } catch (error: unknown) {
      toast({
        title: 'Failed to load jobs',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter, page, toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleCreate() {
    if (!newName.trim()) return;
    setSaving(true);
    try {
      const payload: JobCreate = {
        name: newName.trim(),
        job_type: newType,
        max_retries: Math.max(0, parseInt(newMaxRetries, 10) || 5),
      };
      await createJob(payload);
      toast({ title: 'Job created' });
      setDialogOpen(false);
      setNewName('');
      setNewMaxRetries('5');
      void refresh();
    } catch (error: unknown) {
      toast({
        title: 'Failed to create job',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleRetry(jobId: number) {
    try {
      const updated = await retryJob(jobId);
      toast({
        title: 'Job retried',
        description: `Status: ${updated.status}`,
      });
      void refresh();
    } catch (error: unknown) {
      toast({
        title: 'Failed to retry job',
        description: getErrorMessage(error, 'Please try again.'),
      });
    }
  }

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex items-center justify-between gap-3">
          <div>
            <h2 className="page-title text-2xl md:text-3xl">Background Jobs</h2>
            <p className="page-subtitle">
              Monitor, retry, and manage background tasks with resilient retry logic.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void refresh()}>
              Refresh
            </Button>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button>New Job</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create Background Job</DialogTitle>
                  <DialogDescription>
                    Enqueue a new job for background processing with automatic retry.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="jobName">Job Name</Label>
                    <Input
                      id="jobName"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="Sync bank transactions"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="jobType">Type</Label>
                      <select
                        id="jobType"
                        className="input"
                        value={newType}
                        onChange={(e) => setNewType(e.target.value as JobType)}
                      >
                        <option value="DATA_SYNC">Data Sync</option>
                        <option value="REPORT_GENERATION">Report Generation</option>
                        <option value="EMAIL_NOTIFICATION">Email Notification</option>
                      </select>
                    </div>
                    <div>
                      <Label htmlFor="maxRetries">Max Retries</Label>
                      <Input
                        id="maxRetries"
                        type="number"
                        min="0"
                        max="20"
                        value={newMaxRetries}
                        onChange={(e) => setNewMaxRetries(e.target.value)}
                      />
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
                    Cancel
                  </Button>
                  <Button onClick={handleCreate} disabled={saving || !newName.trim()}>
                    Create
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-6 fade-in-up">
          <div onClick={() => { setStatusFilter(''); setPage(1); }}>
            <StatsCard label="Total" count={stats.total} active={statusFilter === ''} />
          </div>
          <div onClick={() => { setStatusFilter('PENDING'); setPage(1); }}>
            <StatsCard label="Pending" count={stats.pending} active={statusFilter === 'PENDING'} />
          </div>
          <div onClick={() => { setStatusFilter('RUNNING'); setPage(1); }}>
            <StatsCard label="Running" count={stats.running} active={statusFilter === 'RUNNING'} />
          </div>
          <div onClick={() => { setStatusFilter('COMPLETED'); setPage(1); }}>
            <StatsCard
              label="Completed"
              count={stats.completed}
              active={statusFilter === 'COMPLETED'}
            />
          </div>
          <div onClick={() => { setStatusFilter('FAILED'); setPage(1); }}>
            <StatsCard label="Failed" count={stats.failed} active={statusFilter === 'FAILED'} />
          </div>
          <div onClick={() => { setStatusFilter('DEAD'); setPage(1); }}>
            <StatsCard label="Dead Letter" count={stats.dead} active={statusFilter === 'DEAD'} />
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="card p-4 fade-in-up">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label className="text-xs">Job Type</Label>
            <select
              className="input"
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value as JobType | '');
                setPage(1);
              }}
            >
              <option value="">All types</option>
              <option value="DATA_SYNC">Data Sync</option>
              <option value="REPORT_GENERATION">Report Generation</option>
              <option value="EMAIL_NOTIFICATION">Email Notification</option>
            </select>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setStatusFilter('');
              setTypeFilter('');
              setPage(1);
            }}
          >
            Clear Filters
          </Button>
        </div>
      </div>

      {/* Job list as timeline */}
      {loading ? (
        <div className="card fade-in-up p-6">Loading...</div>
      ) : jobs.length === 0 ? (
        <div className="card fade-in-up p-6 text-sm text-muted-foreground">
          No jobs found. Create one to get started.
        </div>
      ) : (
        <div className="card fade-in-up p-6">
          <h3 className="text-base font-semibold mb-4">Job History</h3>
          <div className="space-y-0">
            {jobs.map((job) => (
              <div key={job.id} className="group relative">
                <TimelineEntry job={job} />
                {(job.status === 'FAILED' || job.status === 'DEAD') && (
                  <div className="absolute top-0 right-0">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRetry(job.id)}
                    >
                      Retry
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-6 pt-4 border-t">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <span className="text-xs text-muted-foreground">
                Page {page} of {totalPages} ({total} total)
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default Jobs;
