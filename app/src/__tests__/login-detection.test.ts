import { checkUnusualLogin } from "../utils/login-detection";

describe("checkUnusualLogin", () => {
  beforeEach(() => {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.clear();
    }
  });

  test("returns false on first login and stores history with new context", () => {
    const isUnusual = checkUnusualLogin(1, { userAgent: 'UA1', ip: '1.2.3.4' });
    expect(isUnusual).toBe(false);
    const raw = localStorage.getItem('finmind_login_history_1');
    expect(raw).not.toBeNull();
    const hist = JSON.parse(raw!);
    const last = hist[hist.length - 1];
    expect(last.userAgent).toBe('UA1');
    expect(last.ip).toBe('1.2.3.4');
    expect(typeof last.timestamp).toBe('number');
  });

  test("returns false when context already seen in history", () => {
    localStorage.setItem('finmind_login_history_1', JSON.stringify([{ userAgent: 'UA1', ip: '1.2.3.4', timestamp: Date.now() }]));
    const isUnusual = checkUnusualLogin(1, { userAgent: 'UA1', ip: '1.2.3.4' });
    expect(isUnusual).toBe(false);
  });

  test("flags unusual when both userAgent and IP are unseen", () => {
    localStorage.setItem('finmind_login_history_1', JSON.stringify([{ userAgent: 'OldUA', ip: '1.2.3.4', timestamp: Date.now() }]));
    const isUnusual = checkUnusualLogin(1, { userAgent: 'NewUA', ip: '9.9.9.9' });
    expect(isUnusual).toBe(true);
  });

  test("handles empty history gracefully and creates first entry", () => {
    const isUnusual = checkUnusualLogin(2, { userAgent: 'UA2', ip: '2.3.4.5' });
    expect(isUnusual).toBe(false);
    const raw = localStorage.getItem('finmind_login_history_2');
    expect(raw).not.toBeNull();
    const hist = JSON.parse(raw!);
    expect(hist.length).toBe(1);
    expect(hist[0].userAgent).toBe('UA2');
    expect(hist[0].ip).toBe('2.3.4.5');
  });

  test("clips history to MAX_HISTORY on update", () => {
    // Prepopulate with 5 entries
    const base = [
      { userAgent: 'A1', ip: '1.1.1.1' },
      { userAgent: 'A2', ip: '2.2.2.2' },
      { userAgent: 'A3', ip: '3.3.3.3' },
      { userAgent: 'A4', ip: '4.4.4.4' },
      { userAgent: 'A5', ip: '5.5.5.5' },
    ];
    localStorage.setItem('finmind_login_history_3', JSON.stringify(base.map(b => ({ ...b, timestamp: Date.now() - 1000 }))));
    const isUnusual = checkUnusualLogin(3, { userAgent: 'NewUA', ip: '9.9.9.9' });
    expect(isUnusual).toBe(true);
    const raw = localStorage.getItem('finmind_login_history_3');
    expect(raw).not.toBeNull();
    const hist = JSON.parse(raw!);
    expect(hist.length).toBe(5);
    expect(hist[hist.length - 1].userAgent).toBe('NewUA');
    expect(hist[hist.length - 1].ip).toBe('9.9.9.9');
  });

  test("legacy history format is normalized and used for matching", () => {
    localStorage.setItem('finmind_login_history_4', JSON.stringify({ lastUserAgent: 'LegacyUA', lastIp: '10.0.0.1', lastTimestamp: 12345 }));
    const isUnusual = checkUnusualLogin(4, { userAgent: 'LegacyUA', ip: '10.0.0.1' });
    // Since both UA and IP match legacy data, should not be unusual
    expect(isUnusual).toBe(false);
    const raw = localStorage.getItem('finmind_login_history_4');
    expect(raw).not.toBeNull();
    const hist = JSON.parse(raw!);
    expect(hist.length).toBe(1);
    expect(hist[0].userAgent).toBe('LegacyUA');
  });
});
