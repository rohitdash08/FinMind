import { useEffect, useState } from 'react';
import {
  Shield,
  AlertTriangle,
  CheckCircle,
  Monitor,
  Globe,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { getLoginHistory, getLoginStats, LoginEvent, LoginStats } from '@/api/security';
import { useToast } from '@/components/ui/use-toast';

function riskLabel(score: number): { label: string; color: string } {
  if (score === 0) return { label: 'Safe', color: 'text-green-600' };
  if (score < 0.4) return { label: 'Low', color: 'text-yellow-500' };
  if (score < 0.7) return { label: 'Medium', color: 'text-orange-500' };
  return { label: 'High', color: 'text-red-600' };
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

export function Security() {
  const [stats, setStats] = useState<LoginStats | null>(null);
  const [history, setHistory] = useState<LoginEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    try {
      const [s, h] = await Promise.all([getLoginStats(), getLoginHistory(20)]);
      setStats(s);
      setHistory(h);
    } catch (err: unknown) {
      toast({
        variant: 'destructive',
        title: 'Failed to load security data',
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-6 h-6 animate-spin text-primary" />
        <span className="ml-3 text-muted-foreground">Loading security data…</span>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="w-7 h-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Security Center</h1>
            <p className="text-sm text-muted-foreground">
              Monitor login activity and suspicious behaviour
            </p>
          </div>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm text-primary hover:text-primary-hover transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={<CheckCircle className="w-5 h-5 text-green-500" />}
            label="Total Logins"
            value={stats.total_logins}
          />
          <StatCard
            icon={<Globe className="w-5 h-5 text-blue-500" />}
            label="Unique IPs"
            value={stats.unique_ips}
          />
          <StatCard
            icon={<Monitor className="w-5 h-5 text-purple-500" />}
            label="Unique Devices"
            value={stats.unique_devices}
          />
          <StatCard
            icon={<AlertTriangle className="w-5 h-5 text-orange-500" />}
            label="Suspicious Events"
            value={stats.suspicious_count}
            highlight={stats.suspicious_count > 0}
          />
        </div>
      )}

      {stats?.last_anomaly && (
        <div className="flex items-center gap-2 rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 text-sm text-orange-800">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>
            Last suspicious login detected at{' '}
            <strong>{formatDate(stats.last_anomaly)}</strong>. Review your login
            history below.
          </span>
        </div>
      )}

      {/* Login history */}
      <div>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Clock className="w-5 h-5 text-muted-foreground" />
          Recent Login Activity
        </h2>
        {history.length === 0 ? (
          <p className="text-muted-foreground text-sm">No login events recorded yet.</p>
        ) : (
          <div className="rounded-xl border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Date &amp; Time</th>
                  <th className="px-4 py-3 text-left font-medium">IP Address</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-left font-medium">Risk</th>
                  <th className="px-4 py-3 text-left font-medium">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {history.map((evt) => {
                  const { label, color } = riskLabel(evt.anomaly_score);
                  return (
                    <tr
                      key={evt.id}
                      className={
                        evt.anomaly_score > 0
                          ? 'bg-orange-50/40 hover:bg-orange-50/60'
                          : 'hover:bg-muted/30'
                      }
                    >
                      <td className="px-4 py-3 text-foreground">
                        {formatDate(evt.created_at)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {evt.ip_address || '—'}
                      </td>
                      <td className="px-4 py-3">
                        {evt.success ? (
                          <span className="inline-flex items-center gap-1 text-green-700">
                            <CheckCircle className="w-3.5 h-3.5" />
                            Success
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-red-600">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            Failed
                          </span>
                        )}
                      </td>
                      <td className={`px-4 py-3 font-semibold ${color}`}>{label}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs max-w-xs truncate">
                        {evt.anomaly_reasons || '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  highlight = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-4 space-y-2 ${
        highlight ? 'border-orange-300 bg-orange-50' : 'border-border bg-card'
      }`}
    >
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      <div className="text-2xl font-bold text-foreground">{value}</div>
    </div>
  );
}
