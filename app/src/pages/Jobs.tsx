import { useEffect, useState, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Skull,
  RefreshCw,
  Loader2,
  RotateCcw,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
  listJobs,
  getJobStats,
  retryJob,
  type JobExecution,
  type JobStats,
} from '@/api/jobs';

const STATUS_CONFIG: Record<
  string,
  { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: React.ElementType; color: string }
> = {
  PENDING: { label: 'Pending', variant: 'secondary', icon: Clock, color: 'text-muted-foreground' },
  RUNNING: { label: 'Running', variant: 'default', icon: Loader2, color: 'text-blue-600' },
  SUCCESS: { label: 'Success', variant: 'outline', icon: CheckCircle2, color: 'text-green-600' },
  FAILED: { label: 'Failed', variant: 'destructive', icon: XCircle, color: 'text-red-500' },
  RETRYING: { label: 'Retrying', variant: 'secondary', icon: RefreshCw, color: 'text-amber-500' },
  DEAD: { label: 'Dead', variant: 'destructive', icon: Skull, color: 'text-red-700' },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.PENDING;
  const Icon = cfg.icon;
  return (
    <Badge variant={cfg.variant} className="gap-1">
      <Icon className={`h-3 w-3 ${cfg.color} ${status === 'RUNNING' ? 'animate-spin' : ''}`} />
      {cfg.label}
    </Badge>
  );
}

function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <FinancialCard>
      <FinancialCardContent className="flex items-center gap-4 p-4">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${color}`}>
          <Icon className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-xs text-muted-foreground">{title}</p>
        </div>
      </FinancialCardContent>
    </FinancialCard>
  );
}

function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function Jobs() {
  const [jobs, setJobs] = useState<JobExecution[]>([]);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState<number | null>(null);
  const { toast } = useToast();

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const filter = statusFilter === 'ALL' ? undefined : statusFilter;
      const [jobList, jobStats] = await Promise.all([
        listJobs({ limit: 100, status: filter }),
        getJobStats(),
      ]);
      setJobs(jobList);
      setStats(jobStats);
    } catch (err: unknown) {
      toast({
        title: 'Error loading jobs',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, toast]);

  useEffect(() => {
    void fetchData();
    const interval = setInterval(() => void fetchData(), 15000); // auto-refresh 15s
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRetry = async (id: number) => {
    setRetrying(id);
    try {
      await retryJob(id);
      toast({ title: 'Job queued for retry' });
      void fetchData();
    } catch (err: unknown) {
      toast({
        title: 'Retry failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setRetrying(null);
    }
  };

  return (
    <div className="container-financial py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Job Monitor</h1>
          <p className="text-sm text-muted-foreground">
            Background job executions, retries & health
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void fetchData()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard title="Total" value={stats.total} icon={Activity} color="bg-slate-600" />
          <StatCard title="Success" value={stats.SUCCESS} icon={CheckCircle2} color="bg-green-600" />
          <StatCard title="Running" value={stats.RUNNING} icon={Loader2} color="bg-blue-600" />
          <StatCard title="Retrying" value={stats.RETRYING} icon={RefreshCw} color="bg-amber-500" />
          <StatCard title="Failed" value={stats.FAILED} icon={XCircle} color="bg-red-500" />
          <StatCard title="Dead" value={stats.DEAD} icon={Skull} color="bg-red-800" />
        </div>
      )}

      {/* Filter + table */}
      <FinancialCard>
        <FinancialCardHeader className="flex flex-row items-center justify-between">
          <FinancialCardTitle>Recent Executions</FinancialCardTitle>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Filter status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Statuses</SelectItem>
              {Object.keys(STATUS_CONFIG).map((s) => (
                <SelectItem key={s} value={s}>
                  {STATUS_CONFIG[s].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FinancialCardHeader>
        <FinancialCardContent>
          {loading && jobs.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading jobs…
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Activity className="mb-2 h-8 w-8" />
              <p>No job executions found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Job Name</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-center">Attempt</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Error</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobs.map((job) => (
                    <TableRow key={job.id}>
                      <TableCell className="font-medium max-w-[200px] truncate">
                        {job.job_name}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={job.status} />
                      </TableCell>
                      <TableCell className="text-center">
                        {job.attempt}/{job.max_retries + 1}
                      </TableCell>
                      <TableCell>{formatDuration(job.duration_ms)}</TableCell>
                      <TableCell className="text-xs">{formatTime(job.started_at)}</TableCell>
                      <TableCell className="max-w-[250px] truncate text-xs text-red-600">
                        {job.error_message || '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        {job.status === 'DEAD' && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleRetry(job.id)}
                            disabled={retrying === job.id}
                          >
                            {retrying === job.id ? (
                              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                            ) : (
                              <RotateCcw className="mr-1 h-3 w-3" />
                            )}
                            Retry
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </FinancialCardContent>
      </FinancialCard>
    </div>
  );
}
