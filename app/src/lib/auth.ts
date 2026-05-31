export const TOKEN_KEY = 'fm_token';
export const REFRESH_TOKEN_KEY = 'fm_refresh_token';
export const CURRENCY_KEY = 'fm_currency';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  // notify listeners (e.g., Navbar) that auth state changed
  window.dispatchEvent(new Event('auth_changed'));
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event('auth_changed'));
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string) {
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
  window.dispatchEvent(new Event('auth_changed'));
}

export function clearRefreshToken() {
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.dispatchEvent(new Event('auth_changed'));
}

export function getCurrency(): string {
  return localStorage.getItem(CURRENCY_KEY) || 'INR';
}

export function setCurrency(currency: string) {
  localStorage.setItem(CURRENCY_KEY, currency);
  window.dispatchEvent(new Event('currency_changed'));
}
