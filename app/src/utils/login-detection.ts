// A lightweight login anomaly detector that stores a short history of
// recent login contexts in localStorage and flags an unusual login when the
// new context has not appeared in the recent history.
type HistoryRecord = {
  userAgent?: string;
  ip?: string;
  timestamp?: number;
};

function getKey(userId: number): string {
  return `finmind_login_history_${userId}`;
}

const MAX_HISTORY = 5;

export function checkUnusualLogin(
  userId: number,
  context: { userAgent?: string; ip?: string }
): boolean {
  try {
    if (typeof window === 'undefined' || !('localStorage' in window)) {
      return false;
    }

    const key = getKey(userId);
    const raw = localStorage.getItem(key);
    const history: HistoryRecord[] = raw ? (JSON.parse(raw) as HistoryRecord[]) : [];

    // Determine if the new context has been seen before. We treat a login as
    // unusual if neither the userAgent nor the IP matches any of the recent
    // history entries.
    const hasSeenUA = typeof context.userAgent === 'string'
      ? history.some((h) => h.userAgent === context.userAgent)
      : false;
    const hasSeenIP = typeof context.ip === 'string'
      ? history.some((h) => h.ip === context.ip)
      : false;

    const isUnusual = !!(context.userAgent || context.ip) && !(hasSeenUA || hasSeenIP);

    // Update history with the latest context, keeping a reasonable window.
    const updated: HistoryRecord = {
      userAgent: context.userAgent,
      ip: context.ip,
      timestamp: Date.now(),
    };
    const newHistory = [...history, updated].slice(-MAX_HISTORY);
    localStorage.setItem(key, JSON.stringify(newHistory));

    return isUnusual;
  } catch {
    // Be conservative in error scenarios: do not flag as unusual.
    return false;
  }
}
