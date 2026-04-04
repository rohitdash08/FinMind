import { getCurrency } from '@/lib/auth';

const LOCALE_KEY = 'fm_locale';

export const SUPPORTED_LOCALES = [
  'en-US', 'en-GB', 'en-IN', 'de-DE', 'ja-JP', 'fr-FR', 'ar-SA', 'zh-CN',
] as const;

export function getLocale(): string {
  return localStorage.getItem(LOCALE_KEY) || navigator.language;
}

export function setLocale(locale: string) {
  localStorage.setItem(LOCALE_KEY, locale);
  window.dispatchEvent(new Event('locale_changed'));
}

export function formatDate(date: Date | string, options?: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(getLocale(), options).format(typeof date === 'string' ? new Date(date) : date);
}

export function formatCurrency(amount: number, currencyCode?: string): string {
  const currency = (currencyCode || getCurrency() || 'USD').toUpperCase();
  try {
    return new Intl.NumberFormat(getLocale(), {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(amount || 0));
  } catch {
    return `${currency} ${Number(amount || 0).toFixed(2)}`;
  }
}

export function formatNumber(n: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(getLocale(), options).format(n);
}
