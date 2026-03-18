import { z } from 'zod';

// Types
export interface Transaction {
  id: string;
  description: string;
  amount: number;
  merchant?: string;
  date: Date;
  accountId: string;
}

export interface Category {
  id: string;
  name: string;
  parentId?: string;
  keywords: string[];
  merchantPatterns: string[];
}

export interface CategorizationResult {
  categoryId: string;
  confidence: number;
  method: 'rule' | 'ml' | 'manual' | 'fallback';
  reasons: string[];
}

export interface LearningData {
  transactionId: string;
  originalCategoryId: string;
  correctedCategoryId: string;
  description: string;
  merchant?: string;
  amount: number;
  timestamp: Date;
}

// Default categories with patterns
const DEFAULT_CATEGORIES: Category[] = [
  {
    id: 'groceries',
    name: 'Groceries',
    keywords: ['grocery', 'supermarket', 'food', 'produce'],
    merchantPatterns: ['walmart', 'kroger', 'safeway', 'whole foods', 'trader joe']
  },
  {
    id: 'dining',
    name: 'Dining & Restaurants',
    keywords: ['restaurant', 'cafe', 'coffee', 'pizza', 'burger'],
    merchantPatterns: ['mcdonalds', 'starbucks', 'subway', 'dominos']
  },
  {
    id: 'gas',
    name: 'Gas & Fuel',
    keywords: ['gas', 'fuel', 'station', 'petroleum'],
    merchantPatterns: ['shell', 'exxon', 'bp', 'chevron', 'mobil']
  },
  {
    id: 'utilities',
    name: 'Utilities',
    keywords: ['electric', 'water', 'gas bill', 'internet', 'cable'],
    merchantPatterns: ['pge', 'comcast', 'att', 'verizon']
  },
  {
    id: 'entertainment',
    name: 'Entertainment',
    keywords: ['movie', 'theater', 'netflix', 'spotify', 'gaming'],
    merchantPatterns: ['netflix', 'spotify', 'amazon prime', 'hulu']
  },
  {
    id: 'shopping',
    name: 'Shopping',
    keywords: ['store', 'retail', 'amazon', 'target'],
    merchantPatterns: ['amazon', 'target', 'costco', 'best buy']
  },
  {
    id: 'transport',
    name: 'Transportation',
    keywords: ['uber', 'lyft', 'taxi', 'bus', 'train'],
    merchantPatterns: ['uber', 'lyft', 'metro']
  },
  {
    id: 'healthcare',
    name: 'Healthcare',
    keywords: ['medical', 'doctor', 'pharmacy', 'hospital'],
    merchantPatterns: ['cvs', 'walgreens', 'kaiser']
  }
];

export class TransactionCategorizer {
  private categories: Map<string, Category>;
  private learningData: LearningData[];
  private mlWeights: Map<string, number>;

  constructor(customCategories?: Category[]) {
    this.categories = new Map();
    this.learningData = [];
    this.mlWeights = new Map();
    
    // Initialize with default categories
    const categories = customCategories || DEFAULT_CATEGORIES;
    categories.forEach(category => {
      this.categories.set(category.id, category);
    });
  }

  /**
   * Categorize a single transaction
   */
  categorize(transaction: Transaction): CategorizationResult {
    // Try ML-based categorization first
    const mlResult = this.categorizeMl(transaction);
    if (mlResult && mlResult.confidence > 0.7) {
      return mlResult;
    }

    // Fall back to rule-based categorization
    const ruleResult = this.categorizeRuleBased(transaction);
    if (ruleResult && ruleResult.confidence > 0.5) {
      return ruleResult;
    }

    // Return ML result if available, otherwise fallback
    if (mlResult && mlResult.confidence > 0.3) {
      return mlResult;
    }

    return this.getFallbackCategory(transaction);
  }

  /**
   * Rule-based categorization using keywords and patterns
   */
  private categorizeRuleBased(transaction: Transaction): CategorizationResult | null {
    const description = transaction.description.toLowerCase();
    const merchant = transaction.merchant?.toLowerCase() || '';
    
    let bestMatch: { category: Category; score: number; reasons: string[] } | null = null;

    for (const [categoryId, category] of this.categories) {
      let score = 0;
      const reasons: string[] = [];

      // Check merchant patterns
      for (const pattern of category.merchantPatterns) {
        if (merchant.includes(pattern.toLowerCase()) || description.includes(pattern.toLowerCase())) {
          score += 0.8;
          reasons.push(`Merchant pattern match: ${pattern}`);
        }
      }

      // Check keywords
      for (const keyword of category.keywords) {
        if (description.includes(keyword.toLowerCase())) {
          score += 0.6;
          reasons.push(`Keyword match: ${keyword}`);
        }
      }

      // Amount-based hints for specific categories
      if (categoryId === 'gas' && transaction.amount >= 20 && transaction.amount <= 100) {
        score += 0.2;
        reasons.push('Amount typical for gas purchase');
      }
      
      if (categoryId === 'groceries' && transaction.amount >= 20 && transaction.amount <= 300) {
        score += 0.1;
        reasons.push('Amount typical for grocery purchase');
      }

      if (score > 0 && (!bestMatch || score > bestMatch.score)) {
        bestMatch = { category, score, reasons };
      }
    }

    if (bestMatch && bestMatch.score > 0) {
      return {
        categoryId: bestMatch.category.id,
        confidence: Math.min(bestMatch.score, 1.0),
        method: 'rule',
        reasons: bestMatch.reasons
      };
    }

    return null;
  }

  /**
   * ML-based categorization using learned patterns
   */
  private categorizeMl(transaction: Transaction): CategorizationResult | null {
    if (this.learningData.length < 10) {
      return null; // Need minimum data for ML
    }

    const features = this.extractFeatures(transaction);
    const categoryScores = new Map<string, number>();

    // Calculate similarity scores based on learned data
    for (const learning of this.learningData) {
      const learningFeatures = this.extractFeaturesFromLearning(learning);
      const similarity = this.calculateSimilarity(features, learningFeatures);
      
      if (similarity > 0.3) {
        const currentScore = categoryScores.get(learning.correctedCategoryId) || 0;
        categoryScores.set(learning.correctedCategoryId, currentScore + similarity);
      }
    }

    if (categoryScores.size === 0) {
      return null;
    }

    // Find best category
    let bestCategoryId = '';
    let bestScore = 0;
    
    for (const [categoryId, score] of categoryScores) {
      if (score > bestScore) {
        bestScore = score;
        bestCategoryId = categoryId;
      }
    }

    // Normalize confidence score
    const totalScore = Array.from(categoryScores.values()).reduce((sum, score) => sum + score, 0);
    const confidence = bestScore / totalScore;

    return {
      categoryId: bestCategoryId,
      confidence: Math.min(confidence, 0.95),
      method: 'ml',
      reasons: [`ML prediction based on ${this.learningData.length} learned examples`]
    };
  }

  /**
   * Extract features from transaction for ML
   */
  private extractFeatures(transaction: Transaction): Map<string, number> {
    const features = new Map<string, number>();
    
    // Text features
    const words = transaction.description.toLowerCase().split(/\W+/);
    words.forEach(word => {
      if (word.length > 2) {
        features.set(`word_${word}`, (features.get(`word_${word}`) || 0) + 1);
      }
    });

    // Amount features
    features.set('amount', transaction.amount);
    features.set('amount_log', Math.log(Math.max(transaction.amount, 1)));
    
    // Time features
    const hour = transaction.date.getHours();
    const dayOfWeek = transaction.date.getDay();
    features.set('hour', hour);
    features.set('day_of_week', dayOfWeek);
    features.set('is_weekend', dayOfWeek === 0 || dayOfWeek === 6 ? 1 : 0);

    return features;
  }

  /**
   * Extract features from learning data
   */
  private extractFeaturesFromLearning(learning: LearningData): Map<string, number> {
    const features = new Map<string, number>();
    
    const words = learning.description.toLowerCase().split(/\W+/);
    words.forEach(word => {
      if (word.length > 2) {
        features.set(`word_${word}`, (features.get(`word_${word}`) || 0) + 1);
      }
    });

    features.set('amount', learning.amount);
    features.set('amount_log', Math.log(Math.max(learning.amount, 1)));

    return features;
  }

  /**
   * Calculate similarity between feature sets
   */
  private calculateSimilarity(features1: Map<string, number>, features2: Map<string, number>): number {
    const allKeys = new Set([...features1.keys(), ...features2.keys()]);
    let dotProduct = 0;
    let norm1 = 0;
    let norm2 = 0;

    for (const key of allKeys) {
      const val1 = features1.get(key) || 0;
      const val2 = features2.get(key) || 0;
      
      dotProduct += val1 * val2;
      norm1 += val1 * val1;
      norm2 += val2 * val2;
    }

    const magnitude = Math.sqrt(norm1) * Math.sqrt(norm2);
    return magnitude > 0 ? dotProduct / magnitude : 0;
  }

  /**
   * Get fallback category when no good match is found
   */
  private getFallbackCategory(transaction: Transaction): CategorizationResult {
    return {
      categoryId: 'other',
      confidence: 0.1,
      method: 'fallback',
      reasons: ['No matching patterns found']
    };
  }

  /**
   * Learn from user corrections
   */
  learnFromCorrection(
    transactionId: string,
    transaction: Transaction,
    originalCategoryId: string,
    correctedCategoryId: string
  ): void {
    const learningData: LearningData = {
      transactionId,
      originalCategoryId,
      correctedCategoryId,
      description: transaction.description,
      merchant: transaction.merchant,
      amount: transaction.amount,
      timestamp: new Date()
    };

    this.learningData.push(learningData);

    // Keep only recent learning data (last 1000 corrections)
    if (this.learningData.length > 1000) {
      this.learningData = this.learningData.slice(-1000);
    }

    // Update ML weights
    this.updateMlWeights();
  }

  /**
   * Update ML weights based on learning data
   */
  private updateMlWeights(): void {
    // Simple frequency-based weighting
    const categoryFrequency = new Map<string, number>();
    
    for (const learning of this.learningData) {
      const count = categoryFrequency.get(learning.correctedCategoryId) || 0;
      categoryFrequency.set(learning.correctedCategoryId, count + 1);
    }

    const total = this.learningData.length;
    for (const [categoryId, count] of categoryFrequency) {
      this.mlWeights.set(categoryId, count / total);
    }
  }

  /**
   * Bulk categorize multiple transactions
   */
  categorizeMultiple(transactions: Transaction[]): Map<string, CategorizationResult> {
    const results = new Map<string, CategorizationResult>();
    
    for (const transaction of transactions) {
      results.set(transaction.id, this.categorize(transaction));
    }
    
    return results;
  }

  /**
   * Add or update a category
   */
  addCategory(category: Category): void {
    this.categories.set(category.id, category);
  }

  /**
   * Get all categories
   */
  getCategories(): Category[] {
    return Array.from(this.categories.values());
  }

  /**
   * Get learning statistics
   */
  getLearningStats(): {
    totalCorrections: number;
    categoryDistribution: Record<string, number>;
    confidenceDistribution: Record<string, number>;
  } {
    const categoryDistribution: Record<string, number> = {};
    
    for (const learning of this.learningData) {
      categoryDistribution[learning.correctedCategoryId] = 
        (categoryDistribution[learning.correctedCategoryId] || 0) + 1;
    }

    return {
      totalCorrections: this.learningData.length,
      categoryDistribution,
      confidenceDistribution: {
        'high (>0.8)': 0,
        'medium (0.5-0.8)': 0,
        'low (<0.5)': 0
      }
    };
  }
}

// Export default instance
export const transactionCategorizer = new TransactionCategorizer();