import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dailog';
import { useToast } from '@/hooks/use-toast';
import {
  listReminders,
  createReminder,
  deleteReminder,
  runDue,
  scheduleBillReminders,
  reportAutopayResult,
  type Reminder,
} from '@/api/reminders';
import { listBills, type Bill } from '@/api/bills';

export function Reminders() {
  const { toast } = useToast();
  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;
  const [items, setItems] = useState<Reminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [sendAt, setSendAt] = useState<string>(() => new Date().toISOString().slice(0, 16));
  const [channel, setChannel] = useState<'email' | 'whatsapp'>('email');
  const [saving, setSaving] = useState(false);
  const [bills, setBills] = useState<Bill[]>([]);
  const [selectedBillId, setSelectedBillId] = useState<string>('');
  const [offsetsInput, setOffsetsInput] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listReminders();
      setItems(data);
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to load reminders');
      setError(message);
      toast({ title: 'Failed to load reminders', description: message || 'Please try again.' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const loadBills = useCallback(async () => {
    try {
      const data = await listBills();
      setBills(data);
      setSelectedBillId((prev) => (prev || (data.length > 0 ? String(data[0].id) : '')));
    } catch {
      toast({ title: 'Failed to load bills', description: 'Please try again.' });
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
    void loadBills();
  }, [refresh, loadBills]);

  async function onCreate() {
    if (!message.trim()) return;
    setSaving(true);
    try {
      await createReminder({ message: message.trim(), send_at: new Date(sendAt).toISOString(), channel });
      await refresh();
      setOpen(false);
      setMessage('');
      setChannel('email');
      setSendAt(new Date().toISOString().slice(0, 16));
      toast({ title: 'Reminder created' });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to create reminder');
      setError(message);
      toast({ title: 'Failed to create reminder', description: message || 'Please try again.' });
    } finally {
      setSaving(false);
    }
  }

  async function onScheduleBillReminders() {
    if (!selectedBillId) {
      toast({ title: 'Select a bill first' });
      return;
    }
    setSaving(true);
    try {
      const offsets = offsetsInput
        .split(',')
        .map((x) => Number(x.trim()))
        .filter((x) => Number.isFinite(x) && x >= 0);
      const result = await scheduleBillReminders(
        Number(selectedBillId),
        offsets.length > 0 ? offsets : undefined,
      );
      toast({ title: 'Bill reminders scheduled', description: `${result.created} created.` });
      await refresh();
    } catch (error: unknown) {
      toast({
        title: 'Failed to schedule bill reminders',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setSaving(false);
    }
  }

  async function onAutopayResult(status: 'SUCCESS' | 'FAILED') {
    if (!selectedBillId) {
      toast({ title: 'Select a bill first' });
      return;
    }
    setSaving(true);
    try {
      const result = await reportAutopayResult(Number(selectedBillId), status);
      toast({
        title: `Autopay ${status.toLowerCase()} recorded`,
        description: `${result.created} follow-up reminders created.`,
      });
      await refresh();
    } catch (error: unknown) {
      toast({
        title: 'Failed to record autopay result',
        description: getErrorMessage(error, 'Please try again.'),
      });
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: number) {
    setSaving(true);
    try {
      await deleteReminder(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
      toast({ title: 'Reminder deleted' });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to delete reminder');
      setError(message);
      toast({ title: 'Failed to delete reminder', description: message || 'Please try again.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative flex items-center justify-between gap-3">
        <div>
          <h2 className="page-title text-2xl md:text-3xl">Reminders</h2>
          <p className="page-subtitle">Create, schedule, and dispatch reminders across channels.</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={async () => {
              try {
                const res = await runDue();
                const processed = typeof res.processed === 'number' ? `${res.processed} processed` : undefined;
                toast({ title: 'Processed due reminders', description: processed });
                void refresh();
              } catch (error: unknown) {
                toast({ title: 'Failed to run due reminders', description: getErrorMessage(error, 'Please try again.') });
              }
            }}
          >
            Run Due
          </Button>
          <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => setOpen(true)}>New Reminder</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New Reminder</DialogTitle>
              <DialogDescription>Create a reminder to notify you later.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label htmlFor="msg">Message</Label>
                <Input id="msg" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Pay credit card" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="sendAt">Send At</Label>
                  <Input id="sendAt" type="datetime-local" value={sendAt} onChange={(e) => setSendAt(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="channel">Channel</Label>
                  <select id="channel" className="input" value={channel} onChange={(e) => setChannel(e.target.value as 'email' | 'whatsapp')}>
                    <option value="email">Email</option>
                    <option value="whatsapp">WhatsApp</option>
                  </select>
                </div>
              </div>
            </div>
            {error && <div className="error">{error}</div>}
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
              <Button onClick={onCreate} disabled={saving || !message.trim()}>Create</Button>
            </DialogFooter>
          </DialogContent>
          </Dialog>
        </div>
        </div>
      </div>

      {loading ? (
        <div className="card fade-in-up">Loading…</div>
      ) : (
        <div className="space-y-4">
          <div className="card card-interactive p-4 space-y-3 fade-in-up">
            <h3 className="text-base font-semibold">Smart Bill Scheduling</h3>
            <div className="grid gap-3 md:grid-cols-4">
              <select
                aria-label="bill picker"
                className="input"
                value={selectedBillId}
                onChange={(e) => setSelectedBillId(e.target.value)}
              >
                <option value="">Select bill</option>
                {bills.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name} {b.autopay_enabled ? '(autopay)' : ''}
                  </option>
                ))}
              </select>
              <Input
                aria-label="reminder offsets"
                placeholder="Offsets days (e.g. 7,3,1)"
                value={offsetsInput}
                onChange={(e) => setOffsetsInput(e.target.value)}
              />
              <Button onClick={onScheduleBillReminders} disabled={saving || !selectedBillId}>
                Schedule Bill Reminders
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => onAutopayResult('SUCCESS')}
                  disabled={saving || !selectedBillId}
                >
                  Autopay Success
                </Button>
                <Button
                  variant="outline"
                  onClick={() => onAutopayResult('FAILED')}
                  disabled={saving || !selectedBillId}
                >
                  Autopay Failed
                </Button>
              </div>
            </div>
          </div>

          <div className="card fade-in-up">
          {items.length === 0 ? (
            <div className="text-sm text-muted-foreground">No reminders.</div>
          ) : (
            <div className="space-y-2">
              {items.map((r) => (
                <div key={r.id} className="interactive-row flex items-center justify-between border-b py-2">
                  <div>
                    <div className="font-medium">{r.message}</div>
                    <div className="text-xs text-muted-foreground">{new Date(r.send_at).toLocaleString()} • {r.channel} • {r.sent ? 'sent' : 'pending'}</div>
                  </div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="outline">Delete</Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete reminder?</AlertDialogTitle>
                        <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => onDelete(r.id)}>Delete</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              ))}
            </div>
          )}
          </div>
        </div>
      )}
    </div>
  );
}

export default Reminders;
