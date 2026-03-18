import { DateTime } from 'luxon';
import { getClientIP, getDeviceFingerprint, getUserAgent } from '../utils/request';
import { logger } from '../utils/logger';
import { Redis } from 'ioredis';
import geoip from 'geoip-lite';

interface LoginAttempt {
  userId: string;
  ip: string;
  userAgent: string;
  deviceFingerprint: string;
  timestamp: Date;
  success: boolean;
  location?: {
    country: string;
    region: string;
    city: string;
    coordinates: [number, number];
  };
}

interface RiskFactors {
  newLocation: boolean;
  newDevice: boolean;
  unusualTime: boolean;
  highFrequency: boolean;
  failedAttempts: boolean;
  vpnDetected: boolean;
  locationDistance: number;
}

interface AnomalyScore {
  totalScore: number;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  factors: RiskFactors;
  recommendedAction: 'ALLOW' | 'CHALLENGE' | 'BLOCK' | 'ALERT';
}

export class LoginAnomalyDetector {
  private redis: Redis;
  private readonly REDIS_PREFIX = 'login_anomaly';
  private readonly RISK_THRESHOLDS = {
    LOW: 0,
    MEDIUM: 30,
    HIGH: 60,
    CRITICAL: 85
  };

  constructor(redis: Redis) {
    this.redis = redis;
  }

  async analyzeLoginAttempt(
    userId: string,
    ip: string,
    userAgent: string,
    success: boolean
  ): Promise<AnomalyScore> {
    const loginAttempt: LoginAttempt = {
      userId,
      ip,
      userAgent,
      deviceFingerprint: getDeviceFingerprint(userAgent, ip),
      timestamp: new Date(),
      success,
      location: this.getLocationFromIP(ip)
    };

    // Store the login attempt
    await this.storeLoginAttempt(loginAttempt);

    // Calculate risk factors
    const riskFactors = await this.calculateRiskFactors(loginAttempt);
    
    // Calculate anomaly score
    const score = this.calculateAnomalyScore(riskFactors);

    // Log high-risk attempts
    if (score.riskLevel === 'HIGH' || score.riskLevel === 'CRITICAL') {
      logger.warn('High-risk login attempt detected', {
        userId,
        ip,
        riskLevel: score.riskLevel,
        score: score.totalScore,
        factors: riskFactors
      });
    }

    return score;
  }

  private getLocationFromIP(ip: string): LoginAttempt['location'] | undefined {
    try {
      const geo = geoip.lookup(ip);
      if (geo) {
        return {
          country: geo.country,
          region: geo.region,
          city: geo.city,
          coordinates: [geo.ll[0], geo.ll[1]]
        };
      }
    } catch (error) {
      logger.error('Error getting location from IP', { ip, error });
    }
    return undefined;
  }

  private async calculateRiskFactors(attempt: LoginAttempt): Promise<RiskFactors> {
    const [
      isNewLocation,
      isNewDevice,
      isUnusualTime,
      isHighFrequency,
      hasRecentFailures,
      isVPNDetected,
      locationDistance
    ] = await Promise.all([
      this.isNewLocation(attempt),
      this.isNewDevice(attempt),
      this.isUnusualTime(attempt),
      this.isHighFrequency(attempt),
      this.hasRecentFailedAttempts(attempt),
      this.detectVPN(attempt.ip),
      this.calculateLocationDistance(attempt)
    ]);

    return {
      newLocation: isNewLocation,
      newDevice: isNewDevice,
      unusualTime: isUnusualTime,
      highFrequency: isHighFrequency,
      failedAttempts: hasRecentFailures,
      vpnDetected: isVPNDetected,
      locationDistance
    };
  }

  private async isNewLocation(attempt: LoginAttempt): Promise<boolean> {
    if (!attempt.location) return false;

    const key = `${this.REDIS_PREFIX}:locations:${attempt.userId}`;
    const knownLocations = await this.redis.smembers(key);
    
    const locationKey = `${attempt.location.country}:${attempt.location.region}:${attempt.location.city}`;
    const isNew = !knownLocations.includes(locationKey);

    if (isNew) {
      await this.redis.sadd(key, locationKey);
      await this.redis.expire(key, 86400 * 90); // 90 days
    }

    return isNew;
  }

  private async isNewDevice(attempt: LoginAttempt): Promise<boolean> {
    const key = `${this.REDIS_PREFIX}:devices:${attempt.userId}`;
    const knownDevices = await this.redis.smembers(key);
    
    const isNew = !knownDevices.includes(attempt.deviceFingerprint);

    if (isNew) {
      await this.redis.sadd(key, attempt.deviceFingerprint);
      await this.redis.expire(key, 86400 * 90); // 90 days
    }

    return isNew;
  }

  private async isUnusualTime(attempt: LoginAttempt): Promise<boolean> {
    const hour = attempt.timestamp.getHours();
    const key = `${this.REDIS_PREFIX}:login_hours:${attempt.userId}`;
    
    // Get user's typical login hours
    const hourCounts = await this.redis.hgetall(key);
    
    // If no history, consider normal business hours as usual
    if (Object.keys(hourCounts).length === 0) {
      await this.redis.hincrby(key, hour.toString(), 1);
      await this.redis.expire(key, 86400 * 30); // 30 days
      return hour < 6 || hour > 22; // Outside 6 AM - 10 PM
    }

    // Calculate if this hour is unusual based on history
    const totalLogins = Object.values(hourCounts).reduce((sum, count) => sum + parseInt(count), 0);
    const hourCount = parseInt(hourCounts[hour.toString()] || '0');
    const hourPercentage = hourCount / totalLogins;

    // Update the hour count
    await this.redis.hincrby(key, hour.toString(), 1);
    await this.redis.expire(key, 86400 * 30);

    // Consider unusual if this hour represents less than 2% of historical logins
    return hourPercentage < 0.02;
  }

  private async isHighFrequency(attempt: LoginAttempt): Promise<boolean> {
    const key = `${this.REDIS_PREFIX}:frequency:${attempt.userId}`;
    const now = Date.now();
    const fiveMinutesAgo = now - (5 * 60 * 1000);
    
    // Count attempts in the last 5 minutes
    const recentAttempts = await this.redis.zcount(key, fiveMinutesAgo, now);
    
    // Add current attempt
    await this.redis.zadd(key, now, `${now}:${attempt.ip}`);
    await this.redis.expire(key, 300); // 5 minutes
    
    // Clean old entries
    await this.redis.zremrangebyscore(key, 0, fiveMinutesAgo);
    
    return recentAttempts > 10; // More than 10 attempts in 5 minutes
  }

  private async hasRecentFailedAttempts(attempt: LoginAttempt): Promise<boolean> {
    const key = `${this.REDIS_PREFIX}:failures:${attempt.userId}:${attempt.ip}`;
    const failureCount = await this.redis.get(key);
    
    if (!attempt.success) {
      // Increment failure count
      await this.redis.incr(key);
      await this.redis.expire(key, 3600); // 1 hour
      return parseInt(failureCount || '0') >= 2;
    } else {
      // Clear failure count on successful login
      await this.redis.del(key);
      return false;
    }
  }

  private async detectVPN(ip: string): Promise<boolean> {
    // This is a simplified VPN detection
    // In production, you might use a service like IPQualityScore or similar
    const key = `${this.REDIS_PREFIX}:vpn_cache:${ip}`;
    const cached = await this.redis.get(key);
    
    if (cached !== null) {
      return cached === 'true';
    }

    // Simple heuristics - in production, use proper VPN detection service
    const isVPN = await this.simpleVPNDetection(ip);
    
    await this.redis.setex(key, 86400, isVPN.toString()); // Cache for 24 hours
    return isVPN;
  }

  private async simpleVPNDetection(ip: string): Promise<boolean> {
    // This is a placeholder - implement proper VPN detection
    // Common VPN characteristics:
    // - Known VPN IP ranges
    // - ASN associated with VPN providers
    // - Multiple users from same IP
    const vpnProviders = ['NordVPN', 'ExpressVPN', 'Surfshark', 'ProtonVPN'];
    // Simplified check - in reality, you'd check against known VPN IP ranges
    return false;
  }

  private async calculateLocationDistance(attempt: LoginAttempt): Promise<number> {
    if (!attempt.location) return 0;

    const key = `${this.REDIS_PREFIX}:last_location:${attempt.userId}`;
    const lastLocation = await this.redis.get(key);
    
    if (!lastLocation) {
      await this.redis.setex(key, 86400 * 7, JSON.stringify(attempt.location)); // 7 days
      return 0;
    }

    try {
      const last = JSON.parse(lastLocation);
      const distance = this.calculateHaversineDistance(
        last.coordinates,
        attempt.location.coordinates
      );
      
      // Update last location
      await this.redis.setex(key, 86400 * 7, JSON.stringify(attempt.location));
      
      return distance;
    } catch {
      return 0;
    }
  }

  private calculateHaversineDistance(coords1: [number, number], coords2: [number, number]): number {
    const R = 6371; // Earth's radius in kilometers
    const dLat = this.toRadians(coords2[0] - coords1[0]);
    const dLon = this.toRadians(coords2[1] - coords1[1]);
    
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(this.toRadians(coords1[0])) * Math.cos(this.toRadians(coords2[0])) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  }

  private toRadians(degrees: number): number {
    return degrees * (Math.PI / 180);
  }

  private calculateAnomalyScore(factors: RiskFactors): AnomalyScore {
    let score = 0;

    // Location-based scoring
    if (factors.newLocation) score += 25;
    if (factors.locationDistance > 1000) score += 20; // More than 1000km
    else if (factors.locationDistance > 500) score += 10; // 500-1000km

    // Device-based scoring
    if (factors.newDevice) score += 20;

    // Time-based scoring
    if (factors.unusualTime) score += 15;

    // Frequency-based scoring
    if (factors.highFrequency) score += 30;

    // Security-based scoring
    if (factors.failedAttempts) score += 25;
    if (factors.vpnDetected) score += 15;

    // Determine risk level
    let riskLevel: AnomalyScore['riskLevel'] = 'LOW';
    if (score >= this.RISK_THRESHOLDS.CRITICAL) riskLevel = 'CRITICAL';
    else if (score >= this.RISK_THRESHOLDS.HIGH) riskLevel = 'HIGH';
    else if (score >= this.RISK_THRESHOLDS.MEDIUM) riskLevel = 'MEDIUM';

    // Determine recommended action
    let recommendedAction: AnomalyScore['recommendedAction'] = 'ALLOW';
    if (score >= 85) recommendedAction = 'BLOCK';
    else if (score >= 60) recommendedAction = 'CHALLENGE';
    else if (score >= 30) recommendedAction = 'ALERT';

    return {
      totalScore: score,
      riskLevel,
      factors,
      recommendedAction
    };
  }

  private async storeLoginAttempt(attempt: LoginAttempt): Promise<void> {
    const key = `${this.REDIS_PREFIX}:attempts:${attempt.userId}`;
    const attemptData = JSON.stringify(attempt);
    
    await this.redis.lpush(key, attemptData);
    await this.redis.ltrim(key, 0, 99); // Keep last 100 attempts
    await this.redis.expire(key, 86400 * 30); // 30 days
  }

  async getRecentAttempts(userId: string, limit: number = 10): Promise<LoginAttempt[]> {
    const key = `${this.REDIS_PREFIX}:attempts:${userId}`;
    const attempts = await this.redis.lrange(key, 0, limit - 1);
    
    return attempts.map(attempt => {
      try {
        return JSON.parse(attempt);
      } catch {
        return null;
      }
    }).filter(Boolean);
  }

  async clearUserData(userId: string): Promise<void> {
    const keys = await this.redis.keys(`${this.REDIS_PREFIX}:*:${userId}*`);
    if (keys.length > 0) {
      await this.redis.del(...keys);
    }
  }
}