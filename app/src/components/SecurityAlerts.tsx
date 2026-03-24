import { useEffect, useState } from 'react';
import { getAlerts, markAlertsRead, LoginAlert } from '@/api/alerts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Shield, ShieldAlert, ShieldCheck, ShieldQuestion, Check } from 'lucide-react';
import { toast } from 'sonner';

const SEVERITY_COLORS: Record<string, string> = {
  high: 'bg-red-100 text-red-800 border-red-200',
  medium: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  low: 'bg-blue-100 text-blue-800 border-blue-200',
};

const ALERT_ICONS: Record<string, typeof Shield> = {
  brute_force: ShieldAlert,
  credential_stuffing: ShieldAlert,
  new_ip: ShieldQuestion,
  new_device: ShieldQuestion,
};

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function AlertItem({
  alert,
  onMarkRead,
}: {
  alert: LoginAlert;
  onMarkRead: (id: number) => void;
}) {
  const Icon = ALERT_ICONS[alert.alert_type] || Shield;
  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-lg border transition-colors ${
        alert.read ? 'bg-muted/30 opacity-60' : 'bg-card'
      }`}
    >
      <div className="mt-0.5">
        <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="outline" className={SEVERITY_COLORS[alert.severity] || ''}>
            {alert.severity}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {formatRelativeTime(alert.created_at)}
          </span>
          {!alert.read && (
            <span className="h-2 w-2 rounded-full bg-blue-500 flex-shrink-0" />
          )}
        </div>
        <p className="text-sm">{alert.message}</p>
      </div>
      {!alert.read && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onMarkRead(alert.id)}
          className="flex-shrink-0"
        >
          <Check className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

export default function SecurityAlerts() {
  const [alerts, setAlerts] = useState<LoginAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'unread'>('all');

  const fetchAlerts = async () => {
    try {
      const data = await getAlerts(filter === 'unread');
      setAlerts(data.alerts);
    } catch {
      toast.error('Failed to load security alerts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, [filter]);

  const handleMarkRead = async (id: number) => {
    try {
      await markAlertsRead([id]);
      setAlerts((prev) =>
        prev.map((a) => (a.id === id ? { ...a, read: true } : a))
      );
    } catch {
      toast.error('Failed to mark alert as read');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAlertsRead();
      setAlerts((prev) => prev.map((a) => ({ ...a, read: true })));
      toast.success('All alerts marked as read');
    } catch {
      toast.error('Failed to mark alerts as read');
    }
  };

  const unreadCount = alerts.filter((a) => !a.read).length;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" />
          <CardTitle className="text-lg">Security Alerts</CardTitle>
          {unreadCount > 0 && (
            <Badge variant="secondary">{unreadCount} unread</Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={filter === 'all' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('all')}
          >
            All
          </Button>
          <Button
            variant={filter === 'unread' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilter('unread')}
          >
            Unread
          </Button>
          {unreadCount > 0 && (
            <Button variant="ghost" size="sm" onClick={handleMarkAllRead}>
              Mark all read
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading...</div>
        ) : alerts.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <ShieldCheck className="h-12 w-12 mx-auto mb-2 opacity-50" />
            <p>No security alerts</p>
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map((alert) => (
              <AlertItem key={alert.id} alert={alert} onMarkRead={handleMarkRead} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
