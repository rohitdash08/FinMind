'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Download, Trash2, Shield, AlertTriangle, CheckCircle } from 'lucide-react';

interface PrivacySettingsProps {
  userId: string;
}

export default function PrivacySettings({ userId }: PrivacySettingsProps) {
  const [exportProgress, setExportProgress] = useState(0);
  const [isExporting, setIsExporting] = useState(false);
  const [exportComplete, setExportComplete] = useState(false);
  const [deleteProgress, setDeleteProgress] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [confirmationText, setConfirmationText] = useState('');
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  const handleExportData = async () => {
    setIsExporting(true);
    setExportProgress(0);
    setExportComplete(false);

    try {
      const response = await fetch('/api/privacy/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId }),
      });

      if (!response.ok) throw new Error('Export failed');

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response stream');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = new TextDecoder().decode(value);
        const lines = chunk.split('\n').filter(Boolean);

        for (const line of lines) {
          try {
            const data = JSON.parse(line);
            if (data.progress) {
              setExportProgress(data.progress);
            }
            if (data.downloadUrl) {
              setDownloadUrl(data.downloadUrl);
              setExportComplete(true);
            }
          } catch (e) {
            // Ignore malformed JSON
          }
        }
      }
    } catch (error) {
      console.error('Export error:', error);
    } finally {
      setIsExporting(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (confirmationText !== 'DELETE' || !agreedToTerms) return;

    setIsDeleting(true);
    setDeleteProgress(0);

    try {
      const response = await fetch('/api/privacy/delete', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, confirmation: confirmationText }),
      });

      if (!response.ok) throw new Error('Deletion failed');

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response stream');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = new TextDecoder().decode(value);
        const lines = chunk.split('\n').filter(Boolean);

        for (const line of lines) {
          try {
            const data = JSON.parse(line);
            if (data.progress) {
              setDeleteProgress(data.progress);
            }
            if (data.complete) {
              window.location.href = '/account-deleted';
            }
          } catch (e) {
            // Ignore malformed JSON
          }
        }
      }
    } catch (error) {
      console.error('Deletion error:', error);
      setIsDeleting(false);
    }
  };

  const isDeleteConfirmationValid = confirmationText === 'DELETE' && agreedToTerms;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Shield className="h-6 w-6" />
        <h1 className="text-2xl font-bold">Privacy Settings</h1>
      </div>

      {/* Export Data Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Download className="h-5 w-5" />
            Export Your Data
          </CardTitle>
          <CardDescription>
            Download a copy of all your personal data stored in our system. This includes your profile, messages, and activity history.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isExporting && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Preparing your data export...</span>
                <span>{exportProgress}%</span>
              </div>
              <Progress value={exportProgress} className="w-full" />
            </div>
          )}

          {exportComplete && downloadUrl && (
            <Alert>
              <CheckCircle className="h-4 w-4" />
              <AlertDescription>
                Your data export is ready!{' '}
                <a 
                  href={downloadUrl} 
                  download 
                  className="font-medium underline hover:no-underline"
                >
                  Download your data
                </a>
              </AlertDescription>
            </Alert>
          )}

          <Button 
            onClick={handleExportData} 
            disabled={isExporting}
            className="w-full"
          >
            {isExporting ? 'Exporting...' : 'Request Data Export'}
          </Button>
        </CardContent>
      </Card>

      {/* Delete Account Section */}
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <Trash2 className="h-5 w-5" />
            Delete Account
          </CardTitle>
          <CardDescription>
            Permanently delete your account and all associated data. This action cannot be undone.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="destructive" className="w-full">
                Delete My Account
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[500px]">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-destructive" />
                  Delete Account Confirmation
                </DialogTitle>
                <DialogDescription>
                  This will permanently delete your account and all associated data. This action cannot be undone.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4">
                <Alert>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    <strong>Warning:</strong> The following data will be permanently deleted:
                    <ul className="mt-2 list-disc list-inside space-y-1 text-sm">
                      <li>Your profile and account information</li>
                      <li>All messages and conversations</li>
                      <li>Upload history and files</li>
                      <li>Settings and preferences</li>
                      <li>Activity logs and analytics data</li>
                    </ul>
                  </AlertDescription>
                </Alert>

                <div className="space-y-2">
                  <Label htmlFor="confirmation">
                    Type <strong>DELETE</strong> to confirm:
                  </Label>
                  <Input
                    id="confirmation"
                    value={confirmationText}
                    onChange={(e) => setConfirmationText(e.target.value)}
                    placeholder="DELETE"
                    disabled={isDeleting}
                  />
                </div>

                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="terms"
                    checked={agreedToTerms}
                    onCheckedChange={setAgreedToTerms}
                    disabled={isDeleting}
                  />
                  <Label htmlFor="terms" className="text-sm">
                    I understand that this action is permanent and cannot be undone
                  </Label>
                </div>

                {isDeleting && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span>Deleting your account...</span>
                      <span>{deleteProgress}%</span>
                    </div>
                    <Progress value={deleteProgress} className="w-full" />
                  </div>
                )}

                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setDeleteDialogOpen(false)}
                    disabled={isDeleting}
                    className="flex-1"
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleDeleteAccount}
                    disabled={!isDeleteConfirmationValid || isDeleting}
                    className="flex-1"
                  >
                    {isDeleting ? 'Deleting...' : 'Delete Account'}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      <div className="text-xs text-muted-foreground">
        <p>
          These privacy controls are provided in compliance with GDPR, CCPA, and other data protection regulations.
          For questions about data processing, please contact our privacy team.
        </p>
      </div>
    </div>
  );
}