import crypto from 'crypto';

export interface WebhookEvent {
  id: string;
  type: string;
  payload: Record<string, any>;
  timestamp: string;
}

export interface WebhookConfig {
  endpoint: string;
  secret: string;
  eventTypes: string[];
}

export class WebhookService {
  constructor(private configs: WebhookConfig[]) {}

  /**
   * Generates a signature for the webhook payload
   */
  generateSignature(payload: string, secret: string): string {
    return crypto.createHmac('sha256', secret).update(payload).digest('hex');
  }

  /**
   * Emits an event to all subscribed endpoints with retry logic
   */
  async emit(event: WebhookEvent): Promise<void> {
    const payloadString = JSON.stringify(event);
    
    for (const config of this.configs) {
      if (config.eventTypes.includes('*') || config.eventTypes.includes(event.type)) {
        await this.sendWithRetry(config.endpoint, payloadString, config.secret);
      }
    }
  }

  private async sendWithRetry(endpoint: string, payload: string, secret: string, retries = 3): Promise<void> {
    const signature = this.generateSignature(payload, secret);
    
    for (let attempt = 1; attempt <= retries; attempt++) {
      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature,
          },
          body: payload,
        });

        if (response.ok) {
          return; // Success
        }
      } catch (error) {
        if (attempt === retries) {
          console.error(`Failed to deliver webhook to ${endpoint} after ${retries} attempts`, error);
          throw error;
        }
      }
      // Exponential backoff
      await new Promise(res => setTimeout(res, Math.pow(2, attempt) * 1000));
    }
  }
}
