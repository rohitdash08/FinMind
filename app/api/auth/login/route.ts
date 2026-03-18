import { NextRequest, NextResponse } from 'next/server';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { prisma } from '@/lib/db';
import { ratelimit } from '@/lib/ratelimit';
import { anomalyDetector } from '@/lib/security/anomalyDetector';
import { securityLogger } from '@/lib/security/logger';
import { alertManager } from '@/lib/security/alerts';

export async function POST(request: NextRequest) {
  try {
    const ip = request.ip || request.headers.get('x-forwarded-for') || 'unknown';
    const userAgent = request.headers.get('user-agent') || 'unknown';
    
    // Rate limiting
    const { success } = await ratelimit.limit(ip);
    if (!success) {
      await securityLogger.logSecurityEvent({
        type: 'RATE_LIMIT_EXCEEDED',
        severity: 'medium',
        ip,
        userAgent,
        details: 'Login rate limit exceeded'
      });
      
      return NextResponse.json({ error: 'Too many requests' }, { status: 429 });
    }

    const { email, password } = await request.json();

    if (!email || !password) {
      await securityLogger.logSecurityEvent({
        type: 'INVALID_LOGIN_ATTEMPT',
        severity: 'low',
        ip,
        userAgent,
        details: 'Missing email or password',
        metadata: { email }
      });
      
      return NextResponse.json({ error: 'Email and password required' }, { status: 400 });
    }

    // Find user
    const user = await prisma.user.findUnique({
      where: { email },
      include: {
        loginHistory: {
          orderBy: { createdAt: 'desc' },
          take: 10
        }
      }
    });

    if (!user) {
      await securityLogger.logSecurityEvent({
        type: 'LOGIN_FAILED',
        severity: 'medium',
        ip,
        userAgent,
        details: 'User not found',
        metadata: { email }
      });
      
      return NextResponse.json({ error: 'Invalid credentials' }, { status: 401 });
    }

    // Check password
    const isPasswordValid = await bcrypt.compare(password, user.password);
    if (!isPasswordValid) {
      // Record failed attempt
      await prisma.loginAttempt.create({
        data: {
          userId: user.id,
          ip,
          userAgent,
          success: false,
          failureReason: 'INVALID_PASSWORD'
        }
      });

      await securityLogger.logSecurityEvent({
        type: 'LOGIN_FAILED',
        severity: 'medium',
        ip,
        userAgent,
        userId: user.id,
        details: 'Invalid password',
        metadata: { email }
      });

      // Check for brute force attempts
      const recentFailedAttempts = await prisma.loginAttempt.count({
        where: {
          userId: user.id,
          success: false,
          createdAt: {
            gte: new Date(Date.now() - 15 * 60 * 1000) // Last 15 minutes
          }
        }
      });

      if (recentFailedAttempts >= 5) {
        await alertManager.triggerAlert({
          type: 'BRUTE_FORCE_DETECTED',
          severity: 'high',
          userId: user.id,
          ip,
          details: `${recentFailedAttempts} failed login attempts in 15 minutes`
        });
      }

      return NextResponse.json({ error: 'Invalid credentials' }, { status: 401 });
    }

    // Anomaly detection
    const loginContext = {
      userId: user.id,
      ip,
      userAgent,
      timestamp: new Date(),
      location: await getLocationFromIP(ip),
      device: parseUserAgent(userAgent)
    };

    const anomalies = await anomalyDetector.detectLoginAnomalies(loginContext, user.loginHistory);
    
    // Log successful login
    const loginRecord = await prisma.loginAttempt.create({
      data: {
        userId: user.id,
        ip,
        userAgent,
        success: true,
        location: loginContext.location,
        device: loginContext.device.type
      }
    });

    await securityLogger.logSecurityEvent({
      type: 'LOGIN_SUCCESS',
      severity: 'info',
      ip,
      userAgent,
      userId: user.id,
      details: 'User logged in successfully',
      metadata: { 
        email,
        anomalies: anomalies.map(a => a.type),
        loginId: loginRecord.id
      }
    });

    // Process anomalies
    if (anomalies.length > 0) {
      for (const anomaly of anomalies) {
        await securityLogger.logSecurityEvent({
          type: 'ANOMALY_DETECTED',
          severity: anomaly.severity,
          ip,
          userAgent,
          userId: user.id,
          details: anomaly.description,
          metadata: {
            anomalyType: anomaly.type,
            confidence: anomaly.confidence,
            loginId: loginRecord.id
          }
        });

        // Trigger alerts for high-confidence anomalies
        if (anomaly.confidence > 0.7) {
          await alertManager.triggerAlert({
            type: 'LOGIN_ANOMALY',
            severity: anomaly.severity,
            userId: user.id,
            ip,
            details: anomaly.description,
            metadata: {
              anomalyType: anomaly.type,
              confidence: anomaly.confidence
            }
          });
        }
      }

      // For high-risk anomalies, require additional verification
      const highRiskAnomalies = anomalies.filter(a => 
        a.severity === 'high' && a.confidence > 0.8
      );

      if (highRiskAnomalies.length > 0) {
        await alertManager.triggerAlert({
          type: 'HIGH_RISK_LOGIN',
          severity: 'critical',
          userId: user.id,
          ip,
          details: 'High-risk login detected - additional verification required',
          metadata: {
            anomalies: highRiskAnomalies.map(a => a.type),
            loginId: loginRecord.id
          }
        });

        return NextResponse.json({
          success: false,
          requiresVerification: true,
          verificationId: loginRecord.id,
          message: 'Additional verification required due to unusual activity'
        }, { status: 202 });
      }
    }

    // Generate JWT token
    const token = jwt.sign(
      { 
        userId: user.id, 
        email: user.email,
        loginId: loginRecord.id
      },
      process.env.JWT_SECRET!,
      { expiresIn: '24h' }
    );

    // Update user's last login
    await prisma.user.update({
      where: { id: user.id },
      data: { lastLogin: new Date() }
    });

    const response = NextResponse.json({
      success: true,
      user: {
        id: user.id,
        email: user.email,
        name: user.name
      },
      anomalies: anomalies.map(a => ({
        type: a.type,
        severity: a.severity,
        description: a.description
      }))
    });

    response.cookies.set('token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 24 * 60 * 60 // 24 hours
    });

    return response;

  } catch (error) {
    console.error('Login error:', error);
    
    await securityLogger.logSecurityEvent({
      type: 'LOGIN_ERROR',
      severity: 'high',
      ip: request.ip || 'unknown',
      userAgent: request.headers.get('user-agent') || 'unknown',
      details: 'Server error during login',
      metadata: { error: error instanceof Error ? error.message : 'Unknown error' }
    });

    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

async function getLocationFromIP(ip: string) {
  try {
    // Mock implementation - replace with actual geolocation service
    if (ip === 'unknown' || ip.startsWith('192.168.') || ip.startsWith('10.')) {
      return { country: 'Unknown', city: 'Unknown', region: 'Unknown' };
    }
    
    // This would typically call a geolocation API
    return { country: 'US', city: 'Unknown', region: 'Unknown' };
  } catch {
    return { country: 'Unknown', city: 'Unknown', region: 'Unknown' };
  }
}

function parseUserAgent(userAgent: string) {
  // Simple user agent parsing - replace with proper library like ua-parser-js
  const isDesktop = /Windows|Macintosh|Linux/.test(userAgent);
  const isMobile = /Mobile|Android|iPhone/.test(userAgent);
  const isBot = /bot|crawler|spider/i.test(userAgent);
  
  let type = 'unknown';
  if (isBot) type = 'bot';
  else if (isMobile) type = 'mobile';
  else if (isDesktop) type = 'desktop';
  
  return {
    type,
    browser: extractBrowser(userAgent),
    os: extractOS(userAgent)
  };
}

function extractBrowser(userAgent: string): string {
  if (userAgent.includes('Chrome')) return 'Chrome';
  if (userAgent.includes('Firefox')) return 'Firefox';
  if (userAgent.includes('Safari')) return 'Safari';
  if (userAgent.includes('Edge')) return 'Edge';
  return 'Unknown';
}

function extractOS(userAgent: string): string {
  if (userAgent.includes('Windows')) return 'Windows';
  if (userAgent.includes('Mac OS')) return 'macOS';
  if (userAgent.includes('Linux')) return 'Linux';
  if (userAgent.includes('Android')) return 'Android';
  if (userAgent.includes('iPhone')) return 'iOS';
  return 'Unknown';
}