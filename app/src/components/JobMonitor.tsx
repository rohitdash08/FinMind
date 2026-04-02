import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { listJobs, createJob, type Job } from '@/api/jobs';
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';

const JOB_TYPES = ['export_data', 'generate_report', 'sync_transactions'] as const;

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  running: 'default',
  failed: 'destructive',
  complete: 'outline',
};

export function JobMonitor() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    try {
      setLoading(true);
      setJobs(await listJobs());
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    void refresh();
    const id = setInterval(() => void refresh(), 10_000);
    return () => clearInterval(id);
  }, [open]);

  async function handleCreate(type: string) {
    await createJob(type);
    await refresh();
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border p-4">
      <CollapsibleTrigger className="flex w-full items-center justify-between text-sm font-semibold">
        <span className="flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Background Jobs
          {jobs.length > 0 && (
            <Badge variant="secondary" className="ml-1">{jobs.length}</Badge>
          )}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-3 space-y-3">
        <div className="flex flex-wrap gap-2">
          {JOB_TYPES.map((t) => (
            <Button key={t} size="sm" variant="outline" onClick={() => void handleCreate(t)}>
              + {t.replace(/_/g, ' ')}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
        {jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No jobs yet.</p>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => (
              <div key={job.id} className="rounded-md border p-3 text-sm space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{job.job_type.replace(/_/g, ' ')}</span>
                  <Badge variant={STATUS_VARIANT[job.status] ?? 'secondary'}>{job.status}</Badge>
                </div>
                <div className="text-xs text-muted-foreground">
                  Created: {new Date(job.created_at).toLocaleString()}
                </div>
                {job.retry_count > 0 && (
                  <div className="text-xs text-muted-foreground">
                    Retries: {job.retry_count}/3
                    {job.next_retry_at && (
                      <> · Next retry: {new Date(job.next_retry_at).toLocaleString()}</>
                    )}
                  </div>
                )}
                {job.failures.length > 0 && (
                  <div className="text-xs text-red-600">
                    Last error: {job.failures[job.failures.length - 1].error}
                  </div>
                )}
                {job.completed_at && (
                  <div className="text-xs text-green-600">
                    Completed: {new Date(job.completed_at).toLocaleString()}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
