import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { exportData, type ExportFormat, type EncryptedExport } from '@/api/export';

export default function Export() {
  const { toast } = useToast();
  const [password, setPassword] = useState('');
  const [format, setFormat] = useState<ExportFormat>('json');
  const [loading, setLoading] = useState(false);

  const handleExport = async () => {
    if (password.length < 8) {
      toast({ title: 'Password too short', description: 'Password must be at least 8 characters.' });
      return;
    }
    setLoading(true);
    try {
      const result: EncryptedExport = await exportData(password, format);
      // Download as .json file
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `finmind-backup-${new Date().toISOString().slice(0, 10)}.encrypted.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast({ title: 'Export complete', description: 'Your encrypted backup has been downloaded.' });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Export failed';
      toast({ title: 'Export failed', description: message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Secure Backup</h1>
          <p className="page-subtitle">
            Export your financial data as an encrypted file. Your data is
            protected with AES-256-GCM encryption using a password you provide.
          </p>
        </div>
      </div>

      <div className="card card-interactive space-y-5 fade-in-up">
        <div className="space-y-2">
          <Label htmlFor="export-format">Export Format</Label>
          <select
            id="export-format"
            className="input"
            value={format}
            onChange={(e) => setFormat(e.target.value as ExportFormat)}
          >
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
          </select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="export-password">Encryption Password</Label>
          <p className="text-xs text-muted-foreground">
            Minimum 8 characters. You will need this password to decrypt your backup.
          </p>
          <input
            id="export-password"
            type="password"
            className="input"
            placeholder="Enter a strong password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <div className="flex justify-end">
          <Button
            variant="financial"
            onClick={handleExport}
            disabled={loading || password.length < 8}
          >
            {loading ? 'Encrypting...' : 'Download Encrypted Backup'}
          </Button>
        </div>
      </div>
    </div>
  );
}
