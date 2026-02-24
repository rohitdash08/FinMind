import { getCurrency, getLocale } from '@/lib/auth';

/**
 * Format a monetary amount using the user's locale and currency preferences.
 */
export function formatCurrency(amount: number, currencyCode?: string, locale?: string): string {
  const currency = (currencyCode || getCurrency() || 'USD').toUpperCase();
  const loc = locale || getLocale() || 'en-US';
  try {
    return new Intl.NumberFormat(loc, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(amount || 0));
  } catch {
    return `${currency} ${Number(amount || 0).toFixed(2)}`;
  }
}

/**
 * Format a date string or Date object using the user's locale.
 */
export function formatDate(
  d: string | Date | null | undefined,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (!d) return '';
  const loc = locale || getLocale() || 'en-US';
  const dateObj = typeof d === 'string' ? new Date(d) : d;
  if (isNaN(dateObj.getTime())) return String(d);
  const defaultOptions: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  };
  try {
    return new Intl.DateTimeFormat(loc, options || defaultOptions).format(dateObj);
  } catch {
    return dateObj.toLocaleDateString();
  }
}

/**
 * Format a number with locale-aware grouping and decimal separators.
 */
export function formatNumber(
  n: number,
  locale?: string,
  options?: Intl.NumberFormatOptions,
): string {
  const loc = locale || getLocale() || 'en-US';
  const defaultOptions: Intl.NumberFormatOptions = {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  };
  try {
    return new Intl.NumberFormat(loc, options || defaultOptions).format(Number(n || 0));
  } catch {
    return String(n);
  }
}
