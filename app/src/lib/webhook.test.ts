/**
 * Webhook Event System – focused test suite
 *
 * Covers the three critical acceptance criteria:
 *  1. Signed delivery (HMAC-SHA256 signature is verifiable)
 *  2. Retry & failure handling (3 retries logged; subscription auto-disabled)
 *  3. Idempotency key stability across retries
 */

import {
  computeSignature,
  verifySignature,
  generateSecret,
  createSubscription,
  deliverWebhook,
  emitEvent,
  getDeliveryLogs,
  getSubscription,
  WebhookEventType,
} from './webhook';

// ---------------------------------------------------------------------------
// Helper: create a mock fetch that returns a given status N times then succeeds
// ---------------------------------------------------------------------------
function mockFetch(responses: number[]) {
  let call = 0;
  return vi.fn().mockImplementation(async () => {
    const status = responses[call] ?? 200;
    call++;
    return { status } as Response;
  });
}

// Use Vitest globals (vi) – compatible with the Vite/Vitest setup typical in
// this kind of React project.
declare const vi: any;
declare function describe(name: string, fn: () => void): void;
declare function it(name: string, fn: () => Promise<void>): void;
declare function expect(val: any): any;
declare function beforeEach(fn: () => void): void;

describe('Webhook Event System', () => {
  // -------------------------------------------------------------------------
  // Test 1: Signed delivery
  // WHY: Consumers must be able to verify payload authenticity via HMAC-SHA256.
  // -------------------------------------------------------------------------
  it('signs payloads with HMAC-SHA256 and allows consumer verification', async () => {
    const secret = generateSecret();
    const payload = JSON.stringify({ event: 'expense.created', data: { id: 1 } });

    const signature = await computeSignature(payload, secret);

    // Signature must be a 64-char hex string (SHA-256 = 32 bytes)
    expect(signature).toMatch(/^[0-9a-f]{64}$/);

    // Consumer-side verification must pass for the correct payload+secret
    const valid = await verifySignature(payload, secret, signature);
    expect(valid).toBe(true);

    // Must FAIL for a tampered payload (prevents replay / forgery)
    const tampered = await verifySignature(payload + 'x', secret, signature);
    expect(tampered).toBe(false);

    // Must FAIL for a wrong secret
    const wrongSecret = await verifySignature(payload, generateSecret(), signature);
    expect(wrongSecret).toBe(false);
  });

  // -------------------------------------------------------------------------
  // Test 2: Retry with backoff + auto-disable after MAX_FAILURES
  // WHY: At-least-once delivery requires retries; persistent failures must
  //      not silently loop forever – auto-disable protects the consumer.
  // -------------------------------------------------------------------------
  it('retries up to MAX_ATTEMPTS and auto-disables subscription on repeated failure', async () => {
    // Intercept fetch with all-500 responses
    const MAX_ATTEMPTS = 5;
    const allFailing = Array(MAX_ATTEMPTS).fill(500);
    const fetchMock = mockFetch(allFailing);
    global.fetch = fetchMock as any;

    // Override sleep to avoid real delays in CI
    // (In production the delays provide real backoff)
    vi.useFakeTimers();

    const { subscription } = await createSubscription(
      'user-test-1',
      'https://example.com/hook',
      ['expense.created']
    );

    // Run delivery; advance timers to skip backoff waits
    const deliveryPromise = deliverWebhook(
      subscription,
      'expense.created',
      { amount: 42 }
    );
    // Advance through all backoff delays
    for (let i = 0; i < MAX_ATTEMPTS; i++) {
      await vi.runAllTimersAsync();
    }
    const result = await deliveryPromise;

    expect(result).toBe(false); // delivery must report failure

    const logs = getDeliveryLogs(subscription.id);
    // Every attempt must be logged
    expect(logs.length).toBe(MAX_ATTEMPTS);
    expect(logs.every((l) => l.status === 'failed')).toBe(true);
    expect(logs.every((l) => l.responseCode === 500)).toBe(true);

    // All logs share the same idempotency key (same logical event)
    const keys = new Set(logs.map((l) => l.idempotencyKey));
    expect(keys.size).toBe(1);

    // After MAX_FAILURES_BEFORE_DISABLE consecutive event failures the
    // subscription must be soft-disabled so the user can fix their endpoint.
    const updated = getSubscription(subscription.id)!;
    expect(updated.active).toBe(false);

    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Test 3: 404/410 causes immediate disable (no pointless retries)
  // WHY: Retrying a permanently-gone URL wastes resources; a 404/410 is a
  //      signal that the consumer has explicitly removed the endpoint.
  // -------------------------------------------------------------------------
  it('immediately disables subscription on 404 or 410 without further retries', async () => {
    const fetchMock = mockFetch([410]);
    global.fetch = fetchMock as any;

    const { subscription } = await createSubscription(
      'user-test-2',
      'https://example.com/gone',
      ['bill.paid']
    );

    const result = await deliverWebhook(subscription, 'bill.paid', { billId: 7 });

    expect(result).toBe(false);
    // Only ONE attempt must have been made (no retry on permanent failure)
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const logs = getDeliveryLogs(subscription.id);
    expect(logs.length).toBe(1);
    expect(logs[0].responseCode).toBe(410);

    const updated = getSubscription(subscription.id)!;
    expect(updated.active).toBe(false);
  });
});
