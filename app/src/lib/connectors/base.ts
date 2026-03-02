// WHY: Defines the canonical contract every bank connector must satisfy.
// Keeping it in one place means the registry, UI, and tests all import
// from a single source of truth — no drift between implementations.

export interface Transaction {
  /** Stable, provider-scoped unique ID — used for idempotent upserts */
  id: string;
  amount: number;          // positive = credit, negative = debit (INR paise or rupees, documented per connector)
  date: string;            // ISO-8601 date string, e.g. "2024-06-15"
  description: string;
  category?: string;
  currency: string;        // ISO-4217, default "INR" for Indian bank connectors
  accountId: string;       // provider-scoped account reference
  raw?: Record<string, unknown>; // preserve original payload for debugging
}

export interface ImportResult {
  transactions: Transaction[];
  /** Opaque cursor / lastSyncTime returned by provider; store and pass back on next call */
  nextCursor?: string;
  /** True when provider indicates there are more pages to fetch */
  hasMore: boolean;
}

export interface ConnectorCredentials {
  /** Arbitrary key-value bag — each connector documents its own required keys.
   *  WHY bag rather than union type: keeps base interface stable as new
   *  providers are added without touching shared types. */
  [key: string]: string | undefined;
}

/**
 * BankConnector — pluggable interface for every bank / AA-provider integration.
 *
 * Lifecycle:
 *   1. authenticate()           — exchange credentials for a session/token
 *   2. importTransactions()     — initial full or incremental fetch
 *   3. refreshSync()            — lightweight poll used by the sync scheduler
 *
 * WHY three separate methods instead of one:
 *   - authenticate() may involve OAuth / AA redirect flows that are async
 *     and user-visible; separating it avoids blocking background refreshes.
 *   - refreshSync() can be a no-op thin wrapper over importTransactions()
 *     for simple connectors, but AA connectors need to re-consent periodically.
 */
export interface BankConnector {
  /** Human-readable name shown in the UI */
  readonly name: string;
  /** Provider identifier, e.g. "aa", "saltedge", "mock" */
  readonly provider: string;

  /**
   * Authenticate with the provider using the supplied credentials.
   * Implementations should store session tokens internally (NOT in localStorage
   * — WHY: credential leakage risk; use in-memory or secure httpOnly cookie
   * via a backend proxy for real connectors).
   * @throws {ConnectorAuthError} on invalid credentials
   */
  authenticate(credentials: ConnectorCredentials): Promise<void>;

  /**
   * Fetch transactions from the provider.
   * @param cursor  Opaque pagination token from a previous ImportResult.
   *                Pass undefined for an initial / full import.
   * WHY cursor-based: prevents duplicate transactions on retry and supports
   * incremental sync without re-fetching the full history.
   */
  importTransactions(cursor?: string): Promise<ImportResult>;

  /**
   * Lightweight refresh — called by the background sync scheduler.
   * Default implementations can delegate to importTransactions(lastCursor),
   * but AA connectors may need to revalidate consent here.
   * WHY separate: decouples UI-triggered imports from scheduled background
   * refreshes so each can have independent retry/timeout policies.
   */
  refreshSync(lastCursor?: string): Promise<ImportResult>;
}

/** Typed error subclass so callers can distinguish auth failures from network errors */
export class ConnectorAuthError extends Error {
  constructor(public readonly provider: string, message: string) {
    super(`[${provider}] Auth failed: ${message}`);
    this.name = 'ConnectorAuthError';
  }
}

/** Typed error for provider API / network failures */
export class ConnectorSyncError extends Error {
  constructor(public readonly provider: string, message: string) {
    super(`[${provider}] Sync failed: ${message}`);
    this.name = 'ConnectorSyncError';
  }
}
