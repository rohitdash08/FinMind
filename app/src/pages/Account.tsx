import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { me, updateMe } from '@/api/auth';
import { setCurrency, setLocale } from '@/lib/auth';

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

const SUPPORTED_LOCALES = [
  { code: 'en-US', label: 'English (US)' },
  { code: 'en-GB', label: 'English (UK)' },
  { code: 'en-IN', label: 'English (India)' },
  { code: 'en-AU', label: 'English (Australia)' },
  { code: 'en-CA', label: 'English (Canada)' },
  { code: 'fr-FR', label: 'French (France)' },
  { code: 'de-DE', label: 'German (Germany)' },
  { code: 'ja-JP', label: 'Japanese (Japan)' },
  { code: 'hi-IN', label: 'Hindi (India)' },
  { code: 'ar-AE', label: 'Arabic (UAE)' },
  { code: 'zh-CN', label: 'Chinese (China)' },
  { code: 'es-ES', label: 'Spanish (Spain)' },
  { code: 'pt-BR', label: 'Portuguese (Brazil)' },
];

export default function Account() {
  const { toast } = useToast();
  const [email, setEmail] = useState('');
  const [currency, setCurrencyState] = useState('INR');
  const [locale, setLocaleState] = useState('en-US');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await me();
        setEmail(data.email);
        setCurrencyState(data.preferred_currency || 'INR');
        setLocaleState(data.locale || 'en-US');
      } catch (error: unknown) {
        const message =
          error instanceof Error ? error.message : 'Failed to load account';
        toast({ title: 'Failed to load account', description: message });
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [toast]);

  const onSave = async () => {
    setSaving(true);
    try {
      const updated = await updateMe({ preferred_currency: currency, locale });
      setCurrency(updated.preferred_currency);
      setLocale(updated.locale);
      toast({
        title: 'Account updated',
        description: `Currency: ${updated.preferred_currency}, Locale: ${updated.locale}.`,
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : 'Failed to update account';
      toast({ title: 'Failed to update account', description: message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h1 className="page-title">Account Settings</h1>
          <p className="page-subtitle">
            Manage your profile defaults. Currency and locale settings control
            how dates, numbers, and amounts are displayed across the app.
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
            <div className="space-y-2">
              <Label htmlFor="locale">Display Locale</Label>
              <p className="text-xs text-muted-foreground">
                Controls how dates, numbers, and currencies are formatted.
              </p>
              <select
                id="locale"
                className="input"
                value={locale}
                onChange={(e) => setLocaleState(e.target.value)}
              >
                {SUPPORTED_LOCALES.map((item) => (
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
    </div>
  );
}
