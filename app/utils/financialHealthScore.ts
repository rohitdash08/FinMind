export interface FinancialMetrics {
  totalIncome: number;
  totalExpenses: number;
  savingsAmount: number;
  billsAmount: number;
  monthlyData: Array<{
    month: string;
    income: number;
    expenses: number;
    savings: number;
  }>;
}

export interface HealthScoreComponents {
  savingsStrength: number;
  spendingStability: number;
  billReliability: number;
  trendDirection: number;
  overallScore: number;
}

export class FinancialHealthCalculator {
  private metrics: FinancialMetrics;

  constructor(metrics: FinancialMetrics) {
    this.metrics = metrics;
  }

  calculateSavingsStrength(): number {
    const { totalIncome, savingsAmount } = this.metrics;
    
    if (totalIncome === 0) return 0;
    
    const savingsRate = (savingsAmount / totalIncome) * 100;
    
    // Score based on savings rate benchmarks
    if (savingsRate >= 20) return 100;
    if (savingsRate >= 15) return 85;
    if (savingsRate >= 10) return 70;
    if (savingsRate >= 5) return 50;
    if (savingsRate > 0) return 25;
    
    return 0;
  }

  calculateSpendingStability(): number {
    const { monthlyData } = this.metrics;
    
    if (monthlyData.length < 2) return 50; // Default for insufficient data
    
    // Calculate coefficient of variation for expenses
    const expenses = monthlyData.map(data => data.expenses);
    const mean = expenses.reduce((sum, exp) => sum + exp, 0) / expenses.length;
    
    if (mean === 0) return 100; // No expenses is perfectly stable
    
    const variance = expenses.reduce((sum, exp) => sum + Math.pow(exp - mean, 2), 0) / expenses.length;
    const standardDeviation = Math.sqrt(variance);
    const coefficientOfVariation = standardDeviation / mean;
    
    // Lower coefficient of variation = higher stability
    // Score inversely related to CV
    const stabilityScore = Math.max(0, 100 - (coefficientOfVariation * 100));
    
    return Math.min(100, stabilityScore);
  }

  calculateBillReliability(): number {
    const { totalIncome, billsAmount } = this.metrics;
    
    if (totalIncome === 0) return 0;
    
    const billToIncomeRatio = billsAmount / totalIncome;
    
    // Ideal bill ratio is 30-50% of income
    if (billToIncomeRatio <= 0.3) return 100;
    if (billToIncomeRatio <= 0.4) return 85;
    if (billToIncomeRatio <= 0.5) return 70;
    if (billToIncomeRatio <= 0.6) return 50;
    if (billToIncomeRatio <= 0.7) return 30;
    
    return 10; // Bills are too high relative to income
  }

  calculateTrendDirection(): number {
    const { monthlyData } = this.metrics;
    
    if (monthlyData.length < 3) return 50; // Default for insufficient data
    
    // Calculate trend for savings over time
    const savingsTrend = this.calculateLinearTrend(monthlyData.map(data => data.savings));
    
    // Calculate trend for net income (income - expenses)
    const netIncomeTrend = this.calculateLinearTrend(
      monthlyData.map(data => data.income - data.expenses)
    );
    
    // Combine both trends (weighted)
    const combinedTrend = (savingsTrend * 0.6) + (netIncomeTrend * 0.4);
    
    // Convert trend to score (0-100)
    // Positive trends get higher scores
    if (combinedTrend > 100) return 100;
    if (combinedTrend > 50) return 85;
    if (combinedTrend > 0) return 70;
    if (combinedTrend > -50) return 40;
    if (combinedTrend > -100) return 20;
    
    return 10;
  }

  private calculateLinearTrend(values: number[]): number {
    const n = values.length;
    if (n < 2) return 0;
    
    // Simple linear regression slope
    const xValues = Array.from({ length: n }, (_, i) => i);
    const xMean = (n - 1) / 2;
    const yMean = values.reduce((sum, val) => sum + val, 0) / n;
    
    const numerator = xValues.reduce((sum, x, i) => sum + (x - xMean) * (values[i] - yMean), 0);
    const denominator = xValues.reduce((sum, x) => sum + Math.pow(x - xMean, 2), 0);
    
    if (denominator === 0) return 0;
    
    const slope = numerator / denominator;
    
    // Normalize slope to a trend score
    return slope * 10; // Adjust multiplier based on typical data scale
  }

  calculateOverallScore(): HealthScoreComponents {
    const savingsStrength = this.calculateSavingsStrength();
    const spendingStability = this.calculateSpendingStability();
    const billReliability = this.calculateBillReliability();
    const trendDirection = this.calculateTrendDirection();
    
    // Weighted average for overall score
    const overallScore = Math.round(
      (savingsStrength * 0.3) +
      (spendingStability * 0.25) +
      (billReliability * 0.25) +
      (trendDirection * 0.2)
    );
    
    return {
      savingsStrength: Math.round(savingsStrength),
      spendingStability: Math.round(spendingStability),
      billReliability: Math.round(billReliability),
      trendDirection: Math.round(trendDirection),
      overallScore
    };
  }

  getScoreInterpretation(score: number): string {
    if (score >= 90) return 'Excellent';
    if (score >= 80) return 'Very Good';
    if (score >= 70) return 'Good';
    if (score >= 60) return 'Fair';
    if (score >= 50) return 'Needs Improvement';
    return 'Poor';
  }

  getRecommendations(components: HealthScoreComponents): string[] {
    const recommendations: string[] = [];
    
    if (components.savingsStrength < 70) {
      recommendations.push('Increase your savings rate to at least 10-15% of income');
    }
    
    if (components.spendingStability < 70) {
      recommendations.push('Work on stabilizing your monthly expenses through budgeting');
    }
    
    if (components.billReliability < 70) {
      recommendations.push('Consider reducing fixed expenses or increasing income to improve bill-to-income ratio');
    }
    
    if (components.trendDirection < 70) {
      recommendations.push('Focus on improving your financial trajectory through better money management');
    }
    
    if (recommendations.length === 0) {
      recommendations.push('Great job! Continue maintaining your healthy financial habits');
    }
    
    return recommendations;
  }
}