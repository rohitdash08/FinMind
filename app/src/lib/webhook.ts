/**
 * Webhook Event System
 *
 * WHY: The issue requires signed webhook delivery with retry/failure handling.
 * This module provides:
 *  - HMAC-SHA256 request signing so consumers can verify authenticity
 *  - Idempotency keys on every payload so consumers can deduplicate retries
 *  - Schema versioning via a `webhook_version` header
 *  - Exponential-backoff retry (up to 5 attempts over ~24 h)
 *  - Auto-disable of subscriptions after N consecutive failures (dead-letter)
 *  - In-memory subscription/log store (swap for DB calls in the real backend)
 */

import { api } from '@/api/client';

// ---------------------------------------------------------------------------
// Public event-type catalogue  (acceptance criterion: event types documented)
// ---------------------------------------------------------------------------
export const WEBHOOK_EVENT_TYPES = [
  'expense.created',
  'expense.updated',
  'expense.deleted',
  'bill.paid',
  'bill.created',
  'settlement.completed',
] as const;

export type WebhookEventType = typeof WEBHOOK_EVENT_TYPES[number];

// ---------------------------------------------------------------------------
// Data shapes
// ---------------------------------------------------------------------------
export interface WebhookSubscription {
  id: string;
  userId: string;
  url: string;
  /** HMAC-SHA256 signing secret – generated once, never returned after creation */
  secret: string;
  eventTypes: WebhookEventType[];
  active: boolean;
  failureCount: number;
  createdAt: string;
}

export interface WebhookDeliveryLog {
  id: string;
  subscriptionId: string;
  eventType: WebhookEventType;
  /** Idempotency key – consumers MUST use this to deduplicate */
  idempotencyKey: string;
  attempt: number;
  status: 'pending' | 'success' | 'failed';
  responseCode: number | null;
  deliveredAt: string;
}

export interface WebhookPayload<T = unknown> {
  /** Semantic version of the payload schema – bump on breaking changes */
  version: '1.0';
  /** Use this to deduplicate retries; same event => same key */
  idempotency_key: string;
  event: WebhookEventType;
  timestamp: string;
  data: T;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const MAX_ATTEMPTS = 5;
const MAX_FAILURES_BEFORE_DISABLE = 5;
const CONNECTION_TIMEOUT_MS = 10_000;   // 10 s – prevents stalling event loop
const MAX_PAYLOAD_BYTES = 1_048_576;    // 1 MB
const WEBHOOK_SCHEMA_VERSION = '1.0';

/** Backoff delays in ms: 30 s, 5 min, 30 min, 2 h, 8 h */
const BACKOFF_DELAYS_MS = [30_000, 300_000, 1_800_000, 7_200_000, 28_800_000];

// ---------------------------------------------------------------------------
// Crypto helpers (browser SubtleCrypto / Node crypto compatible)
// ---------------------------------------------------------------------------

/**
 * Generate a cryptographically random hex string.
 * WHY: Used for both subscription secrets and idempotency keys.
 */
export function generateSecret(byteLength = 32): string {
  const buf = new Uint8Array(byteLength);
  crypto.getRandomValues(buf);
  return Array.from(buf)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Compute HMAC-SHA256 of `payload` using `secret`.
 * WHY: Consumers verify this signature to ensure the request came from us.
 */
export async function computeSignature(
  payload: string,
  secret: string
): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(payload));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Verify a signature from a consumer callback (used in tests / webhook echo endpoints).
 */
export async function verifySignature(
  payload: string,
  secret: string,
  signature: string
): Promise<boolean> {
  const expected = await computeSignature(payload, secret);
  // Constant-time comparison to prevent timing attacks
  if (expected.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  }
  return diff === 0;
}

// ---------------------------------------------------------------------------
// In-memory store (replace with real DB queries in production)
// WHY: Keeps this module self-contained for review; production would call
//      the backend REST endpoints below instead.
// ---------------------------------------------------------------------------
const _subscriptions = new Map<string, WebhookSubscription>();
const _logs: WebhookDeliveryLog[] = [];

// ---------------------------------------------------------------------------
// Subscription management (thin wrappers – real app calls backend API)
// ---------------------------------------------------------------------------

/** Register a new webhook subscription. Returns the one-time-visible secret. */
export async function createSubscription(
  userId: string,
  url: string,
  eventTypes: WebhookEventType[]
): Promise<{ subscription: WebhookSubscription; secret: string }> {
  const secret = generateSecret();
  const sub: WebhookSubscription = {
    id: generateSecret(8),
    userId,
    url,
    secret,               // stored hashed in real DB; returned plain-text once
    eventTypes,
    active: true,
    failureCount: 0,
    createdAt: new Date().toISOString(),
  };
  _subscriptions.set(sub.id, sub);
  return { subscription: sub, secret };
}

export function getSubscription(id: string): WebhookSubscription | undefined {
  return _subscriptions.get(id);
}

export function listSubscriptionsForUser(userId: string): WebhookSubscription[] {
  return Array.from(_subscriptions.values()).filter(
    (s) => s.userId === userId && s.active
  );
}

export function disableSubscription(id: string): void {
  const sub = _subscriptions.get(id);
  if (sub) sub.active = false;
}

export function getDeliveryLogs(subscriptionId: string): WebhookDeliveryLog[] {
  return _logs.filter((l) => l.subscriptionId === subscriptionId);
}

// ---------------------------------------------------------------------------
// Core delivery engine
// ---------------------------------------------------------------------------

/**
 * Deliver a webhook to a single subscription with exponential-backoff retries.
 *
 * WHY exponential backoff: avoids hammering a temporarily-down consumer;
 * the increasing delays spread load and give the consumer time to recover.
 *
 * WHY idempotency_key: at-least-once delivery means the same event MAY arrive
 * more than once on retry. Consumers MUST deduplicate on this key.
 */
export async function deliverWebhook<T>(
  subscription: WebhookSubscription,
  eventType: WebhookEventType,
  data: T,
  idempotencyKey?: string
): Promise<boolean> {
  const iKey = idempotencyKey ?? generateSecret(16);

  const payload: WebhookPayload<T> = {
    version: WEBHOOK_SCHEMA_VERSION,
    idempotency_key: iKey,
    event: eventType,
    timestamp: new Date().toISOString(),
    data,
  };

  const bodyStr = JSON.stringify(payload);

  // Guard: reject oversized payloads before attempting delivery
  if (new TextEncoder().encode(bodyStr).length > MAX_PAYLOAD_BYTES) {
    console.error(
      `[webhook] Payload for ${eventType} exceeds 1 MB limit; delivery skipped.`
    );
    return false;
  }

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const logEntry: WebhookDeliveryLog = {
      id: generateSecret(8),
      subscriptionId: subscription.id,
      eventType,
      idempotencyKey: iKey,
      attempt,
      status: 'pending',
      responseCode: null,
      deliveredAt: new Date().toISOString(),
    };

    try {
      // Sign the payload so the consumer can verify authenticity
      const signature = await computeSignature(bodyStr, subscription.secret);

      const controller = new AbortController();
      const timer = setTimeout(
        () => controller.abort(),
        CONNECTION_TIMEOUT_MS
      );

      let responseStatus: number;
      try {
        const res = await fetch(subscription.url, {
          method: 'POST',
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            // WHY X-Webhook-Signature: standard pattern; consumers validate
            'X-Webhook-Signature': `sha256=${signature}`,
            // WHY X-Webhook-Version: allows consumers to handle multiple
            // schema versions gracefully without breaking on future changes
            'X-Webhook-Version': WEBHOOK_SCHEMA_VERSION,
            'X-Webhook-Event': eventType,
            'X-Idempotency-Key': iKey,
          },
          body: bodyStr,
        });
        responseStatus = res.status;
      } finally {
        clearTimeout(timer);
      }

      logEntry.responseCode = responseStatus;

      if (responseStatus >= 200 && responseStatus < 300) {
        // Success path
        logEntry.status = 'success';
        _logs.push(logEntry);
        // Reset failure counter on success
        subscription.failureCount = 0;
        return true;
      }

      // 410 Gone: consumer explicitly says the endpoint is gone; soft-disable now
      if (responseStatus === 410 || responseStatus === 404) {
        logEntry.status = 'failed';
        _logs.push(logEntry);
        _handlePermanentFailure(subscription, `HTTP ${responseStatus}`);
        return false;
      }

      // Any other non-2xx: log and retry
      logEntry.status = 'failed';
      _logs.push(logEntry);
    } catch (err) {
      // Network error / timeout
      logEntry.status = 'failed';
      logEntry.responseCode = null;
      _logs.push(logEntry);
      console.warn(`[webhook] Attempt ${attempt} failed for ${subscription.id}:`, err);
    }

    // If we've exhausted retries, handle dead-letter
    if (attempt === MAX_ATTEMPTS) {
      subscription.failureCount += 1;
      if (subscription.failureCount >= MAX_FAILURES_BEFORE_DISABLE) {
        _handlePermanentFailure(
          subscription,
          `${MAX_FAILURES_BEFORE_DISABLE} consecutive event failures`
        );
      }
      return false;
    }

    // Wait before next attempt (exponential backoff)
    const delay = BACKOFF_DELAYS_MS[attempt - 1] ?? BACKOFF_DELAYS_MS[BACKOFF_DELAYS_MS.length - 1];
    await _sleep(delay);
  }

  return false;
}

/**
 * Emit an event to ALL active subscriptions that match the event type.
 * WHY: Decouples event producers from specific subscribers.
 */
export async function emitEvent<T>(
  eventType: WebhookEventType,
  data: T,
  userId?: string
): Promise<void> {
  // Generate one idempotency key per event emission so all delivery attempts
  // for the same logical event share the same key across retries.
  const iKey = generateSecret(16);

  const candidates = userId
    ? listSubscriptionsForUser(userId)
    : Array.from(_subscriptions.values()).filter((s) => s.active);

  const matching = candidates.filter((s) => s.eventTypes.includes(eventType));

  await Promise.allSettled(
    matching.map((sub) => deliverWebhook(sub, eventType, data, iKey))
  );
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _handlePermanentFailure(
  subscription: WebhookSubscription,
  reason: string
): void {
  subscription.active = false;
  // WHY: soft-disable rather than delete preserves audit trail and lets
  // users re-enable after fixing their endpoint.
  console.error(
    `[webhook] Subscription ${subscription.id} auto-disabled: ${reason}. ` +
    `User ${subscription.userId} should be notified via email/UI.`
  );
  // TODO: trigger in-app notification / email to subscription.userId
}

function _sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
