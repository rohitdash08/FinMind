import { describe, it, expect, vi } from 'vitest'
import { WebhookEventSystem } from '../event-system'

describe('WebhookEventSystem', () => {
  it('should emit events to local handlers', async () => {
    const system = new WebhookEventSystem()
    const handler = vi.fn()
    system.on('transaction.created', handler)
    
    await system.emit('transaction.created', { id: '123', amount: 100 })
    
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0][0].data).toEqual({ id: '123', amount: 100 })
  })

  it('should support unsubscribing', async () => {
    const system = new WebhookEventSystem()
    const handler = vi.fn()
    const unsub = system.on('transaction.created', handler)
    
    unsub()
    await system.emit('transaction.created', { id: '123' })
    
    expect(handler).not.toHaveBeenCalled()
  })

  it('should only trigger handlers for matching events', async () => {
    const system = new WebhookEventSystem()
    const handler1 = vi.fn()
    const handler2 = vi.fn()
    
    system.on('transaction.created', handler1)
    system.on('budget.exceeded', handler2)
    
    await system.emit('transaction.created', { id: '123' })
    
    expect(handler1).toHaveBeenCalledTimes(1)
    expect(handler2).not.toHaveBeenCalled()
  })

  it('should register and list webhooks', () => {
    const system = new WebhookEventSystem()
    system.registerWebhook('wh1', {
      url: 'https://example.com/webhook',
      secret: 'secret123',
      events: ['transaction.created'],
      active: true,
    })
    
    const webhooks = system.listWebhooks()
    expect(webhooks).toHaveLength(1)
    expect(webhooks[0].id).toBe('wh1')
  })

  it('should remove webhooks', () => {
    const system = new WebhookEventSystem()
    system.registerWebhook('wh1', {
      url: 'https://example.com',
      secret: 's',
      events: ['transaction.created'],
      active: true,
    })
    
    expect(system.removeWebhook('wh1')).toBe(true)
    expect(system.listWebhooks()).toHaveLength(0)
  })
})
