import { formatCurrency } from '@/lib/locale';

export function formatMoney(amount: number, currencyCode?: string): string {
  return formatCurrency(amount, currencyCode);
}
