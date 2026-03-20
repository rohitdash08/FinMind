import {
  formatMoney,
  formatNumber,
  formatDate,
  formatDateTime,
  formatPercent,
} from '@/lib/formatting';

// Mock the auth module so we control locale/currency
jest.mock('@/lib/auth', () => ({
  getLocale: jest.fn(() => 'en-US'),
  getCurrency: jest.fn(() => 'USD'),
}));

import { getLocale, getCurrency } from '@/lib/auth';

describe('formatting utilities', () => {
  beforeEach(() => {
    (getLocale as jest.Mock).mockReturnValue('en-US');
    (getCurrency as jest.Mock).mockReturnValue('USD');
  });

  describe('formatMoney', () => {
    it('formats currency with user locale', () => {
      const result = formatMoney(1234.56);
      expect(result).toContain('1,234.56');
      expect(result).toContain('$');
    });

    it('respects explicit currency code', () => {
      const result = formatMoney(1000, 'EUR');
      expect(result).toContain('1,000.00');
    });

    it('respects explicit locale', () => {
      const result = formatMoney(1234.56, 'EUR', 'de-DE');
      // German format uses . for thousands and , for decimals
      expect(result).toContain('1.234,56');
    });

    it('handles zero', () => {
      const result = formatMoney(0);
      expect(result).toContain('0.00');
    });

    it('falls back on invalid currency code', () => {
      const result = formatMoney(100, 'INVALID');
      expect(result).toContain('INVALID');
      expect(result).toContain('100.00');
    });
  });

  describe('formatNumber', () => {
    it('formats with thousand separators for en-US', () => {
      expect(formatNumber(1234567)).toBe('1,234,567');
    });

    it('respects explicit locale', () => {
      const result = formatNumber(1234567, 'de-DE');
      expect(result).toBe('1.234.567');
    });

    it('handles zero', () => {
      expect(formatNumber(0)).toBe('0');
    });
  });

  describe('formatDate', () => {
    it('formats a date string', () => {
      const result = formatDate('2024-03-15');
      // en-US short month format
      expect(result).toMatch(/Mar\s+15,?\s+2024/);
    });

    it('formats a Date object', () => {
      const result = formatDate(new Date(2024, 0, 1));
      expect(result).toMatch(/Jan\s+1,?\s+2024/);
    });

    it('returns original string for invalid date', () => {
      expect(formatDate('not-a-date')).toBe('not-a-date');
    });

    it('respects explicit locale', () => {
      const result = formatDate('2024-03-15', 'de-DE');
      // German format: "15. Mrz 2024" or "15. Mär. 2024" or "15. März 2024"
      expect(result).toMatch(/15\.\s*(Mrz|Mär|März)\.?\s*2024/);
    });
  });

  describe('formatDateTime', () => {
    it('includes time in the output', () => {
      const result = formatDateTime('2024-03-15T14:30:00');
      expect(result).toMatch(/Mar/);
      // Should contain some time representation
      expect(result).toMatch(/\d{1,2}:\d{2}/);
    });
  });

  describe('formatPercent', () => {
    it('formats a percentage value', () => {
      expect(formatPercent(75)).toBe('75%');
    });

    it('respects fraction digits', () => {
      const result = formatPercent(33.33, undefined, 1);
      expect(result).toBe('33.3%');
    });

    it('respects explicit locale', () => {
      const result = formatPercent(50, 'fr-FR');
      // French uses non-breaking space before %
      expect(result).toMatch(/50\s*%/);
    });
  });
});
