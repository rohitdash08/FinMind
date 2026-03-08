type HistoryRecord = {
  lastUserAgent?: string;
  lastIp?: string;
  lastTimestamp?: number;
};

function getKey(userId: number): string {
  return `finmind_login_history_${userId}`;
}

export function checkUnusualLogin(userId: number, context: { userAgent?: string; ip?: string }): boolean {
  try {
    if (typeof window === 'undefined' || !('localStorage' in window)) {
      return false;
    }
    const key = getKey(userId);
    const raw = localStorage.getItem(key);
    const prev: HistoryRecord = raw ? (JSON.parse(raw) as HistoryRecord) : {};

    const hadHistory = typeof prev.lastTimestamp === 'number';
    const isUnusual = hadHistory && (
      (context.userAgent && prev.lastUserAgent && context.userAgent !== prev.lastUserAgent) ||
      (context.ip && prev.lastIp && context.ip !== prev.lastIp)
    );

    // Update history with latest context
    const updated: HistoryRecord = {
      lastUserAgent: context.userAgent ?? prev.lastUserAgent,
      lastIp: context.ip ?? prev.lastIp,
      lastTimestamp: Date.now(),
    };
    localStorage.setItem(key, JSON.stringify(updated));
    return !!isUnusual;
  } catch {
    // If anything goes wrong, fail-safe by not flagging.
    return false;
  }
}
