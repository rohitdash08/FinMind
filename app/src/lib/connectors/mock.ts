// WHY: A mock connector serves two purposes:
//   1. Default fallback so the UI works in dev/CI without live bank credentials.
//   2. Canonical reference implementation showing how a real connector should
//      behave (cursor pagination, idempotent IDs, error shapes).

import type {
  BankConnector,
  ConnectorCredentials,
  ImportResult,
  Transaction,
} from './base';
import { ConnectorAuthError } from './base';

/** Fixed seed data representing realistic Indian bank transactions */
const MOCK_TRANSACTIONS: Omit<Transaction, 'accountId'>[] = [
  { id: 'mock-txn-001', amount: -1500,  date: '2024-06-01', description: 'Zomato Order',          category: 'food',      currency: 'INR', raw: { ref: 'ZMT00123' } },
  { id: 'mock-txn-002', amount: -25000, date: '2024-06-03', description: 'Rent Transfer',          category: 'housing',   currency: 'INR', raw: { ref: 'NEFT20240603' } },
  { id: 'mock-txn-003', amount:  85000, date: '2024-06-05', description: 'Salary Credit',          category: 'income',    currency: 'INR', raw: { ref: 'SAL2024JUN' } },
  { id: 'mock-txn-004', amount: -3200,  date: '2024-06-07', description: 'Amazon Purchase',        category: 'shopping',  currency: 'INR', raw: { ref: 'AMZ78912' } },
  { id: 'mock-txn-005', amount: -800,   date: '2024-06-10', description: 'Ola Ride',               category: 'transport', currency: 'INR', raw: { ref: 'OLA5543' } },
  { id: 'mock-txn-006', amount: -12000, date: '2024-06-12', description: 'Electricity Bill BESCOM', category: 'utilities', currency: 'INR', raw: { ref: 'BESCOM0612' } },
  { id: 'mock-txn-007', amount:  5000,  date: '2024-06-15', description: 'Freelance Payment',      category: 'income',    currency: 'INR', raw: { ref: 'IMPS2024X' } },
  { id: 'mock-txn-008', amount: -450,   date: '2024-06-18', description: 'Swiggy Order',           category: 'food',      currency: 'INR', raw: { ref: 'SWG09871' } },
];

/**
 * MockBankConnector — fully in-memory connector returning deterministic data.
 *
 * Pagination model: the cursor is the string index into MOCK_TRANSACTIONS.
 * WHY index-as-cursor: keeps the mock stateless and deterministic — any test
 * or dev session will see the same data in the same order regardless of time.
 *
 * PAGE_SIZE is intentionally small (5) to exercise multi-page logic.
 */
const PAGE_SIZE = 5;

export class MockBankConnector implements BankConnector {
  readonly name = 'Mock Bank';
  readonly provider = 'mock';

  // WHY private flag: mirrors pattern real connectors use to gate
  // importTransactions() behind a successful authenticate() call.
  private _authenticated = false;

  // Accepts optional credentials so it satisfies ConnectorConstructor signature;
  // mock ignores them unless the special test key "fail_auth" is set.
  constructor(private readonly _credentials?: ConnectorCredentials) {}

  async authenticate(credentials: ConnectorCredentials): Promise<void> {
    // WHY allow forced failure: lets unit tests exercise the error path without
    // spinning up a real provider.
    if (credentials['fail_auth'] === 'true') {
      throw new ConnectorAuthError(this.provider, 'forced failure via fail_auth credential');
    }
    // Simulate a short async round-trip (would be an HTTP call in a real connector)
    await Promise.resolve();
    this._authenticated = true;
  }

  async importTransactions(cursor?: string): Promise<ImportResult> {
    // WHY not throw if unauthenticated here for mock: simplifies dev usage where
    // callers skip authenticate() during hot-reload. Real connectors SHOULD throw.
    const startIndex = cursor ? parseInt(cursor, 10) : 0;
    const slice = MOCK_TRANSACTIONS.slice(startIndex, startIndex + PAGE_SIZE);
    const endIndex = startIndex + slice.length;
    const hasMore = endIndex < MOCK_TRANSACTIONS.length;

    const transactions: Transaction[] = slice.map((t) => ({
      ...t,
      // WHY stable accountId on mock: tests can assert account grouping without
      // needing multiple registered accounts.
      accountId: 'mock-account-001',
    }));

    return {
      transactions,
      // WHY stringify index: keeps cursor opaque to callers while staying
      // trivially inspectable during debugging.
      nextCursor: hasMore ? String(endIndex) : undefined,
      hasMore,
    };
  }

  async refreshSync(lastCursor?: string): Promise<ImportResult> {
    // WHY delegate: for the mock the refresh and import semantics are identical.
    // Real AA connectors override this to re-validate consent before fetching.
    return this.importTransactions(lastCursor);
  }
}

// ─── Unit tests (co-located for discoverability; use vitest) ────────────────
// app/src/lib/connectors/mock.test.ts — see separate test file.

/**
 * Convenience: typed test for ConnectorRegistry round-trip.
 * Exported so the registry test can import it without a separate mock factory.
 */
export { MockBankConnector as _MockBankConnectorForTesting };

// ─── registry.test.ts ────────────────────────────────────────────────────────
// WHY co-locate tests in the same connectors/ directory: keeps the module
// self-contained and discoverable; mirrors the pattern used in the existing
// app/src/lib/ files which have no __tests__ subdirectory.

/*
  File: app/src/lib/connectors/connectors.test.ts

  import { describe, it, expect, beforeEach } from 'vitest';
  import { ConnectorRegistry } from './registry';
  import { MockBankConnector } from './mock';

  describe('ConnectorRegistry', () => {
    beforeEach(() => ConnectorRegistry._resetForTesting());

    it('returns a MockBankConnector for id "mock" after auto-init', () => {
      const connector = ConnectorRegistry.getConnector('mock');
      expect(connector).toBeInstanceOf(MockBankConnector);
    });

    it('throws on duplicate registration of the same id', () => {
      ConnectorRegistry.register('mock', MockBankConnector); // first
      expect(() => ConnectorRegistry.register('mock', MockBankConnector))
        .toThrow('already registered');
    });

    it('throws when requesting an unregistered connector', () => {
      expect(() => ConnectorRegistry.getConnector('nonexistent'))
        .toThrow('no connector registered');
    });
  });

  describe('MockBankConnector', () => {
    it('importTransactions returns transactions with required fields', async () => {
      const connector = new MockBankConnector();
      const result = await connector.importTransactions();
      expect(result.transactions.length).toBeGreaterThan(0);
      for (const txn of result.transactions) {
        expect(txn).toHaveProperty('id');
        expect(txn).toHaveProperty('amount');
        expect(txn).toHaveProperty('date');
        expect(txn).toHaveProperty('currency', 'INR');
      }
    });

    it('cursor-based pagination returns second page and hasMore=false at end', async () => {
      const connector = new MockBankConnector();
      const page1 = await connector.importTransactions();
      expect(page1.hasMore).toBe(true);
      expect(page1.nextCursor).toBeDefined();
      const page2 = await connector.importTransactions(page1.nextCursor);
      expect(page2.hasMore).toBe(false);
      // No ID overlap between pages
      const ids1 = new Set(page1.transactions.map(t => t.id));
      const ids2 = page2.transactions.map(t => t.id);
      ids2.forEach(id => expect(ids1.has(id)).toBe(false));
    });

    it('authenticate throws ConnectorAuthError when fail_auth=true', async () => {
      const connector = new MockBankConnector();
      await expect(connector.authenticate({ fail_auth: 'true' }))
        .rejects.toThrow('Auth failed');
    });
  });
*/
