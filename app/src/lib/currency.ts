import { getCurrency } from '@/lib/auth';

export function formatMoney(amount: number, currencyCode?: string): string {
  const currency = (currencyCode || getCurrency() || 'USD').toUpperCase();
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(amount || 0));
  } catch {
    return `${currency} ${Number(amount || 0).toFixed(2)}`;
  }
}
