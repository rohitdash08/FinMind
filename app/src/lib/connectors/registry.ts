// WHY: A central registry decouples connector instantiation from the rest of
// the application. New connectors (AA provider, SaltEdge, etc.) are added by
// calling ConnectorRegistry.register() — no switch-statements or imports
// scattered across the codebase.

import type { BankConnector, ConnectorCredentials } from './base';
import { MockBankConnector } from './mock';

/** Constructor signature every connector class must satisfy */
export type ConnectorConstructor = new (credentials?: ConnectorCredentials) => BankConnector;

/**
 * ConnectorRegistry — singleton factory for BankConnector instances.
 *
 * Usage:
 *   ConnectorRegistry.register('mock', MockBankConnector);
 *   const connector = ConnectorRegistry.getConnector('mock');
 *
 * WHY singleton pattern:
 *   - Guarantees one authoritative map of connector IDs across the app.
 *   - Prevents accidental re-registration that could silently overwrite a
 *     connector in production (we throw instead — fast failure is safer).
 */
export class ConnectorRegistry {
  // WHY private static map: hides internal state; only expose controlled API
  private static readonly _registry = new Map<string, ConnectorConstructor>();
  private static _initialised = false;

  /** Seed built-in connectors exactly once */
  private static _init(): void {
    if (ConnectorRegistry._initialised) return;
    ConnectorRegistry._initialised = true;
    // Mock connector is always registered as the default / fallback.
    // WHY: keeps the UI functional without live provider credentials during
    // development and CI runs.
    ConnectorRegistry._registry.set('mock', MockBankConnector);
  }

  /**
   * Register a connector class under a unique ID.
   * @throws {Error} if the ID is already registered — prevents silent overwrite.
   *
   * WHY throw rather than warn: silently replacing a production connector
   * (e.g., an AA provider) with a different implementation would be a
   * hard-to-debug data integrity issue.
   */
  static register(id: string, ConnectorClass: ConnectorConstructor): void {
    ConnectorRegistry._init();
    if (ConnectorRegistry._registry.has(id)) {
      throw new Error(
        `ConnectorRegistry: connector "${id}" is already registered. ` +
        'Use ConnectorRegistry.unregister() first if replacement is intentional.'
      );
    }
    ConnectorRegistry._registry.set(id, ConnectorClass);
  }

  /**
   * Explicit de-registration — required before re-registering the same ID.
   * WHY: makes intentional replacement visible in code review.
   */
  static unregister(id: string): void {
    ConnectorRegistry._init();
    ConnectorRegistry._registry.delete(id);
  }

  /**
   * Instantiate and return a connector by ID.
   * @param credentials  Optional credentials forwarded to the constructor.
   * @throws {Error} if no connector is registered for the given ID.
   *
   * WHY instantiate on every call rather than caching instances:
   *   - Avoids stale session tokens being reused across user sessions.
   *   - Each caller gets its own instance, preventing shared mutable state
   *     (important for concurrent refresh races — each caller holds its own
   *     cursor / mutex independently).
   */
  static getConnector(id: string, credentials?: ConnectorCredentials): BankConnector {
    ConnectorRegistry._init();
    const ConnectorClass = ConnectorRegistry._registry.get(id);
    if (!ConnectorClass) {
      const available = [...ConnectorRegistry._registry.keys()].join(', ');
      throw new Error(
        `ConnectorRegistry: no connector registered for "${id}". ` +
        `Available: [${available}]`
      );
    }
    return new ConnectorClass(credentials);
  }

  /** Returns a copy of all registered connector IDs — useful for UI pickers */
  static listConnectors(): string[] {
    ConnectorRegistry._init();
    return [...ConnectorRegistry._registry.keys()];
  }

  /**
   * Reset registry to initial state — intended for tests only.
   * WHY: allows each test to start clean without cross-test pollution.
   */
  static _resetForTesting(): void {
    ConnectorRegistry._registry.clear();
    ConnectorRegistry._initialised = false;
  }
}
