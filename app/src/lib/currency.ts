import { getCurrency } from '@/lib/auth';

export function getLocale(): string | undefined {
  if (typeof navigator !== 'undefined' && navigator.language) {
    return navigator.language;
  }
  return undefined;
}

export function formatMoney(amount: number, currencyCode?: string): string {
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

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  try {
    return new Intl.NumberFormat(getLocale(), options).format(Number(value || 0));
  } catch {
    return Number(value || 0).toLocaleString('en-US');
  }
}

export function formatPercent(value: number, maximumFractionDigits = 0): string {
  return formatNumber(Number(value || 0) / 100, {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits,
  });
}

export function formatDate(value: string | Date, options?: Intl.DateTimeFormatOptions): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return typeof value === 'string' ? value : '';
  }

  try {
    return new Intl.DateTimeFormat(getLocale(), options).format(date);
  } catch {
    return date.toISOString().slice(0, 10);
  }
}
