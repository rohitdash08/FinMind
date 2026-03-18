import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { z } from 'zod';
import { PrismaClient } from '@prisma/client';
import { createHash } from 'crypto';

const prisma = new PrismaClient();

const exportRequestSchema = z.object({
  userId: z.string().optional(),
  email: z.string().email().optional(),
}).refine(data => data.userId || data.email, {
  message: "Either userId or email must be provided"
});

const deleteRequestSchema = z.object({
  userId: z.string().optional(),
  email: z.string().email().optional(),
  confirmationCode: z.string().min(6),
}).refine(data => data.userId || data.email, {
  message: "Either userId or email must be provided"
});

async function createAuditLog(action: string, userId: string, details: any, ipAddress?: string) {
  await prisma.auditLog.create({
    data: {
      action,
      userId,
      details: JSON.stringify(details),
      ipAddress,
      timestamp: new Date(),
    },
  });
}

async function getUserData(userId: string) {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: {
      profile: true,
      posts: true,
      comments: true,
      likes: true,
      followers: true,
      following: true,
      notifications: true,
      sessions: true,
    },
  });

  return user;
}

async function hashData(data: string): Promise<string> {
  return createHash('sha256').update(data).digest('hex');
}

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { userId, email } = exportRequestSchema.parse(body);
    
    const ipAddress = request.headers.get('x-forwarded-for') || 
                     request.headers.get('x-real-ip') || 
                     'unknown';

    // Find user by userId or email
    let targetUser;
    if (userId) {
      targetUser = await prisma.user.findUnique({ where: { id: userId } });
    } else if (email) {
      targetUser = await prisma.user.findUnique({ where: { email } });
    }

    if (!targetUser) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Check if requesting user has permission (self or admin)
    const isAdmin = session.user.role === 'ADMIN' || session.user.role === 'SUPER_ADMIN';
    const isSelf = session.user.id === targetUser.id;
    
    if (!isAdmin && !isSelf) {
      await createAuditLog('GDPR_EXPORT_DENIED', session.user.id, {
        targetUserId: targetUser.id,
        reason: 'Insufficient permissions'
      }, ipAddress);
      return NextResponse.json({ error: 'Insufficient permissions' }, { status: 403 });
    }

    // Get all user data
    const userData = await getUserData(targetUser.id);
    
    if (!userData) {
      return NextResponse.json({ error: 'User data not found' }, { status: 404 });
    }

    // Create export record
    const exportRecord = await prisma.gdprExport.create({
      data: {
        userId: targetUser.id,
        requestedBy: session.user.id,
        status: 'COMPLETED',
        dataHash: await hashData(JSON.stringify(userData)),
        createdAt: new Date(),
        expiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000), // 30 days
      },
    });

    // Create audit log
    await createAuditLog('GDPR_EXPORT_REQUESTED', session.user.id, {
      targetUserId: targetUser.id,
      exportId: exportRecord.id,
      dataTypes: Object.keys(userData).filter(key => userData[key] !== null)
    }, ipAddress);

    // Remove sensitive fields before sending
    const sanitizedData = {
      ...userData,
      password: '[REDACTED]',
      sessions: userData.sessions?.map(session => ({
        ...session,
        sessionToken: '[REDACTED]',
        accessToken: '[REDACTED]',
        refreshToken: '[REDACTED]',
      })),
    };

    return NextResponse.json({
      success: true,
      exportId: exportRecord.id,
      data: sanitizedData,
      exportedAt: exportRecord.createdAt,
      expiresAt: exportRecord.expiresAt,
    });

  } catch (error) {
    console.error('GDPR export error:', error);
    
    if (error instanceof z.ZodError) {
      return NextResponse.json({
        error: 'Validation failed',
        details: error.errors
      }, { status: 400 });
    }

    return NextResponse.json({
      error: 'Internal server error'
    }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { userId, email, confirmationCode } = deleteRequestSchema.parse(body);
    
    const ipAddress = request.headers.get('x-forwarded-for') || 
                     request.headers.get('x-real-ip') || 
                     'unknown';

    // Find user by userId or email
    let targetUser;
    if (userId) {
      targetUser = await prisma.user.findUnique({ where: { id: userId } });
    } else if (email) {
      targetUser = await prisma.user.findUnique({ where: { email } });
    }

    if (!targetUser) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Check if requesting user has permission (self or admin)
    const isAdmin = session.user.role === 'ADMIN' || session.user.role === 'SUPER_ADMIN';
    const isSelf = session.user.id === targetUser.id;
    
    if (!isAdmin && !isSelf) {
      await createAuditLog('GDPR_DELETE_DENIED', session.user.id, {
        targetUserId: targetUser.id,
        reason: 'Insufficient permissions'
      }, ipAddress);
      return NextResponse.json({ error: 'Insufficient permissions' }, { status: 403 });
    }

    // Verify confirmation code (in real app, this would be sent via email/SMS)
    const expectedCode = createHash('sha256')
      .update(`${targetUser.id}-${targetUser.email}-delete`)
      .digest('hex')
      .substring(0, 6)
      .toUpperCase();
    
    if (confirmationCode.toUpperCase() !== expectedCode) {
      await createAuditLog('GDPR_DELETE_INVALID_CODE', session.user.id, {
        targetUserId: targetUser.id,
        providedCode: confirmationCode
      }, ipAddress);
      return NextResponse.json({ error: 'Invalid confirmation code' }, { status: 400 });
    }

    // Create deletion record before deleting
    const deletionRecord = await prisma.gdprDeletion.create({
      data: {
        userId: targetUser.id,
        requestedBy: session.user.id,
        status: 'PENDING',
        confirmationCode,
        createdAt: new Date(),
      },
    });

    // Start transaction for data deletion
    await prisma.$transaction(async (tx) => {
      // Delete related data in correct order
      await tx.notification.deleteMany({ where: { userId: targetUser.id } });
      await tx.like.deleteMany({ where: { userId: targetUser.id } });
      await tx.comment.deleteMany({ where: { userId: targetUser.id } });
      await tx.post.deleteMany({ where: { userId: targetUser.id } });
      await tx.follow.deleteMany({ 
        where: { 
          OR: [
            { followerId: targetUser.id },
            { followingId: targetUser.id }
          ]
        }
      });
      await tx.session.deleteMany({ where: { userId: targetUser.id } });
      await tx.profile.deleteMany({ where: { userId: targetUser.id } });
      await tx.gdprExport.deleteMany({ where: { userId: targetUser.id } });
      
      // Update deletion record
      await tx.gdprDeletion.update({
        where: { id: deletionRecord.id },
        data: { 
          status: 'COMPLETED',
          completedAt: new Date()
        }
      });
      
      // Finally delete the user
      await tx.user.delete({ where: { id: targetUser.id } });
    });

    // Create final audit log
    await createAuditLog('GDPR_DELETE_COMPLETED', session.user.id, {
      targetUserId: targetUser.id,
      deletionId: deletionRecord.id,
      deletedAt: new Date()
    }, ipAddress);

    return NextResponse.json({
      success: true,
      deletionId: deletionRecord.id,
      message: 'User data successfully deleted',
      deletedAt: new Date(),
    });

  } catch (error) {
    console.error('GDPR deletion error:', error);
    
    if (error instanceof z.ZodError) {
      return NextResponse.json({
        error: 'Validation failed',
        details: error.errors
      }, { status: 400 });
    }

    return NextResponse.json({
      error: 'Internal server error'
    }, { status: 500 });
  }
}