import { TransactionCategorizer } from '../transaction-categorizer';
import { Transaction, CategoryRule, Category } from '../types/transaction.types';

describe('TransactionCategorizer', () => {
  let categorizer: TransactionCategorizer;
  
  const mockTransactions: Transaction[] = [
    {
      id: '1',
      description: 'STARBUCKS COFFEE #123',
      amount: -4.50,
      date: new Date('2023-01-15'),
      category: Category.DINING,
      confidence: 0.95
    },
    {
      id: '2',
      description: 'SHELL GAS STATION',
      amount: -45.00,
      date: new Date('2023-01-16'),
      category: Category.TRANSPORTATION,
      confidence: 0.90
    },
    {
      id: '3',
      description: 'WHOLE FOODS MARKET',
      amount: -87.50,
      date: new Date('2023-01-17'),
      category: Category.GROCERIES,
      confidence: 0.88
    },
    {
      id: '4',
      description: 'ELECTRIC COMPANY BILL',
      amount: -125.00,
      date: new Date('2023-01-18'),
      category: Category.UTILITIES,
      confidence: 0.92
    }
  ];

  const mockRules: CategoryRule[] = [
    {
      id: 'rule-1',
      category: Category.DINING,
      patterns: ['STARBUCKS', 'RESTAURANT', 'CAFE'],
      weight: 1.0,
      isUserDefined: false
    },
    {
      id: 'rule-2',
      category: Category.TRANSPORTATION,
      patterns: ['GAS', 'SHELL', 'EXXON', 'UBER'],
      weight: 0.9,
      isUserDefined: false
    },
    {
      id: 'rule-3',
      category: Category.GROCERIES,
      patterns: ['WHOLE FOODS', 'KROGER', 'WALMART'],
      weight: 0.85,
      isUserDefined: false
    }
  ];

  beforeEach(() => {
    categorizer = new TransactionCategorizer();
    mockRules.forEach(rule => categorizer.addRule(rule));
    mockTransactions.forEach(transaction => categorizer.learn(transaction));
  });

  describe('Rule Matching', () => {
    it('should match transactions based on exact pattern matches', () => {
      const transaction = {
        id: 'test-1',
        description: 'STARBUCKS DOWNTOWN',
        amount: -5.25,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).toBe(Category.DINING);
      expect(result.confidence).toBeGreaterThan(0.8);
    });

    it('should match transactions based on partial pattern matches', () => {
      const transaction = {
        id: 'test-2',
        description: 'LOCAL RESTAURANT & BAR',
        amount: -32.50,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).toBe(Category.DINING);
    });

    it('should handle case-insensitive pattern matching', () => {
      const transaction = {
        id: 'test-3',
        description: 'shell gas station downtown',
        amount: -40.00,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).toBe(Category.TRANSPORTATION);
    });

    it('should return UNCATEGORIZED when no patterns match', () => {
      const transaction = {
        id: 'test-4',
        description: 'UNKNOWN MERCHANT XYZ',
        amount: -15.00,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).toBe(Category.UNCATEGORIZED);
      expect(result.confidence).toBeLessThan(0.5);
    });

    it('should prioritize user-defined rules over system rules', () => {
      const userRule: CategoryRule = {
        id: 'user-rule-1',
        category: Category.ENTERTAINMENT,
        patterns: ['STARBUCKS'],
        weight: 1.0,
        isUserDefined: true
      };

      categorizer.addRule(userRule);

      const transaction = {
        id: 'test-5',
        description: 'STARBUCKS COFFEE',
        amount: -4.75,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).toBe(Category.ENTERTAINMENT);
    });
  });

  describe('Learning and Adaptation', () => {
    it('should learn from user corrections', () => {
      const transaction = {
        id: 'learn-1',
        description: 'NEW COFFEE SHOP',
        amount: -6.00,
        date: new Date(),
        category: Category.DINING,
        confidence: 1.0
      };

      categorizer.learn(transaction);

      const similarTransaction = {
        id: 'learn-2',
        description: 'NEW COFFEE SHOP BRANCH',
        amount: -5.50,
        date: new Date()
      };

      const result = categorizer.categorize(similarTransaction);
      expect(result.category).toBe(Category.DINING);
      expect(result.confidence).toBeGreaterThan(0.7);
    });

    it('should improve confidence with repeated patterns', () => {
      const transactions = [
        {
          id: 'repeat-1',
          description: 'ACME HARDWARE STORE',
          amount: -25.00,
          date: new Date(),
          category: Category.SHOPPING,
          confidence: 1.0
        },
        {
          id: 'repeat-2',
          description: 'ACME HARDWARE STORE',
          amount: -30.00,
          date: new Date(),
          category: Category.SHOPPING,
          confidence: 1.0
        },
        {
          id: 'repeat-3',
          description: 'ACME HARDWARE STORE',
          amount: -15.00,
          date: new Date(),
          category: Category.SHOPPING,
          confidence: 1.0
        }
      ];

      transactions.forEach(t => categorizer.learn(t));

      const testTransaction = {
        id: 'test-repeat',
        description: 'ACME HARDWARE STORE',
        amount: -20.00,
        date: new Date()
      };

      const result = categorizer.categorize(testTransaction);
      expect(result.category).toBe(Category.SHOPPING);
      expect(result.confidence).toBeGreaterThan(0.9);
    });

    it('should handle conflicting categorizations by using most recent', () => {
      const transaction1 = {
        id: 'conflict-1',
        description: 'AMBIGUOUS MERCHANT',
        amount: -20.00,
        date: new Date('2023-01-01'),
        category: Category.SHOPPING,
        confidence: 1.0
      };

      const transaction2 = {
        id: 'conflict-2',
        description: 'AMBIGUOUS MERCHANT',
        amount: -25.00,
        date: new Date('2023-01-15'),
        category: Category.DINING,
        confidence: 1.0
      };

      categorizer.learn(transaction1);
      categorizer.learn(transaction2);

      const testTransaction = {
        id: 'conflict-test',
        description: 'AMBIGUOUS MERCHANT',
        amount: -22.00,
        date: new Date()
      };

      const result = categorizer.categorize(testTransaction);
      expect(result.category).toBe(Category.DINING);
    });
  });

  describe('Confidence Scoring', () => {
    it('should return high confidence for exact matches', () => {
      const transaction = {
        id: 'conf-1',
        description: 'SHELL GAS STATION',
        amount: -40.00,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.confidence).toBeGreaterThan(0.85);
    });

    it('should return medium confidence for partial matches', () => {
      const transaction = {
        id: 'conf-2',
        description: 'UNKNOWN GAS STATION',
        amount: -35.00,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.confidence).toBeLessThan(0.85);
      expect(result.confidence).toBeGreaterThan(0.5);
    });

    it('should return low confidence when no clear patterns match', () => {
      const transaction = {
        id: 'conf-3',
        description: 'RANDOM MERCHANT 123',
        amount: -50.00,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.confidence).toBeLessThan(0.5);
    });

    it('should increase confidence based on frequency of pattern', () => {
      // Learn multiple times from similar transactions
      for (let i = 0; i < 5; i++) {
        categorizer.learn({
          id: `freq-${i}`,
          description: 'FREQUENCY TEST MERCHANT',
          amount: -10.00,
          date: new Date(),
          category: Category.SHOPPING,
          confidence: 1.0
        });
      }

      const testTransaction = {
        id: 'freq-test',
        description: 'FREQUENCY TEST MERCHANT',
        amount: -12.00,
        date: new Date()
      };

      const result = categorizer.categorize(testTransaction);
      expect(result.confidence).toBeGreaterThan(0.9);
    });

    it('should consider amount ranges for confidence scoring', () => {
      // Learn from transactions with specific amount patterns
      categorizer.learn({
        id: 'amount-1',
        description: 'MONTHLY SUBSCRIPTION',
        amount: -9.99,
        date: new Date(),
        category: Category.ENTERTAINMENT,
        confidence: 1.0
      });

      const similarAmountTransaction = {
        id: 'amount-test-1',
        description: 'MONTHLY SUBSCRIPTION',
        amount: -9.99,
        date: new Date()
      };

      const differentAmountTransaction = {
        id: 'amount-test-2',
        description: 'MONTHLY SUBSCRIPTION',
        amount: -199.99,
        date: new Date()
      };

      const result1 = categorizer.categorize(similarAmountTransaction);
      const result2 = categorizer.categorize(differentAmountTransaction);

      expect(result1.confidence).toBeGreaterThan(result2.confidence);
    });
  });

  describe('Rule Management', () => {
    it('should add new rules successfully', () => {
      const newRule: CategoryRule = {
        id: 'new-rule',
        category: Category.HEALTH,
        patterns: ['PHARMACY', 'HOSPITAL'],
        weight: 0.9,
        isUserDefined: true
      };

      categorizer.addRule(newRule);

      const transaction = {
        id: 'rule-test',
        description: 'LOCAL PHARMACY',
        amount: -15.00,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).toBe(Category.HEALTH);
    });

    it('should remove rules successfully', () => {
      const ruleToRemove = mockRules[0];
      categorizer.removeRule(ruleToRemove.id);

      const transaction = {
        id: 'remove-test',
        description: 'STARBUCKS COFFEE',
        amount: -4.50,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).not.toBe(Category.DINING);
    });

    it('should update existing rules', () => {
      const updatedRule: CategoryRule = {
        id: 'rule-1',
        category: Category.ENTERTAINMENT,
        patterns: ['STARBUCKS', 'COFFEE'],
        weight: 1.0,
        isUserDefined: true
      };

      categorizer.updateRule(updatedRule);

      const transaction = {
        id: 'update-test',
        description: 'STARBUCKS DOWNTOWN',
        amount: -5.00,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).toBe(Category.ENTERTAINMENT);
    });
  });

  describe('Bulk Operations', () => {
    it('should categorize multiple transactions efficiently', () => {
      const transactions = [
        {
          id: 'bulk-1',
          description: 'STARBUCKS #1',
          amount: -4.50,
          date: new Date()
        },
        {
          id: 'bulk-2',
          description: 'SHELL GAS',
          amount: -40.00,
          date: new Date()
        },
        {
          id: 'bulk-3',
          description: 'WHOLE FOODS',
          amount: -85.00,
          date: new Date()
        }
      ];

      const results = categorizer.categorizeMany(transactions);

      expect(results).toHaveLength(3);
      expect(results[0].category).toBe(Category.DINING);
      expect(results[1].category).toBe(Category.TRANSPORTATION);
      expect(results[2].category).toBe(Category.GROCERIES);
    });

    it('should maintain performance with large datasets', () => {
      const largeTransactionSet = Array.from({ length: 1000 }, (_, i) => ({
        id: `perf-${i}`,
        description: i % 2 === 0 ? 'STARBUCKS COFFEE' : 'SHELL GAS STATION',
        amount: -Math.random() * 100,
        date: new Date()
      }));

      const startTime = Date.now();
      const results = categorizer.categorizeMany(largeTransactionSet);
      const endTime = Date.now();

      expect(results).toHaveLength(1000);
      expect(endTime - startTime).toBeLessThan(1000); // Should complete within 1 second
    });
  });

  describe('Export and Import', () => {
    it('should export learned patterns', () => {
      const exportedData = categorizer.exportLearning();
      
      expect(exportedData).toHaveProperty('rules');
      expect(exportedData).toHaveProperty('patterns');
      expect(exportedData.rules).toBeInstanceOf(Array);
    });

    it('should import learned patterns', () => {
      const exportedData = categorizer.exportLearning();
      const newCategorizer = new TransactionCategorizer();
      
      newCategorizer.importLearning(exportedData);

      const testTransaction = {
        id: 'import-test',
        description: 'STARBUCKS COFFEE',
        amount: -4.50,
        date: new Date()
      };

      const result = newCategorizer.categorize(testTransaction);
      expect(result.category).toBe(Category.DINING);
    });
  });

  describe('Error Handling', () => {
    it('should handle invalid transaction data gracefully', () => {
      const invalidTransaction = {
        id: '',
        description: '',
        amount: 0,
        date: new Date()
      };

      expect(() => {
        categorizer.categorize(invalidTransaction);
      }).not.toThrow();
    });

    it('should handle null or undefined descriptions', () => {
      const transaction = {
        id: 'null-test',
        description: null as any,
        amount: -10.00,
        date: new Date()
      };

      const result = categorizer.categorize(transaction);
      expect(result.category).toBe(Category.UNCATEGORIZED);
    });

    it('should handle duplicate rule IDs', () => {
      const duplicateRule: CategoryRule = {
        id: 'rule-1', // Same ID as existing rule
        category: Category.HEALTH,
        patterns: ['DUPLICATE'],
        weight: 1.0,
        isUserDefined: true
      };

      expect(() => {
        categorizer.addRule(duplicateRule);
      }).not.toThrow();
    });
  });
});