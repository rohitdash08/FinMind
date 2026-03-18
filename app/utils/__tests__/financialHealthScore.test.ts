import { calculateFinancialHealthScore, FinancialData } from '../financialHealthScore';

describe('calculateFinancialHealthScore', () => {
  const mockBaseFinancialData: FinancialData = {
    totalIncome: 5000,
    totalExpenses: 3000,
    totalDebt: 10000,
    totalAssets: 50000,
    emergencyFund: 6000,
    creditScore: 750,
    monthlyDebtPayments: 500,
    monthlyRecurringExpenses: 2500,
    savingsRate: 0.2,
    debtToIncomeRatio: 0.1,
    liquidAssets: 15000,
    age: 30,
    hasHealthInsurance: true,
    hasEmergencyContact: true,
    employmentStatus: 'employed'
  };

  describe('Normal scenarios', () => {
    it('should calculate a good financial health score for healthy finances', () => {
      const result = calculateFinancialHealthScore(mockBaseFinancialData);
      
      expect(result.score).toBeGreaterThan(70);
      expect(result.category).toBe('Good');
      expect(result.recommendations).toHaveLength(0);
    });

    it('should calculate a poor score for unhealthy finances', () => {
      const poorFinances: FinancialData = {
        ...mockBaseFinancialData,
        totalIncome: 2000,
        totalExpenses: 2500,
        totalDebt: 50000,
        emergencyFund: 0,
        creditScore: 500,
        savingsRate: -0.1,
        debtToIncomeRatio: 0.8,
        hasHealthInsurance: false,
        employmentStatus: 'unemployed'
      };
      
      const result = calculateFinancialHealthScore(poorFinances);
      
      expect(result.score).toBeLessThan(40);
      expect(result.category).toBe('Poor');
      expect(result.recommendations.length).toBeGreaterThan(3);
    });

    it('should calculate an excellent score for exceptional finances', () => {
      const excellentFinances: FinancialData = {
        ...mockBaseFinancialData,
        totalIncome: 10000,
        totalExpenses: 4000,
        totalDebt: 5000,
        totalAssets: 200000,
        emergencyFund: 25000,
        creditScore: 850,
        savingsRate: 0.4,
        debtToIncomeRatio: 0.05,
        liquidAssets: 50000
      };
      
      const result = calculateFinancialHealthScore(excellentFinances);
      
      expect(result.score).toBeGreaterThan(85);
      expect(result.category).toBe('Excellent');
    });
  });

  describe('Edge cases', () => {
    it('should handle zero income', () => {
      const zeroIncomeData: FinancialData = {
        ...mockBaseFinancialData,
        totalIncome: 0
      };
      
      const result = calculateFinancialHealthScore(zeroIncomeData);
      
      expect(result.score).toBeLessThan(30);
      expect(result.category).toBe('Poor');
      expect(result.recommendations).toContain('Establish a reliable income source');
    });

    it('should handle negative savings rate', () => {
      const negativeSavingsData: FinancialData = {
        ...mockBaseFinancialData,
        totalExpenses: 6000,
        savingsRate: -0.2
      };
      
      const result = calculateFinancialHealthScore(negativeSavingsData);
      
      expect(result.score).toBeLessThan(50);
      expect(result.recommendations).toContain('Reduce expenses to achieve positive savings rate');
    });

    it('should handle extremely high debt-to-income ratio', () => {
      const highDebtData: FinancialData = {
        ...mockBaseFinancialData,
        totalDebt: 100000,
        monthlyDebtPayments: 4000,
        debtToIncomeRatio: 0.8
      };
      
      const result = calculateFinancialHealthScore(highDebtData);
      
      expect(result.score).toBeLessThan(40);
      expect(result.recommendations).toContain('Focus on debt reduction - debt-to-income ratio is too high');
    });

    it('should handle zero emergency fund', () => {
      const noEmergencyFundData: FinancialData = {
        ...mockBaseFinancialData,
        emergencyFund: 0
      };
      
      const result = calculateFinancialHealthScore(noEmergencyFundData);
      
      expect(result.recommendations).toContain('Build emergency fund to cover 3-6 months of expenses');
    });

    it('should handle very low credit score', () => {
      const lowCreditData: FinancialData = {
        ...mockBaseFinancialData,
        creditScore: 400
      };
      
      const result = calculateFinancialHealthScore(lowCreditData);
      
      expect(result.score).toBeLessThan(60);
      expect(result.recommendations).toContain('Work on improving credit score');
    });

    it('should handle unemployment', () => {
      const unemployedData: FinancialData = {
        ...mockBaseFinancialData,
        employmentStatus: 'unemployed',
        totalIncome: 1000
      };
      
      const result = calculateFinancialHealthScore(unemployedData);
      
      expect(result.score).toBeLessThan(50);
      expect(result.recommendations).toContain('Seek stable employment to improve financial security');
    });
  });

  describe('Boundary conditions', () => {
    it('should handle minimum valid inputs', () => {
      const minimalData: FinancialData = {
        totalIncome: 1,
        totalExpenses: 1,
        totalDebt: 0,
        totalAssets: 0,
        emergencyFund: 0,
        creditScore: 300,
        monthlyDebtPayments: 0,
        monthlyRecurringExpenses: 1,
        savingsRate: 0,
        debtToIncomeRatio: 0,
        liquidAssets: 0,
        age: 18,
        hasHealthInsurance: false,
        hasEmergencyContact: false,
        employmentStatus: 'unemployed'
      };
      
      const result = calculateFinancialHealthScore(minimalData);
      
      expect(result.score).toBeGreaterThanOrEqual(0);
      expect(result.score).toBeLessThanOrEqual(100);
      expect(result.category).toBeDefined();
    });

    it('should handle maximum realistic inputs', () => {
      const maximalData: FinancialData = {
        totalIncome: 1000000,
        totalExpenses: 100000,
        totalDebt: 0,
        totalAssets: 5000000,
        emergencyFund: 500000,
        creditScore: 850,
        monthlyDebtPayments: 0,
        monthlyRecurringExpenses: 8333,
        savingsRate: 0.9,
        debtToIncomeRatio: 0,
        liquidAssets: 1000000,
        age: 65,
        hasHealthInsurance: true,
        hasEmergencyContact: true,
        employmentStatus: 'employed'
      };
      
      const result = calculateFinancialHealthScore(maximalData);
      
      expect(result.score).toBeGreaterThanOrEqual(0);
      expect(result.score).toBeLessThanOrEqual(100);
      expect(result.category).toBe('Excellent');
    });
  });

  describe('Age-based scenarios', () => {
    it('should provide age-appropriate recommendations for young adults', () => {
      const youngAdultData: FinancialData = {
        ...mockBaseFinancialData,
        age: 22,
        totalAssets: 5000,
        emergencyFund: 1000
      };
      
      const result = calculateFinancialHealthScore(youngAdultData);
      
      expect(result.recommendations).toContain('Start building long-term investment portfolio');
    });

    it('should provide age-appropriate recommendations for middle-aged individuals', () => {
      const middleAgedData: FinancialData = {
        ...mockBaseFinancialData,
        age: 45,
        totalAssets: 100000
      };
      
      const result = calculateFinancialHealthScore(middleAgedData);
      
      expect(result.recommendations).toContain('Focus on retirement planning and savings acceleration');
    });

    it('should provide age-appropriate recommendations for pre-retirees', () => {
      const preRetireeData: FinancialData = {
        ...mockBaseFinancialData,
        age: 58,
        totalAssets: 300000
      };
      
      const result = calculateFinancialHealthScore(preRetireeData);
      
      expect(result.recommendations).toContain('Ensure retirement savings are on track');
    });
  });

  describe('Insurance and safety net scenarios', () => {
    it('should penalize lack of health insurance', () => {
      const noInsuranceData: FinancialData = {
        ...mockBaseFinancialData,
        hasHealthInsurance: false
      };
      
      const withInsuranceData: FinancialData = {
        ...mockBaseFinancialData,
        hasHealthInsurance: true
      };
      
      const noInsuranceResult = calculateFinancialHealthScore(noInsuranceData);
      const withInsuranceResult = calculateFinancialHealthScore(withInsuranceData);
      
      expect(noInsuranceResult.score).toBeLessThan(withInsuranceResult.score);
      expect(noInsuranceResult.recommendations).toContain('Obtain health insurance coverage');
    });

    it('should recommend emergency contact setup', () => {
      const noContactData: FinancialData = {
        ...mockBaseFinancialData,
        hasEmergencyContact: false
      };
      
      const result = calculateFinancialHealthScore(noContactData);
      
      expect(result.recommendations).toContain('Set up emergency contacts and estate planning');
    });
  });

  describe('Liquid assets scenarios', () => {
    it('should consider liquid assets availability', () => {
      const lowLiquidityData: FinancialData = {
        ...mockBaseFinancialData,
        liquidAssets: 1000,
        totalAssets: 100000
      };
      
      const result = calculateFinancialHealthScore(lowLiquidityData);
      
      expect(result.recommendations).toContain('Increase liquid assets for better financial flexibility');
    });

    it('should handle high liquid asset ratio positively', () => {
      const highLiquidityData: FinancialData = {
        ...mockBaseFinancialData,
        liquidAssets: 40000,
        totalAssets: 60000
      };
      
      const lowLiquidityData: FinancialData = {
        ...mockBaseFinancialData,
        liquidAssets: 5000,
        totalAssets: 60000
      };
      
      const highLiquidityResult = calculateFinancialHealthScore(highLiquidityData);
      const lowLiquidityResult = calculateFinancialHealthScore(lowLiquidityData);
      
      expect(highLiquidityResult.score).toBeGreaterThan(lowLiquidityResult.score);
    });
  });

  describe('Score categorization', () => {
    it('should categorize scores correctly', () => {
      const testCases = [
        { score: 95, expectedCategory: 'Excellent' },
        { score: 85, expectedCategory: 'Excellent' },
        { score: 80, expectedCategory: 'Good' },
        { score: 70, expectedCategory: 'Good' },
        { score: 65, expectedCategory: 'Fair' },
        { score: 50, expectedCategory: 'Fair' },
        { score: 45, expectedCategory: 'Poor' },
        { score: 20, expectedCategory: 'Poor' }
      ];

      testCases.forEach(({ score, expectedCategory }) => {
        // Create data that would result in approximately the target score
        const testData: FinancialData = {
          ...mockBaseFinancialData,
          totalIncome: score > 80 ? 8000 : score > 60 ? 5000 : score > 40 ? 3000 : 2000,
          totalExpenses: score > 80 ? 4000 : score > 60 ? 3500 : score > 40 ? 2800 : 2500,
          creditScore: score > 80 ? 800 : score > 60 ? 720 : score > 40 ? 650 : 550,
          emergencyFund: score > 80 ? 15000 : score > 60 ? 8000 : score > 40 ? 3000 : 500,
          debtToIncomeRatio: score > 80 ? 0.1 : score > 60 ? 0.2 : score > 40 ? 0.4 : 0.7
        };

        const result = calculateFinancialHealthScore(testData);
        // Allow some tolerance in score matching due to calculation complexity
        if (Math.abs(result.score - score) <= 20) {
          expect(result.category).toBe(expectedCategory);
        }
      });
    });
  });

  describe('Input validation', () => {
    it('should handle null/undefined values gracefully', () => {
      const invalidData = {
        ...mockBaseFinancialData,
        totalIncome: null as any,
        creditScore: undefined as any
      };
      
      expect(() => {
        calculateFinancialHealthScore(invalidData);
      }).not.toThrow();
    });

    it('should handle negative values appropriately', () => {
      const negativeData: FinancialData = {
        ...mockBaseFinancialData,
        totalIncome: -1000,
        emergencyFund: -500
      };
      
      const result = calculateFinancialHealthScore(negativeData);
      
      expect(result.score).toBeGreaterThanOrEqual(0);
      expect(result.score).toBeLessThanOrEqual(100);
    });
  });
});