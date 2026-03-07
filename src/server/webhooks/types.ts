export enum WebhookEvent {
  TRANSACTION_CREATED = 'transaction.created',
  TRANSACTION_UPDATED = 'transaction.updated',
  ACCOUNT_CONNECTED = 'account.connected',
  BUDGET_EXCEEDED = 'budget.exceeded',
  SUBSCRIPTION_DETECTED = 'subscription.detected',
}

export interface WebhookPayload {
  id: string;
  event: WebhookEvent;
  data: any;
  timestamp: string;
}
