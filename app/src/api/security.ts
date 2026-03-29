import { useEffect, useState } from 'react';
import {
  Shield,
  AlertTriangle,
  CheckCircle,
  Monitor,
  Globe,
  Clock,
  RefreshCw,
  Trash2,
  Check,
  X,
} from 'lucide-react';
import { api } from './client';
import { useToast } from '@/components/ui/use-toast';

interface LoginEvent {
  id: number;
  ip_address: string | null;
  user_agent: string | null;
  success: boolean;
  anomaly_score: number;
  anomaly_reasons: string | null;
  created_at: string;
}

interface LoginStats {
  total_logins: number;
  unique_ips: number;
  unique_devices: number;
  suspicious_count: number;
  last_anomaly: string | null;
}

interface UserDevice {
  id: number;
  device_name: string | null;
  device_fingerprint: string;
  ip_address: string;
  user_agent: string | null;
  country: string | null;
  city: string | null;
  first_seen: string;
  last_seen: string;
  is_trusted: boolean;
  is_revoked: boolean;
}

interface SecurityAlert {
  id: number;
  anomaly_type: string;
  severity: string;
  details: string | null;
  acknowledged: boolean;
  created_at: string;
}

export async function getLoginHistory(limit = 50): Promise<LoginEvent[]> {
  return api<LoginEvent[]>(`/security/login-history?limit=${limit}`);
}

export async function getAnomalies(limit = 50): Promise<SecurityAlert[]> {
  return api<SecurityAlert[]>(`/security/alerts?limit=${limit}`);
}

export async function getLoginStats(): Promise<LoginStats> {
  return api<LoginStats>('/security/login-stats');
}

export async function getDevices(): Promise<UserDevice[]> {
  return api<UserDevice[]>('/security/devices');
}

export async function acknowledgeAlert(alertId: number): Promise<void> {
  return api(`/security/alerts/${alertId}/acknowledge`, { method: 'POST' });
}

export async function acknowledgeAllAlerts(): Promise<{ count: number }> {
  return api<{ count: number }>('/security/alerts/acknowledge-all', { method: 'POST' });
}

export async function trustDevice(deviceId: number): Promise<void> {
  return api(`/security/devices/${deviceId}`, {
    method: 'PATCH',
    body: JSON.stringify({ is_trusted: true }),
  });
}

export async function revokeDevice(deviceId: number): Promise<void> {
  return api(`/security/devices/${deviceId}`, { method: 'DELETE' });
}

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

function severityColor(severity: string): string {
  switch (severity) {
    case 'high': return 'text-red-600 bg-red-50';
    case 'medium': return 'text-orange-600 bg-orange-50';
    case 'low': return 'text-yellow-600 bg-yellow-50';
    default: return 'text-gray-600 bg-gray-50';
  }
}

function anomalyTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    new_device: 'New Device',
    new_location: 'New Location',
    unusual_time: 'Unusual Time',
    multiple_failures: 'Multiple Failures',
    suspicious_ip: 'Suspicious IP',
    impossible_travel: 'Impossible Travel',
  };
  return labels[type] || type;
}

export function Security() {
  const [stats, setStats] = useState<LoginStats | null>(null);
  const [history, setHistory] = useState<LoginEvent[]>([]);
  const [devices, setDevices] = useState<UserDevice[]>([]);
  const [alerts, setAlerts] = useState<SecurityAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'history' | 'devices' | 'alerts'>('history');
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    try {
      const [s, h, d, a] = await Promise.all([
        getLoginStats(),
        getLoginHistory(20),
        getDevices(),
        getAnomalies(20),
      ]);
      setStats(s);
      setHistory(h);
      setDevices(d);
      setAlerts(a);
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

  const handleAcknowledgeAlert = async (alertId: number) => {
    try {
      await acknowledgeAlert(alertId);
      setAlerts(alerts.map(a => a.id === alertId ? { ...a, acknowledged: true } : a));
      toast({ title: 'Alert acknowledged' });
    } catch (err: unknown) {
      toast({
        variant: 'destructive',
        title: 'Failed to acknowledge alert',
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  };

  const handleAcknowledgeAll = async () => {
    try {
      const result = await acknowledgeAllAlerts();
      setAlerts(alerts.map(a => ({ ...a, acknowledged: true })));
      toast({ title: `${result.count} alerts acknowledged` });
    } catch (err: unknown) {
      toast({
        variant: 'destructive',
        title: 'Failed to acknowledge alerts',
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  };

  const handleTrustDevice = async (deviceId: number) => {
    try {
      await trustDevice(deviceId);
      setDevices(devices.map(d => d.id === deviceId ? { ...d, is_trusted: true } : d));
      toast({ title: 'Device trusted' });
    } catch (err: unknown) {
      toast({
        variant: 'destructive',
        title: 'Failed to trust device',
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  };

  const handleRevokeDevice = async (deviceId: number) => {
    try {
      await revokeDevice(deviceId);
      setDevices(devices.map(d => d.id === deviceId ? { ...d, is_revoked: true } : d));
      toast({ title: 'Device revoked' });
    } catch (err: unknown) {
      toast({
        variant: 'destructive',
        title: 'Failed to revoke device',
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  };

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
              Monitor login activity and manage security alerts
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
            label="Devices"
            value={stats.unique_devices}
          />
          <StatCard
            icon={<AlertTriangle className="w-5 h-5 text-orange-500" />}
            label="Alerts"
            value={stats.suspicious_count}
            highlight={stats.suspicious_count > 0}
          />
        </div>
      )}

      {stats?.last_anomaly && (
        <div className="flex items-center gap-2 rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 text-sm text-orange-800">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>
            Last suspicious login at <strong>{formatDate(stats.last_anomaly)}</strong>.
            Review your alerts below.
          </span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-border pb-2">
        <button
          onClick={() => setActiveTab('history')}
          className={`px-4 py-2 text-sm font-medium rounded-t ${
            activeTab === 'history'
              ? 'bg-card border border-b-transparent border-border text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <Clock className="w-4 h-4 inline mr-2" />
          Login History
        </button>
        <button
          onClick={() => setActiveTab('devices')}
          className={`px-4 py-2 text-sm font-medium rounded-t ${
            activeTab === 'devices'
              ? 'bg-card border border-b-transparent border-border text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <Monitor className="w-4 h-4 inline mr-2" />
          Devices
        </button>
        <button
          onClick={() => setActiveTab('alerts')}
          className={`px-4 py-2 text-sm font-medium rounded-t ${
            activeTab === 'alerts'
              ? 'bg-card border border-b-transparent border-border text-foreground'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <AlertTriangle className="w-4 h-4 inline mr-2" />
          Alerts {alerts.filter(a => !a.acknowledged).length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 text-xs bg-red-500 text-white rounded-full">
              {alerts.filter(a => !a.acknowledged).length}
            </span>
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'history' && (
        <LoginHistoryTable history={history} />
      )}

      {activeTab === 'devices' && (
        <DevicesTable
          devices={devices}
          onTrust={handleTrustDevice}
          onRevoke={handleRevokeDevice}
        />
      )}

      {activeTab === 'alerts' && (
        <AlertsTable
          alerts={alerts}
          onAcknowledge={handleAcknowledgeAlert}
          onAcknowledgeAll={handleAcknowledgeAll}
        />
      )}
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

function LoginHistoryTable({ history }: { history: LoginEvent[] }) {
  if (history.length === 0) {
    return <p className="text-muted-foreground text-sm">No login events recorded yet.</p>;
  }

  return (
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
                <td className="px-4 py-3 text-foreground">{formatDate(evt.created_at)}</td>
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
                      <X className="w-3.5 h-3.5" />
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
  );
}

function DevicesTable({
  devices,
  onTrust,
  onRevoke,
}: {
  devices: UserDevice[];
  onTrust: (id: number) => void;
  onRevoke: (id: number) => void;
}) {
  const activeDevices = devices.filter(d => !d.is_revoked);

  if (activeDevices.length === 0) {
    return <p className="text-muted-foreground text-sm">No devices registered.</p>;
  }

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-muted-foreground">
          <tr>
            <th className="px-4 py-3 text-left font-medium">Device</th>
            <th className="px-4 py-3 text-left font-medium">Location</th>
            <th className="px-4 py-3 text-left font-medium">Last Seen</th>
            <th className="px-4 py-3 text-left font-medium">Status</th>
            <th className="px-4 py-3 text-left font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {activeDevices.map((device) => (
            <tr key={device.id} className="hover:bg-muted/30">
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <Monitor className="w-4 h-4 text-muted-foreground" />
                  <div>
                    <div className="font-medium">
                      {device.device_name || 'Unknown Device'}
                    </div>
                    <div className="text-xs text-muted-foreground font-mono">
                      {device.device_fingerprint?.substring(0, 12)}...
                    </div>
                  </div>
                </div>
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {device.city && device.country
                  ? `${device.city}, ${device.country}`
                  : device.country || '—'}
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {formatDate(device.last_seen)}
              </td>
              <td className="px-4 py-3">
                {device.is_trusted ? (
                  <span className="inline-flex items-center gap-1 text-green-700">
                    <Check className="w-3.5 h-3.5" />
                    Trusted
                  </span>
                ) : (
                  <span className="text-muted-foreground">Untrusted</span>
                )}
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  {!device.is_trusted && (
                    <button
                      onClick={() => onTrust(device.id)}
                      className="p-1 text-green-600 hover:bg-green-50 rounded"
                      title="Trust device"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => onRevoke(device.id)}
                    className="p-1 text-red-600 hover:bg-red-50 rounded"
                    title="Revoke device"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AlertsTable({
  alerts,
  onAcknowledge,
  onAcknowledgeAll,
}: {
  alerts: SecurityAlert[];
  onAcknowledge: (id: number) => void;
  onAcknowledgeAll: () => void;
}) {
  const unacknowledged = alerts.filter(a => !a.acknowledged);

  if (alerts.length === 0) {
    return <p className="text-muted-foreground text-sm">No security alerts.</p>;
  }

  return (
    <div className="space-y-4">
      {unacknowledged.length > 0 && (
        <button
          onClick={onAcknowledgeAll}
          className="text-sm text-primary hover:text-primary-hover"
        >
          Acknowledge all ({unacknowledged.length})
        </button>
      )}

      <div className="rounded-xl border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Alert</th>
              <th className="px-4 py-3 text-left font-medium">Severity</th>
              <th className="px-4 py-3 text-left font-medium">Time</th>
              <th className="px-4 py-3 text-left font-medium">Status</th>
              <th className="px-4 py-3 text-left font-medium">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {alerts.map((alert) => (
              <tr
                key={alert.id}
                className={alert.acknowledged ? 'opacity-50' : 'hover:bg-muted/30'}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-orange-500" />
                    <span className="font-medium">{anomalyTypeLabel(alert.anomaly_type)}</span>
                  </div>
                  {alert.details && (
                    <div className="text-xs text-muted-foreground mt-1">
                      {alert.details}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${severityColor(alert.severity)}`}>
                    {alert.severity}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {formatDate(alert.created_at)}
                </td>
                <td className="px-4 py-3">
                  {alert.acknowledged ? (
                    <span className="text-green-600">Acknowledged</span>
                  ) : (
                    <span className="text-orange-600">Pending</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {!alert.acknowledged && (
                    <button
                      onClick={() => onAcknowledge(alert.id)}
                      className="text-primary hover:text-primary-hover text-sm"
                    >
                      Acknowledge
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
