import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { Activity, RefreshCw, AlertTriangle, CheckCircle, Clock, XCircle, RotateCcw } from 'lucide-react';
import {
  getJobStats,
  getRecentJobs,
  getDeadLetterJobs,
  retryJob,
  type Job,
  type JobStats,
} from '@/api/jobs';

const STATUS_CONFIG: Record<string, { icon: typeof Activity; color: string; bg: string }> = {
  PENDING: { icon: Clock, color: 'text-yellow-600', bg: 'bg-yellow-100' },
  RUNNING: { icon: Activity, color: 'text-blue-600', bg: 'bg-blue-100' },
  SUCCESS: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-100' },
  FAILED: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-100' },
  RETRYING: { icon: RefreshCw, color: 'text-orange-600', bg: 'bg-orange-100' },
  DEAD: { icon: AlertTriangle, color: 'text-red-800', bg: 'bg-red-200' },
};

export default function Jobs() {
  const [stats, setStats] = useState<JobStats | null>(null);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [deadJobs, setDeadJobs] = useState<Job[]>([]);
  const [tab, setTab] = useState<'recent' | 'dead'>('recent');
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  const fetchData = async () => {
    try {
      const [s, r, d] = await Promise.all([
        getJobStats(),
        getRecentJobs(),
        getDeadLetterJobs(),
      ]);
      setStats(s);
      setRecentJobs(r);
      setDeadJobs(d);
    } catch {
      toast({ title: 'Error', description: 'Failed to load job data', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleRetry = async (jobId: number) => {
    try {
      await retryJob(jobId);
      toast({ title: 'Success', description: 'Job queued for retry' });
      fetchData();
    } catch {
      toast({ title: 'Error', description: 'Failed to retry job', variant: 'destructive' });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  const displayJobs = tab === 'recent' ? recentJobs : deadJobs;

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Activity className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold">Job Monitor</h1>
        </div>
        <Button variant="outline" onClick={fetchData}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="border rounded-lg p-4 bg-card">
            <p className="text-sm text-muted-foreground">Total Jobs</p>
            <p className="text-2xl font-bold">{stats.total}</p>
          </div>
          <div className="border rounded-lg p-4 bg-card">
            <p className="text-sm text-muted-foreground">Success Rate</p>
            <p className="text-2xl font-bold text-green-600">{stats.success_rate}%</p>
          </div>
          <div className="border rounded-lg p-4 bg-card">
            <p className="text-sm text-muted-foreground">Failed</p>
            <p className="text-2xl font-bold text-red-600">
              {(stats.by_status.FAILED || 0) + (stats.by_status.DEAD || 0)}
            </p>
          </div>
          <div className="border rounded-lg p-4 bg-card">
            <p className="text-sm text-muted-foreground">Running</p>
            <p className="text-2xl font-bold text-blue-600">
              {(stats.by_status.RUNNING || 0) + (stats.by_status.RETRYING || 0)}
            </p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b pb-2">
        <Button
          variant={tab === 'recent' ? 'default' : 'ghost'}
          size="sm"
          onClick={() => setTab('recent')}
        >
          Recent Jobs ({recentJobs.length})
        </Button>
        <Button
          variant={tab === 'dead' ? 'default' : 'ghost'}
          size="sm"
          onClick={() => setTab('dead')}
        >
          <AlertTriangle className="h-4 w-4 mr-1" />
          Dead Letter ({deadJobs.length})
        </Button>
      </div>

      {/* Job List */}
      {displayJobs.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Activity className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p className="text-lg">No {tab === 'dead' ? 'dead letter' : 'recent'} jobs</p>
        </div>
      ) : (
        <div className="space-y-2">
          {displayJobs.map((job) => {
            const config = STATUS_CONFIG[job.status] || STATUS_CONFIG.PENDING;
            const Icon = config.icon;
            return (
              <div key={job.id} className="border rounded-lg p-4 flex items-center justify-between bg-card">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-full ${config.bg}`}>
                    <Icon className={`h-4 w-4 ${config.color}`} />
                  </div>
                  <div>
                    <p className="font-medium">{job.name}</p>
                    <p className="text-xs text-muted-foreground">
                      ID: {job.id} · Attempts: {job.attempts}/{job.max_retries + 1}
                      {job.completed_at && ` · Completed: ${new Date(job.completed_at).toLocaleString()}`}
                    </p>
                    {job.last_error && (
                      <p className="text-xs text-red-500 mt-1">{job.last_error}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-medium px-2 py-1 rounded-full ${config.bg} ${config.color}`}>
                    {job.status}
                  </span>
                  {job.status === 'DEAD' && (
                    <Button size="sm" variant="outline" onClick={() => handleRetry(job.id)}>
                      <RotateCcw className="h-3 w-3 mr-1" />
                      Retry
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
