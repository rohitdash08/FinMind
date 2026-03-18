import { LoginAnomalyDetector } from '../../security/LoginAnomalyDetector';
import { RiskScorer } from '../../security/RiskScorer';
import { AlertService } from '../../services/AlertService';
import { UserRepository } from '../../repositories/UserRepository';
import { LoginAttempt, RiskLevel, AnomalyType } from '../../types/security';

jest.mock('../../security/RiskScorer');
jest.mock('../../services/AlertService');
jest.mock('../../repositories/UserRepository');

describe('LoginAnomalyDetector', () => {
  let detector: LoginAnomalyDetector;
  let mockRiskScorer: jest.Mocked<RiskScorer>;
  let mockAlertService: jest.Mocked<AlertService>;
  let mockUserRepository: jest.Mocked<UserRepository>;

  const mockUser = {
    id: '123',
    email: 'test@example.com',
    loginHistory: []
  };

  beforeEach(() => {
    mockRiskScorer = new RiskScorer() as jest.Mocked<RiskScorer>;
    mockAlertService = new AlertService() as jest.Mocked<AlertService>;
    mockUserRepository = new UserRepository() as jest.Mocked<UserRepository>;
    
    detector = new LoginAnomalyDetector(
      mockRiskScorer,
      mockAlertService,
      mockUserRepository
    );

    mockUserRepository.findById.mockResolvedValue(mockUser);
  });

  describe('analyzeLoginAttempt', () => {
    const baseAttempt: LoginAttempt = {
      userId: '123',
      email: 'test@example.com',
      ipAddress: '192.168.1.1',
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
      timestamp: new Date(),
      location: {
        country: 'US',
        city: 'New York',
        latitude: 40.7128,
        longitude: -74.0060
      },
      success: true
    };

    it('should detect geographical anomaly for new location', async () => {
      const attemptFromDifferentLocation = {
        ...baseAttempt,
        location: {
          country: 'RU',
          city: 'Moscow',
          latitude: 55.7558,
          longitude: 37.6176
        }
      };

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 85,
        level: RiskLevel.HIGH,
        factors: ['geographical_anomaly']
      });

      const result = await detector.analyzeLoginAttempt(attemptFromDifferentLocation);

      expect(result.anomalies).toContain(AnomalyType.GEOGRAPHICAL_ANOMALY);
      expect(result.riskScore).toBe(85);
      expect(result.riskLevel).toBe(RiskLevel.HIGH);
    });

    it('should detect device fingerprint anomaly for new device', async () => {
      const attemptFromNewDevice = {
        ...baseAttempt,
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)',
        deviceFingerprint: 'different-device-fingerprint'
      };

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 70,
        level: RiskLevel.MEDIUM,
        factors: ['device_anomaly']
      });

      const result = await detector.analyzeLoginAttempt(attemptFromNewDevice);

      expect(result.anomalies).toContain(AnomalyType.DEVICE_ANOMALY);
      expect(result.riskScore).toBe(70);
      expect(result.riskLevel).toBe(RiskLevel.MEDIUM);
    });

    it('should detect time pattern anomaly for unusual login time', async () => {
      const unusualTimeAttempt = {
        ...baseAttempt,
        timestamp: new Date('2023-01-01T03:30:00Z') // 3:30 AM
      };

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 60,
        level: RiskLevel.MEDIUM,
        factors: ['time_anomaly']
      });

      const result = await detector.analyzeLoginAttempt(unusualTimeAttempt);

      expect(result.anomalies).toContain(AnomalyType.TIME_ANOMALY);
      expect(result.riskScore).toBe(60);
    });

    it('should detect velocity anomaly for rapid login attempts', async () => {
      const rapidAttempt = {
        ...baseAttempt,
        timestamp: new Date(Date.now() - 30000) // 30 seconds ago
      };

      // Mock multiple recent attempts
      mockUserRepository.findRecentLoginAttempts.mockResolvedValue([
        { ...rapidAttempt, timestamp: new Date(Date.now() - 10000) },
        { ...rapidAttempt, timestamp: new Date(Date.now() - 20000) },
        { ...rapidAttempt, timestamp: new Date(Date.now() - 30000) }
      ]);

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 90,
        level: RiskLevel.CRITICAL,
        factors: ['velocity_anomaly']
      });

      const result = await detector.analyzeLoginAttempt(rapidAttempt);

      expect(result.anomalies).toContain(AnomalyType.VELOCITY_ANOMALY);
      expect(result.riskScore).toBe(90);
      expect(result.riskLevel).toBe(RiskLevel.CRITICAL);
    });

    it('should combine multiple anomalies and increase risk score', async () => {
      const multipleAnomaliesAttempt = {
        ...baseAttempt,
        location: { country: 'CN', city: 'Beijing', latitude: 39.9042, longitude: 116.4074 },
        userAgent: 'Mozilla/5.0 (X11; Linux x86_64)',
        timestamp: new Date('2023-01-01T02:00:00Z')
      };

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 95,
        level: RiskLevel.CRITICAL,
        factors: ['geographical_anomaly', 'device_anomaly', 'time_anomaly']
      });

      const result = await detector.analyzeLoginAttempt(multipleAnomaliesAttempt);

      expect(result.anomalies).toHaveLength(3);
      expect(result.anomalies).toContain(AnomalyType.GEOGRAPHICAL_ANOMALY);
      expect(result.anomalies).toContain(AnomalyType.DEVICE_ANOMALY);
      expect(result.anomalies).toContain(AnomalyType.TIME_ANOMALY);
      expect(result.riskScore).toBe(95);
      expect(result.riskLevel).toBe(RiskLevel.CRITICAL);
    });

    it('should handle legitimate login with no anomalies', async () => {
      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 15,
        level: RiskLevel.LOW,
        factors: []
      });

      const result = await detector.analyzeLoginAttempt(baseAttempt);

      expect(result.anomalies).toHaveLength(0);
      expect(result.riskScore).toBe(15);
      expect(result.riskLevel).toBe(RiskLevel.LOW);
    });
  });

  describe('Risk Scoring Edge Cases', () => {
    it('should handle user with no login history', async () => {
      const newUser = { ...mockUser, loginHistory: [] };
      mockUserRepository.findById.mockResolvedValue(newUser);

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 50,
        level: RiskLevel.MEDIUM,
        factors: ['new_user']
      });

      const result = await detector.analyzeLoginAttempt(baseAttempt);

      expect(result.riskScore).toBe(50);
      expect(result.riskLevel).toBe(RiskLevel.MEDIUM);
    });

    it('should handle missing location data gracefully', async () => {
      const attemptWithoutLocation = {
        ...baseAttempt,
        location: undefined
      };

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 30,
        level: RiskLevel.LOW,
        factors: []
      });

      const result = await detector.analyzeLoginAttempt(attemptWithoutLocation);

      expect(result).toBeDefined();
      expect(result.riskScore).toBe(30);
    });

    it('should handle malformed user agent strings', async () => {
      const attemptWithBadUserAgent = {
        ...baseAttempt,
        userAgent: ''
      };

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 40,
        level: RiskLevel.MEDIUM,
        factors: ['missing_user_agent']
      });

      const result = await detector.analyzeLoginAttempt(attemptWithBadUserAgent);

      expect(result.riskScore).toBe(40);
    });

    it('should cap risk score at maximum value', async () => {
      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 150, // Over maximum
        level: RiskLevel.CRITICAL,
        factors: ['multiple_critical_factors']
      });

      const result = await detector.analyzeLoginAttempt(baseAttempt);

      expect(result.riskScore).toBeLessThanOrEqual(100);
    });
  });

  describe('Alert Triggering', () => {
    beforeEach(() => {
      mockAlertService.sendSecurityAlert.mockResolvedValue(undefined);
    });

    it('should trigger alert for high risk login', async () => {
      const highRiskAttempt = {
        ...baseAttempt,
        location: { country: 'KP', city: 'Pyongyang', latitude: 39.0392, longitude: 125.7625 }
      };

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 85,
        level: RiskLevel.HIGH,
        factors: ['geographical_anomaly', 'suspicious_country']
      });

      await detector.analyzeLoginAttempt(highRiskAttempt);

      expect(mockAlertService.sendSecurityAlert).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'suspicious_login',
          severity: 'high',
          userId: '123',
          details: expect.any(Object)
        })
      );
    });

    it('should trigger alert for critical risk login', async () => {
      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 95,
        level: RiskLevel.CRITICAL,
        factors: ['multiple_anomalies']
      });

      await detector.analyzeLoginAttempt(baseAttempt);

      expect(mockAlertService.sendSecurityAlert).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'suspicious_login',
          severity: 'critical',
          userId: '123'
        })
      );
    });

    it('should not trigger alert for low risk login', async () => {
      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 20,
        level: RiskLevel.LOW,
        factors: []
      });

      await detector.analyzeLoginAttempt(baseAttempt);

      expect(mockAlertService.sendSecurityAlert).not.toHaveBeenCalled();
    });

    it('should handle alert service failures gracefully', async () => {
      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 90,
        level: RiskLevel.CRITICAL,
        factors: ['critical_anomaly']
      });

      mockAlertService.sendSecurityAlert.mockRejectedValue(new Error('Alert service unavailable'));

      // Should not throw error
      const result = await detector.analyzeLoginAttempt(baseAttempt);
      
      expect(result).toBeDefined();
      expect(result.riskLevel).toBe(RiskLevel.CRITICAL);
    });
  });

  describe('Concurrent Login Detection', () => {
    it('should detect simultaneous logins from different locations', async () => {
      const concurrentAttempts = [
        { ...baseAttempt, location: { country: 'US', city: 'New York', latitude: 40.7128, longitude: -74.0060 } },
        { ...baseAttempt, location: { country: 'UK', city: 'London', latitude: 51.5074, longitude: -0.1278 } }
      ];

      mockUserRepository.findRecentLoginAttempts.mockResolvedValue(concurrentAttempts);

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 88,
        level: RiskLevel.HIGH,
        factors: ['concurrent_logins', 'impossible_travel']
      });

      const result = await detector.analyzeLoginAttempt(baseAttempt);

      expect(result.anomalies).toContain(AnomalyType.CONCURRENT_SESSIONS);
      expect(result.riskScore).toBe(88);
    });
  });

  describe('Rate Limiting Integration', () => {
    it('should detect brute force patterns', async () => {
      const failedAttempts = Array(10).fill(null).map((_, i) => ({
        ...baseAttempt,
        success: false,
        timestamp: new Date(Date.now() - (i * 1000))
      }));

      mockUserRepository.findRecentLoginAttempts.mockResolvedValue(failedAttempts);

      mockRiskScorer.calculateRiskScore.mockResolvedValue({
        score: 95,
        level: RiskLevel.CRITICAL,
        factors: ['brute_force_pattern']
      });

      const result = await detector.analyzeLoginAttempt(baseAttempt);

      expect(result.anomalies).toContain(AnomalyType.BRUTE_FORCE);
      expect(result.riskLevel).toBe(RiskLevel.CRITICAL);
    });
  });
});