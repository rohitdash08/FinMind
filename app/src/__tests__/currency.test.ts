import { formatDate, formatMoney, formatNumber, formatPercent } from '@/lib/currency';

jest.mock('@/lib/auth', () => ({
  getCurrency: () => 'USD',
}));

describe('locale-aware formatters', () => {
  const originalLanguage = navigator.language;

  afterEach(() => {
    Object.defineProperty(navigator, 'language', {
      configurable: true,
      value: originalLanguage,
    });
  });

  it('formats money with the browser locale and selected currency', () => {
    Object.defineProperty(navigator, 'language', {
      configurable: true,
      value: 'en-US',
    });

    expect(formatMoney(1234.5, 'USD')).toBe('$1,234.50');
  });

  it('formats numbers and percentages with Intl', () => {
    Object.defineProperty(navigator, 'language', {
      configurable: true,
      value: 'en-US',
    });

    expect(formatNumber(1234567)).toBe('1,234,567');
    expect(formatPercent(12.34, 1)).toBe('12.3%');
  });

  it('formats dates and falls back to the input for invalid dates', () => {
    Object.defineProperty(navigator, 'language', {
      configurable: true,
      value: 'en-US',
    });

    expect(formatDate('2026-02-20')).toBe('2/20/2026');
    expect(formatDate('not-a-date')).toBe('not-a-date');
  });
});
