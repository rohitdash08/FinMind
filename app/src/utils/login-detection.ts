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
    // Normalize history data to an array for uniform processing.
    // History can be stored as an array of records or as a legacy object
    // (e.g., { lastUserAgent, lastIp, lastTimestamp }). We normalize to an
    // array of HistoryRecord for the rest of the logic.
    let history: HistoryRecord[] = [];
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          history = parsed as HistoryRecord[];
        } else if (parsed && typeof parsed === 'object') {
          // Legacy shape: { lastUserAgent, lastIp, lastTimestamp }
          const mapped: HistoryRecord = {
            userAgent: parsed.lastUserAgent,
            ip: parsed.lastIp,
            timestamp: parsed.lastTimestamp,
          };
          if (mapped.userAgent !== undefined || mapped.ip !== undefined) {
            history = [mapped];
          }
        }
      } catch {
        history = [];
      }
    }

    // Determine if the new context has been seen before. We consider a login
    // unusual only if there is no existing entry that exactly matches both
    // userAgent and ip for the current context.
    const hasExactHit = history.some(
      (h) => h.userAgent === context.userAgent && h.ip === context.ip
    );

    const isUnusual = !!(context.userAgent || context.ip) && !hasExactHit;

    // Update history with the latest context only if this exact pair hasn't
    // been seen before. Always keep entries within MAX_HISTORY window. When a
    // new pair is seen, append it; otherwise keep history as-is.
    const updated: HistoryRecord = {
      userAgent: context.userAgent,
      ip: context.ip,
      timestamp: Date.now(),
    };

    let newHistory: HistoryRecord[] = history;
    if (!hasExactHit && (context.userAgent || context.ip)) {
      newHistory = [...history, updated].slice(-MAX_HISTORY);
    }

    localStorage.setItem(key, JSON.stringify(newHistory));

    return isUnusual;
  } catch {
    // Be conservative in error scenarios: do not flag as unusual.
    return false;
  }
}
