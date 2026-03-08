export interface LoginEvent {
  userId?: string;
  ip?: string;
  location?: string;
  device?: string;
  timestamp: string; // ISO string
}

export interface Anomaly {
  userId?: string;
  loginEvent: LoginEvent;
  reason: string;
  score: number;
}

// Detect unusual login behavior for a sequence of login events per user.
// Simple heuristic:
// - An event with a location different from previous locations within a short window (default 24h) is an anomaly.
// - An event with a device different from the most common device in the recent history is an anomaly.
export function detectUnusualLogin(events: LoginEvent[]): Anomaly[] {
  if (!Array.isArray(events)) return [];

  // Group by userId when available; if no userId, skip those events.
  const byUser = new Map<string, LoginEvent[]>();

  for (const e of events) {
    const user = e.userId;
    if (!user) continue; // require userId to attribute anomaly
    if (!byUser.has(user)) byUser.set(user, []);
    byUser.get(user)!.push(e);
  }

  const anomalies: Anomaly[] = [];

  // Process each user separately
  for (const [user, list] of byUser.entries()) {
    // sort by timestamp ascending
    const sorted = list.slice().sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

    // Track history of devices and locations for simple heuristics
    const deviceHistory: string[] = [];

    for (let i = 0; i < sorted.length; i++) {
      const ev = sorted[i];
      const time = new Date(ev.timestamp).getTime();

      // look back at previous events within a reasonable window (e.g., 7 days)
      const windowMs = 7 * 24 * 60 * 60 * 1000; // 7 days window
      const prev = sorted.filter((_, idx) => idx < i && (new Date(sorted[idx].timestamp).getTime() >= time - windowMs));

      // determine most common device in previous events
      const prevDevices = prev.map(p => p.device).filter(Boolean) as string[];
      const mostCommonDevice = mostCommon(prevDevices);

      // anomaly checks
      let reason = '';
      let score = 0;

      // Unusual location: if there is a previous event with a different location
      const hasLocationCompared = prev.length > 0 && ev.location;
      if (hasLocationCompared && ev.location) {
        const differentLocation = prev.some(p => p.location && p.location !== ev.location);
        if (differentLocation) {
          reason += (reason ? '; ' : '') + 'Unusual login location';
          score += 1;
        }
      }

      // New device: compare with most common device in history
      if (ev.device && mostCommonDevice && ev.device !== mostCommonDevice) {
        reason += (reason ? '; ' : '') + 'New device detected';
        score += 1;
      }

      if (reason) {
        anomalies.push({ userId: user, loginEvent: ev, reason, score });
      }

      // update device history
      if (ev.device) deviceHistory.push(ev.device);
    }
  }

  return anomalies;
}

function mostCommon(arr: string[]): string | null {
  if (arr.length === 0) return null;
  const freq: Record<string, number> = {};
  for (const v of arr) {
    freq[v] = (freq[v] ?? 0) + 1;
  }
  let maxCount = 0;
  let maxVal: string | null = null;
  for (const k of Object.keys(freq)) {
    if (freq[k] > maxCount) {
      maxCount = freq[k];
      maxVal = k;
    }
  }
  return maxVal;
}
