/**
 * Webhook Event System for FinMind
 * 
 * Provides a type-safe event bus for emitting and handling webhook events
 * throughout the application lifecycle.
 */

export type WebhookEventName =
  | 'transaction.created'
  | 'transaction.updated'
  | 'transaction.deleted'
  | 'budget.threshold_reached'
  | 'budget.exceeded'
  | 'goal.completed'
  | 'report.generated'
  | 'account.connected'
  | 'account.disconnected'
  | 'alert.triggered'

export interface WebhookEvent<T = unknown> {
  id: string
  event: WebhookEventName
  timestamp: string
  data: T
  attempts: number
}

export interface WebhookConfig {
  url: string
  secret: string
  events: WebhookEventName[]
  active: boolean
  retryCount?: number
  retryDelayMs?: number
}

type EventHandler<T = unknown> = (event: WebhookEvent<T>) => Promise<void> | void

export class WebhookEventSystem {
  private handlers: Map<WebhookEventName, Set<EventHandler>> = new Map()
  private webhooks: Map<string, WebhookConfig> = new Map()
  private retryCount: number
  private retryDelayMs: number

  constructor(opts?: { retryCount?: number; retryDelayMs?: number }) {
    this.retryCount = opts?.retryCount ?? 3
    this.retryDelayMs = opts?.retryDelayMs ?? 1000
  }

  /** Register a local event handler */
  on<T = unknown>(event: WebhookEventName, handler: EventHandler<T>): () => void {
    if (!this.handlers.has(event)) this.handlers.set(event, new Set())
    this.handlers.get(event)!.add(handler as EventHandler)
    return () => this.handlers.get(event)?.delete(handler as EventHandler)
  }

  /** Register an external webhook endpoint */
  registerWebhook(id: string, config: WebhookConfig): void {
    this.webhooks.set(id, config)
  }

  /** Remove a webhook */
  removeWebhook(id: string): boolean {
    return this.webhooks.delete(id)
  }

  /** Emit an event to all handlers and webhooks */
  async emit<T = unknown>(eventName: WebhookEventName, data: T): Promise<void> {
    const event: WebhookEvent<T> = {
      id: crypto.randomUUID?.() || Math.random().toString(36).slice(2),
      event: eventName,
      timestamp: new Date().toISOString(),
      data,
      attempts: 0,
    }

    // Local handlers
    const handlers = this.handlers.get(eventName)
    if (handlers) {
      await Promise.allSettled(
        Array.from(handlers).map(h => h(event as WebhookEvent))
      )
    }

    // External webhooks
    const matchingWebhooks = Array.from(this.webhooks.values())
      .filter(w => w.active && w.events.includes(eventName))

    await Promise.allSettled(
      matchingWebhooks.map(w => this.deliverWebhook(w, event))
    )
  }

  private async deliverWebhook(config: WebhookConfig, event: WebhookEvent): Promise<void> {
    const maxAttempts = config.retryCount ?? this.retryCount
    
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const response = await fetch(config.url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Webhook-Secret': config.secret,
            'X-Webhook-Event': event.event,
            'X-Webhook-ID': event.id,
          },
          body: JSON.stringify(event),
        })

        if (response.ok) return
        if (response.status >= 400 && response.status < 500) return // Don't retry client errors
      } catch {
        // Network error, retry
      }

      event.attempts = attempt + 1
      if (attempt < maxAttempts - 1) {
        await new Promise(r => setTimeout(r, this.retryDelayMs * (attempt + 1)))
      }
    }
  }

  /** List registered webhooks */
  listWebhooks(): Array<{ id: string; config: WebhookConfig }> {
    return Array.from(this.webhooks.entries()).map(([id, config]) => ({ id, config }))
  }
}
