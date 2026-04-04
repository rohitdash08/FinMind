import { getLocale, setLocale, formatDate, formatCurrency, formatNumber } from '@/lib/locale';

const LOCALE_KEY = 'fm_locale';

beforeEach(() => localStorage.clear());

describe('getLocale', () => {
  it('defaults to navigator.language', () => {
    expect(getLocale()).toBe(navigator.language);
  });

  it('returns stored locale', () => {
    localStorage.setItem(LOCALE_KEY, 'de-DE');
    expect(getLocale()).toBe('de-DE');
  });
});

describe('setLocale', () => {
  it('persists and dispatches event', () => {
    const handler = jest.fn();
    window.addEventListener('locale_changed', handler);
    setLocale('fr-FR');
    expect(localStorage.getItem(LOCALE_KEY)).toBe('fr-FR');
    expect(handler).toHaveBeenCalled();
    window.removeEventListener('locale_changed', handler);
  });
});

describe('formatDate', () => {
  const date = new Date('2026-01-15T00:00:00');

  it('formats with en-US locale', () => {
    setLocale('en-US');
    expect(formatDate(date)).toContain('1');
    expect(formatDate(date)).toContain('2026');
  });

  it('formats with de-DE locale', () => {
    setLocale('de-DE');
    expect(formatDate(date)).toContain('15');
    expect(formatDate(date)).toContain('2026');
  });

  it('accepts string dates', () => {
    setLocale('en-US');
    expect(formatDate('2026-01-15')).toContain('2026');
  });
});

describe('formatCurrency', () => {
  it('formats USD', () => {
    setLocale('en-US');
    const result = formatCurrency(1234.56, 'USD');
    expect(result).toContain('1');
    expect(result).toMatch(/1.*234/);
  });

  it('formats EUR', () => {
    setLocale('de-DE');
    const result = formatCurrency(1234.56, 'EUR');
    expect(result).toContain('€');
  });

  it('formats JPY', () => {
    setLocale('ja-JP');
    const result = formatCurrency(1234, 'JPY');
    expect(result).toMatch(/[¥￥]/);
  });
});

describe('formatNumber', () => {
  it('formats large numbers with en-US', () => {
    setLocale('en-US');
    expect(formatNumber(1234567.89)).toBe('1,234,567.89');
  });

  it('formats large numbers with de-DE', () => {
    setLocale('de-DE');
    const result = formatNumber(1234567.89);
    expect(result).toContain('1.234.567');
  });
});
