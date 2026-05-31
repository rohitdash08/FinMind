import {
  getToken,
  setToken,
  clearToken,
  getRefreshToken,
  setRefreshToken,
  clearRefreshToken,
  getCurrency,
  setCurrency,
  TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  CURRENCY_KEY,
} from '@/lib/auth';

describe('auth token helpers', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.spyOn(window, 'dispatchEvent');
  });

  afterEach(() => {
    (window.dispatchEvent as jest.Mock | any).mockRestore?.();
  });

  it('sets and gets access token, dispatches auth_changed', () => {
    expect(getToken()).toBeNull();
    setToken('abc');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('abc');
    expect(getToken()).toBe('abc');
    expect(window.dispatchEvent).toHaveBeenCalledWith(expect.objectContaining({ type: 'auth_changed' }));
  });

  it('clears access token and dispatches auth_changed', () => {
    localStorage.setItem(TOKEN_KEY, 'abc');
    clearToken();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.dispatchEvent).toHaveBeenCalledWith(expect.objectContaining({ type: 'auth_changed' }));
  });

  it('sets and clears refresh token, dispatches auth_changed', () => {
    expect(getRefreshToken()).toBeNull();
    setRefreshToken('ref');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('ref');
    expect(getRefreshToken()).toBe('ref');
    clearRefreshToken();
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    expect(window.dispatchEvent).toHaveBeenCalledWith(expect.objectContaining({ type: 'auth_changed' }));
  });

  it('sets and gets preferred currency, dispatches currency_changed', () => {
    expect(getCurrency()).toBe('INR');
    setCurrency('INR');
    expect(localStorage.getItem(CURRENCY_KEY)).toBe('INR');
    expect(getCurrency()).toBe('INR');
    expect(window.dispatchEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'currency_changed' }),
    );
  });
});
