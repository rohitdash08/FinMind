import { checkUnusualLogin } from './login-detection';

describe('checkUnusualLogin', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('no history -> returns false and writes current context', () => {
    const res = checkUnusualLogin(1, { userAgent: 'UA1', ip: '1.2.3.4' });
    expect(res).toBe(false);
    const raw = localStorage.getItem('finmind_login_history_1');
    expect(raw).not.toBeNull();
    const hist = JSON.parse(raw!);
    expect(hist.lastUserAgent).toBe('UA1');
    expect(hist.lastIp).toBe('1.2.3.4');
    expect(typeof hist.lastTimestamp).toBe('number');
  });

  test('same context as history -> not unusual', () => {
    // seed history with UA1/IP1
    localStorage.setItem('finmind_login_history_1', JSON.stringify({ lastUserAgent: 'UA1', lastIp: '1.2.3.4', lastTimestamp: Date.now() }));
    const res = checkUnusualLogin(1, { userAgent: 'UA1', ip: '1.2.3.4' });
    expect(res).toBe(false);
  });

  test('different userAgent -> unusual', () => {
    localStorage.setItem('finmind_login_history_1', JSON.stringify({ lastUserAgent: 'OldUA', lastIp: '1.2.3.4', lastTimestamp: Date.now() }));
    const res = checkUnusualLogin(1, { userAgent: 'NewUA', ip: '1.2.3.4' });
    expect(res).toBe(true);
  });
});
