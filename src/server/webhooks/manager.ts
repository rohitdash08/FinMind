import crypto from 'crypto';
import axios from 'axios';
import { WebhookEvent, WebhookPayload } from './types';

export class WebhookManager {
  private readonly secret: string;

  constructor(secret: string) {
    this.secret = secret;
  }

  private signPayload(payload: string): string {
    return crypto
      .createHmac('sha256', this.secret)
      .update(payload)
      .digest('hex');
  }

  async emit(
    url: string,
    event: WebhookEvent,
    data: any,
    retries = 3
  ): Promise<boolean> {
    const payload: WebhookPayload = {
      id: crypto.randomUUID(),
      event,
      data,
      timestamp: new Date().toISOString(),
    };

    const body = JSON.stringify(payload);
    const signature = this.signPayload(body);

    for (let i = 0; i <= retries; i++) {
      try {
        await axios.post(url, body, {
          headers: {
            'Content-Type': 'application/json',
            'X-FinMind-Signature': signature,
            'X-FinMind-Event': event,
            'User-Agent': 'FinMind-Webhook-System/1.0',
          },
          timeout: 5000,
        });
        return true;
      } catch (error: any) {
        if (i === retries) return false;
        const delay = Math.pow(2, i) * 1000;
        await new Promise((res) => setTimeout(res, delay));
      }
    }
    return false;
  }
}
