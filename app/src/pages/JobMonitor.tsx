import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/hooks/use-toast';
import { listJobRuns, type JobRun } from '@/api/reminders';
import { api } from '@/api/client';

function statusBadgeVariant(status: JobRun['status']): string {
  switch (status) {
    case 'success': return 'bg-green-100 text-green-800 border-green-200';
    case 'partial': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'failed': return 'bg-red-100 text-red-800 border-red-200';
    case 'no_work': return 'bg-gray-100 text-gray-600 border-gray-200';
  }
}

function formatDuration(started: string, finished: string | null): string {
  if (!finished) return '—';
  const ms = new Date(finished).getTime() - new Date(started).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function JobMonitor() {
  const { toast } = useToast();
  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;

  const [items, setItems] = useState<JobRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await listJobRuns();
      setItems(data);
    } catch (error: unknown) {
      toast({ title: 'Failed to load job runs', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => { void refresh(); }, 30_000);
    return () => clearInterval(id);
  }, [refresh]);

  async function onRunDueNow() {
    setRunning(true);
    try {
      const res = await api<{ processed?: number; failed?: number; retried?: number; status?: string }>('/reminders/run', { method: 'POST' });
      toast({
        title: 'Job triggered',
        description: `processed: ${res.processed ?? 0}, failed: ${res.failed ?? 0}, retried: ${res.retried ?? 0}`,
      });
      void refresh();
    } catch (error: unknown) {
      toast({ title: 'Failed to run job', description: getErrorMessage(error, 'Please try again.') });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex items-center justify-between gap-3">
          <div>
            <h2 className="page-title text-2xl md:text-3xl">Job Monitor</h2>
            <p className="page-subtitle">Background job execution history</p>
          </div>
          <Button variant="outline" onClick={() => { void onRunDueNow(); }} disabled={running}>
            {running ? 'Running…' : 'Run Due Now'}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="card fade-in-up">Loading…</div>
      ) : items.length === 0 ? (
        <div className="card fade-in-up">
          <div className="text-sm text-muted-foreground">No job runs yet</div>
        </div>
      ) : (
        <div className="card fade-in-up overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs font-semibold text-muted-foreground">
                <th className="pb-2 pr-4">Time</th>
                <th className="pb-2 pr-4">Job</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2 pr-4 text-right">Processed</th>
                <th className="pb-2 pr-4 text-right">Failed</th>
                <th className="pb-2 pr-4 text-right">Retried</th>
                <th className="pb-2 text-right">Duration</th>
              </tr>
            </thead>
            <tbody>
              {items.map((run) => (
                <tr key={run.id} className="border-b last:border-0">
                  <td className="py-2 pr-4 text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(run.started_at).toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 font-medium">{run.job_name}</td>
                  <td className="py-2 pr-4">
                    <Badge className={`border text-xs font-medium ${statusBadgeVariant(run.status)}`}>
                      {run.status}
                    </Badge>
                  </td>
                  <td className="py-2 pr-4 text-right">{run.processed}</td>
                  <td className="py-2 pr-4 text-right">{run.failed}</td>
                  <td className="py-2 pr-4 text-right">{run.retried}</td>
                  <td className="py-2 text-right text-xs text-muted-foreground">
                    {formatDuration(run.started_at, run.finished_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
