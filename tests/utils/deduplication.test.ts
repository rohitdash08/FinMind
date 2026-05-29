// PATCH: 此為 AI 生成的修復建議，請人工審查後合併
import { deduplicateTransactions } from '../../src/utils/deduplication';

const sampleExisting = [
  { date: '2023-01-01', amount: 29.99, description: 'Netflix subscription' },
  { date: '2023-01-02', amount: 50.00, description: 'Grocery store purchase' },
];

describe('deduplicateTransactions', () => {
  it('should flag exact duplicates', () => {
    const incoming = [
      { date: '2023-01-01', amount: 29.99, description: 'Netflix subscription' },
    ];
    const result = deduplicateTransactions(incoming, sampleExisting);
    expect(result.unique).toHaveLength(0);
    expect(result.duplicates).toHaveLength(1);
  });

  it('should flag similar transactions above threshold', () => {
    const incoming = [
      { date: '2023-01-01', amount: 30.00, description: 'Netflix monthly sub' },
    ];
    const result = deduplicateTransactions(incoming, sampleExisting, { threshold: 0.8 });
    expect(result.unique).toHaveLength(0);
    expect(result.duplicates).toHaveLength(1);
  });

  it('should keep distinct transactions', () => {
    const incoming = [
      { date: '2023-01-03', amount: 15.00, description: 'Coffee shop' },
    ];
    const result = deduplicateTransactions(incoming, sampleExisting);
    expect(result.unique).toHaveLength(1);
    expect(result.duplicates).toHaveLength(0);
  });

  it('should respect custom threshold', () => {
    const incoming = [
      { date: '2023-01-02', amount: 55.00, description: 'Grocery store' },
    ];
    const result = deduplicateTransactions(incoming, sampleExisting, { threshold: 0.95 });
    expect(result.unique).toHaveLength(1);
    expect(result.duplicates).toHaveLength(0);
  });

  it('should handle empty existing list', () => {
    const incoming = [
      { date: '2023-01-01', amount: 29.99, description: 'Netflix subscription' },
    ];
    const result = deduplicateTransactions(incoming, []);
    expect(result.unique).toHaveLength(1);
    expect(result.duplicates).toHaveLength(0);
  });
});
