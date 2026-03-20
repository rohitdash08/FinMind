import { getLocale } from '@/lib/auth';
import { getCurrency } from '@/lib/auth';

/**
 * Locale-aware formatting utilities using the Intl API.
 * All functions read the user's locale preference from localStorage
 * unless an explicit locale is passed.
 */

export function formatMoney(
  amount: number,
  currencyCode?: string,
  locale?: string,
): string {
  const resolvedLocale = locale || getLocale();
  const currency = (currencyCode || getCurrency() || 'USD').toUpperCase();
  try {
    return new Intl.NumberFormat(resolvedLocale, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(amount || 0));
  } catch {
    return `${currency} ${Number(amount || 0).toFixed(2)}`;
  }
}

export function formatNumber(
  value: number,
  locale?: string,
  options?: Intl.NumberFormatOptions,
): string {
  const resolvedLocale = locale || getLocale();
  try {
    return new Intl.NumberFormat(resolvedLocale, options).format(
      Number(value || 0),
    );
  } catch {
    return String(value);
  }
}

export function formatDate(
  date: string | Date,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const resolvedLocale = locale || getLocale();
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return String(date);
  try {
    return new Intl.DateTimeFormat(resolvedLocale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      ...options,
    }).format(d);
  } catch {
    return d.toLocaleDateString();
  }
}

export function formatDateTime(
  date: string | Date,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  const resolvedLocale = locale || getLocale();
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return String(date);
  try {
    return new Intl.DateTimeFormat(resolvedLocale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      ...options,
    }).format(d);
  } catch {
    return d.toLocaleString();
  }
}

export function formatPercent(
  value: number,
  locale?: string,
  fractionDigits = 0,
): string {
  const resolvedLocale = locale || getLocale();
  try {
    return new Intl.NumberFormat(resolvedLocale, {
      style: 'percent',
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    }).format(value / 100);
  } catch {
    return `${value.toFixed(fractionDigits)}%`;
  }
}
