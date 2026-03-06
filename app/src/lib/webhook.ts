import { createHmac } from 'crypto';

interface WebhookEvent {
  id: string;
  type: string;
  payload: any;
  timestamp: string;
  signature: string;
}

interface WebhookConfig {
  url: string;
  secret: string;
  events: string[];
  retryAttempts?: number;
}

export class WebhookManager {
  private configs: Map<string, WebhookConfig> = new Map();
  private webhookSecret: string;

  constructor(secret: string) {
    this.webhookSecret = secret;
  }

  registerWebhook(id: string, config: WebhookConfig): void {
    this.configs.set(id, {
      ...config,
      retryAttempts: config.retryAttempts || 3
    });
  }

  private generateSignature(payload: string): string {
    return createHmac('sha256', this.webhookSecret)
      .update(payload)
      .digest('hex');
  }

  async emitEvent(eventType: string, data: any): Promise<void> {
    const event: WebhookEvent = {
      id: this.generateEventId(),
      type: eventType,
      payload: data,
      timestamp: new Date().toISOString(),
      signature: ''
    };

    const payload = JSON.stringify(event);
    event.signature = this.generateSignature(payload);

    for (const [id, config] of this.configs) {
      if (config.events.includes(eventType) || config.events.includes('*')) {
        await this.deliverWebhook(id, config, event);
      }
    }
  }

  private async deliverWebhook(
    id: string, 
    config: WebhookConfig, 
    event: WebhookEvent
  ): Promise<void> {
    let attempts = 0;
    const maxAttempts = config.retryAttempts || 3;

    while (attempts < maxAttempts) {
      try {
        const response = await fetch(config.url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': event.signature,
            'X-Webhook-Event': event.type,
            'X-Webhook-ID': event.id
          },
          body: JSON.stringify(event)
        });

        if (response.ok) {
          console.log(`Webhook delivered: ${event.type} -> ${config.url}`);
          return;
        }

        throw new Error(`HTTP ${response.status}`);
      } catch (error) {
        attempts++;
        console.warn(`Webhook attempt ${attempts} failed: ${error}`);
        
        if (attempts < maxAttempts) {
          await this.delay(Math.pow(2, attempts) * 1000);
        }
      }
    }

    console.error(`Webhook failed after ${maxAttempts} attempts: ${config.url}`);
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  private generateEventId(): string {
    return `evt_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  async emitExpenseCreated(expense: any): Promise<void> {
    await this.emitEvent('expense.created', expense);
  }

  async emitExpenseUpdated(expense: any): Promise<void> {
    await this.emitEvent('expense.updated', expense);
  }

  async emitExpenseDeleted(expenseId: string): Promise<void> {
    await this.emitEvent('expense.deleted', { id: expenseId });
  }
}

export const WebhookEventTypes = {
  EXPENSE_CREATED: 'expense.created',
  EXPENSE_UPDATED: 'expense.updated',
  EXPENSE_DELETED: 'expense.deleted',
  BUDGET_ALERT: 'budget.alert',
  REMINDER_TRIGGERED: 'reminder.triggered',
} as const;
