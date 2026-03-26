export interface Transaction {
  date: string;
  amount: number;
  description: string;
  category?: string;
}

export interface BankConnector {
  authenticate(credentials: Record<string, any>): Promise<boolean>;
  fetchTransactions(startDate: string, endDate: string): Promise<Transaction[]>;
  fetchBalance(): Promise<number>;
}

export class MockBankConnector implements BankConnector {
  private isAuthenticated = false;

  async authenticate(credentials: Record<string, any>): Promise<boolean> {
    if (credentials.username === 'test_user') {
      this.isAuthenticated = true;
      return true;
    }
    return false;
  }

  async fetchTransactions(startDate: string, endDate: string): Promise<Transaction[]> {
    if (!this.isAuthenticated) throw new Error('Not authenticated');
    return [
      { date: startDate, amount: -15.50, description: 'Coffee Shop', category: 'Food' },
      { date: startDate, amount: -100.00, description: 'Grocery Store', category: 'Groceries' },
      { date: endDate, amount: 2000.00, description: 'Payroll Deposit', category: 'Income' }
    ];
  }

  async fetchBalance(): Promise<number> {
    if (!this.isAuthenticated) throw new Error('Not authenticated');
    return 1884.50;
  }
}
