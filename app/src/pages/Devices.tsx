import { useEffect, useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { listDevices, trustDevice, removeDevice, type Device } from '@/api/devices';

export default function Devices() {
  const { toast } = useToast();
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);

  const loadDevices = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listDevices();
      setDevices(data);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to load devices';
      toast({ title: 'Error', description: message });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadDevices();
  }, [loadDevices]);

  const handleTrust = async (deviceId: number) => {
    try {
      await trustDevice(deviceId);
      toast({ title: 'Device trusted', description: 'Device has been marked as trusted.' });
      await loadDevices();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to trust device';
      toast({ title: 'Error', description: message });
    }
  };

  const handleRemove = async (deviceId: number) => {
    try {
      await removeDevice(deviceId);
      toast({ title: 'Device removed', description: 'Device has been removed.' });
      await loadDevices();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to remove device';
      toast({ title: 'Error', description: message });
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Trusted Devices</h1>
          <p className="page-subtitle">
            Manage devices that have accessed your account. Trust devices you
            recognize and remove any you do not.
          </p>
        </div>
      </div>

      <div className="card card-interactive space-y-4 fade-in-up">
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading devices...</div>
        ) : devices.length === 0 ? (
          <div className="text-sm text-muted-foreground">No devices recorded yet.</div>
        ) : (
          <div className="space-y-3">
            {devices.map((device) => (
              <div
                key={device.id}
                className="flex items-center justify-between rounded-lg border p-4"
              >
                <div className="space-y-1">
                  <div className="font-medium text-sm">{device.device_name}</div>
                  <div className="text-xs text-muted-foreground">
                    IP: {device.ip_address || 'Unknown'} &middot; Last seen:{' '}
                    {device.last_seen
                      ? new Date(device.last_seen).toLocaleString()
                      : 'N/A'}
                  </div>
                  <div className="text-xs">
                    {device.trusted ? (
                      <span className="text-green-600 font-medium">Trusted</span>
                    ) : (
                      <span className="text-yellow-600 font-medium">Untrusted</span>
                    )}
                  </div>
                </div>
                <div className="flex gap-2">
                  {!device.trusted && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleTrust(device.id)}
                    >
                      Trust
                    </Button>
                  )}
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleRemove(device.id)}
                  >
                    Remove
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
