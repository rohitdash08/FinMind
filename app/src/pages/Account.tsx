import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import {
  acknowledgeSecurityAlert,
  getSecurityAlerts,
  me,
  type SecurityAlert,
  updateMe,
} from '@/api/auth';
import { setCurrency } from '@/lib/auth';
import { AlertTriangle, CheckCircle2, ShieldCheck } from 'lucide-react';

const SUPPORTED_CURRENCIES = [
  { code: 'INR', label: 'Indian Rupee (INR)' },
  { code: 'USD', label: 'US Dollar (USD)' },
  { code: 'EUR', label: 'Euro (EUR)' },
  { code: 'GBP', label: 'British Pound (GBP)' },
  { code: 'AED', label: 'UAE Dirham (AED)' },
  { code: 'SGD', label: 'Singapore Dollar (SGD)' },
  { code: 'AUD', label: 'Australian Dollar (AUD)' },
  { code: 'CAD', label: 'Canadian Dollar (CAD)' },
  { code: 'JPY', label: 'Japanese Yen (JPY)' },
];

export default function Account() {
  const { toast } = useToast();
  const [email, setEmail] = useState('');
  const [currency, setCurrencyState] = useState('INR');
  const [securityAlerts, setSecurityAlerts] = useState<SecurityAlert[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [securityLoading, setSecurityLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [acknowledgingId, setAcknowledgingId] = useState<number | null>(null);

  useEffect(() => {
    const loadAccount = async () => {
      setLoading(true);
      try {
        const data = await me();
        setEmail(data.email);
        setCurrencyState(data.preferred_currency || 'INR');
      } catch (error: unknown) {
        const message =
          error instanceof Error ? error.message : 'Failed to load account';
        toast({ title: 'Failed to load account', description: message });
      } finally {
        setLoading(false);
      }
    };

    const loadSecurityAlerts = async () => {
      setSecurityLoading(true);
      try {
        const data = await getSecurityAlerts();
        setSecurityAlerts(data.alerts);
        setUnreadCount(data.unread_count);
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : 'Failed to load security alerts';
        toast({ title: 'Failed to load security alerts', description: message });
      } finally {
        setSecurityLoading(false);
      }
    };

    void loadAccount();
    void loadSecurityAlerts();
  }, [toast]);

  const onSave = async () => {
    setSaving(true);
    try {
      const updated = await updateMe({ preferred_currency: currency });
      setCurrency(updated.preferred_currency);
      toast({
        title: 'Account updated',
        description: `Default currency set to ${updated.preferred_currency}.`,
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to update account';
      toast({ title: 'Failed to update account', description: message });
    } finally {
      setSaving(false);
    }
  };

  const onAcknowledge = async (alert: SecurityAlert) => {
    setAcknowledgingId(alert.id);
    try {
      const updated = await acknowledgeSecurityAlert(alert.id);
      setSecurityAlerts((current) =>
        current.map((item) =>
          item.id === updated.id
            ? { ...item, acknowledged: updated.acknowledged }
            : item,
        ),
      );
      if (!alert.acknowledged && updated.acknowledged) {
        setUnreadCount((count) => Math.max(0, count - 1));
      }
      toast({
        title: 'Security alert reviewed',
        description: alert.message,
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error
          ? error.message
          : 'Failed to update security alert';
      toast({ title: 'Failed to update security alert', description: message });
    } finally {
      setAcknowledgingId(null);
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Account Settings</h1>
          <p className="page-subtitle">
            Manage your profile defaults. Currency stays fixed until you change
            it again.
          </p>
        </div>
      </div>

      <div className="card card-interactive space-y-5 fade-in-up">
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading account...</div>
        ) : (
          <>
            <div className="space-y-2">
              <Label>Email</Label>
              <div className="input bg-muted/30">{email}</div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="preferred_currency">Preferred Currency</Label>
              <select
                id="preferred_currency"
                className="input"
                value={currency}
                onChange={(e) => setCurrencyState(e.target.value)}
              >
                {SUPPORTED_CURRENCIES.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end">
              <Button
                variant="financial"
                onClick={onSave}
                disabled={saving || loading}
              >
                {saving ? 'Saving...' : 'Save Preferences'}
              </Button>
            </div>
          </>
        )}
      </div>

      <div className="card card-interactive space-y-5 fade-in-up">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                Security Alerts
              </h2>
              <p className="text-sm text-muted-foreground">
                {unreadCount} unread login {unreadCount === 1 ? 'alert' : 'alerts'}
              </p>
            </div>
          </div>
        </div>

        {securityLoading ? (
          <div className="text-sm text-muted-foreground">
            Loading security alerts...
          </div>
        ) : securityAlerts.length === 0 ? (
          <div className="rounded-lg border border-border bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
            No suspicious login activity.
          </div>
        ) : (
          <div className="space-y-3">
            {securityAlerts.map((alert) => (
              <div
                key={alert.id}
                className="rounded-lg border border-border bg-background px-4 py-3"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex min-w-0 items-start gap-3">
                    {alert.acknowledged ? (
                      <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                    )}
                    <div className="min-w-0">
                      <div className="font-medium text-foreground">
                        {alert.message}
                      </div>
                      <div className="mt-1 break-words text-sm text-muted-foreground">
                        {securityAlertMeta(alert)}
                      </div>
                      <div className="mt-1 text-xs uppercase tracking-wide text-muted-foreground">
                        {alert.severity} severity
                      </div>
                    </div>
                  </div>
                  {!alert.acknowledged && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void onAcknowledge(alert)}
                      disabled={acknowledgingId === alert.id}
                    >
                      {acknowledgingId === alert.id
                        ? 'Reviewing...'
                        : 'Mark reviewed'}
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function securityAlertMeta(alert: SecurityAlert): string {
  const ip = alert.details?.ip_address
    ? `IP ${String(alert.details.ip_address)}`
    : null;
  const device = alert.details?.user_agent
    ? `Device ${String(alert.details.user_agent)}`
    : null;
  const timestamp = formatTimestamp(alert.created_at);
  return [ip, device, timestamp].filter(Boolean).join(' / ');
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
