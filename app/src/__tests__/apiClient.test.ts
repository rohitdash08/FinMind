import { api } from '@/api/client';
import * as auth from '@/api/auth';

// Use real localStorage via JSDOM

describe('api client', () => {
  const originalFetch = global.fetch as any;

  beforeEach(() => {
    jest.resetAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('passes through on 200 JSON', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    const res = await api('/x');
    expect(res).toEqual({ ok: true });
  });

  it('retries once after refresh on 401 and succeeds', async () => {
    localStorage.setItem('fm_token', 'expired');
    localStorage.setItem('fm_refresh_token', 'r1');

    jest.spyOn(auth, 'refresh').mockResolvedValue({ access_token: 'newA', refresh_token: 'newR' } as any);

    // First call 401, second call 200
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce(new Response('unauthorized', { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: 42 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));

    const res = await api('/secure');
    expect(res).toEqual({ data: 42 });
    expect(auth.refresh).toHaveBeenCalledWith('r1');
    // token should be updated in storage
    expect(localStorage.getItem('fm_token')).toBe('newA');
  });

  it('clears tokens and throws on 401 when refresh fails', async () => {
    localStorage.setItem('fm_token', 'expired');
    localStorage.setItem('fm_refresh_token', 'r1');

    jest.spyOn(auth, 'refresh').mockRejectedValue(new Error('bad refresh'));

    global.fetch = jest.fn().mockResolvedValue(new Response('unauthorized', { status: 401 }));

    await expect(api('/secure')).rejects.toThrow(/unauthorized|Unauthorized/i);
    expect(localStorage.getItem('fm_token')).toBeNull();
    expect(localStorage.getItem('fm_refresh_token')).toBeNull();
  });

  it('throws with parsed error message on non-OK response', async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: 'nope' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }));

    await expect(api('/bad')).rejects.toThrow('nope');
  });

  it('hides raw HTML error pages with a friendly server message', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce(
      new Response(
        '<!doctype html><html><body><h1>500 Internal Server Error</h1></body></html>',
        {
          status: 500,
          headers: { 'Content-Type': 'text/html; charset=utf-8' },
        },
      ),
    );

    await expect(api('/auth/login')).rejects.toThrow(
      'Server error. Please try again in a minute.',
    );
  });
});
