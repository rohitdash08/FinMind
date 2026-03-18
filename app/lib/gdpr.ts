import { User } from '@prisma/client';
import prisma from './prisma';
import { createHash } from 'crypto';

interface UserData {
  user: Partial<User>;
  profile?: any;
  posts?: any[];
  comments?: any[];
  likes?: any[];
  follows?: any[];
  messages?: any[];
  activities?: any[];
}

interface AuditLogEntry {
  id: string;
  userId: string;
  action: 'DATA_EXPORT' | 'DATA_DELETE';
  timestamp: Date;
  details: string;
  ipAddress?: string;
  userAgent?: string;
}

class GDPRService {
  private async createAuditLog(entry: Omit<AuditLogEntry, 'id' | 'timestamp'>): Promise<void> {
    try {
      await prisma.auditLog.create({
        data: {
          ...entry,
          id: createHash('sha256').update(`${entry.userId}-${Date.now()}`).digest('hex').substring(0, 16),
          timestamp: new Date(),
        },
      });
    } catch (error) {
      console.error('Failed to create audit log:', error);
    }
  }

  async exportUserData(userId: string, requestMetadata?: { ipAddress?: string; userAgent?: string }): Promise<UserData> {
    try {
      const userData: UserData = {};

      // Export user profile
      const user = await prisma.user.findUnique({
        where: { id: userId },
        select: {
          id: true,
          email: true,
          name: true,
          username: true,
          bio: true,
          avatar: true,
          banner: true,
          website: true,
          location: true,
          birthDate: true,
          createdAt: true,
          updatedAt: true,
          verified: true,
          private: true,
          followersCount: true,
          followingCount: true,
          postsCount: true,
        },
      });

      if (!user) {
        throw new Error('User not found');
      }

      userData.user = user;

      // Export user profile additional data
      const profile = await prisma.profile.findUnique({
        where: { userId },
      });
      userData.profile = profile;

      // Export posts
      const posts = await prisma.post.findMany({
        where: { authorId: userId },
        include: {
          media: true,
          _count: {
            select: {
              likes: true,
              comments: true,
              reposts: true,
            },
          },
        },
      });
      userData.posts = posts;

      // Export comments
      const comments = await prisma.comment.findMany({
        where: { authorId: userId },
        include: {
          post: {
            select: {
              id: true,
              content: true,
            },
          },
        },
      });
      userData.comments = comments;

      // Export likes
      const likes = await prisma.like.findMany({
        where: { userId },
        include: {
          post: {
            select: {
              id: true,
              content: true,
              authorId: true,
            },
          },
        },
      });
      userData.likes = likes;

      // Export follows
      const following = await prisma.follow.findMany({
        where: { followerId: userId },
        include: {
          following: {
            select: {
              id: true,
              username: true,
              name: true,
            },
          },
        },
      });

      const followers = await prisma.follow.findMany({
        where: { followingId: userId },
        include: {
          follower: {
            select: {
              id: true,
              username: true,
              name: true,
            },
          },
        },
      });

      userData.follows = { following, followers };

      // Export messages
      const messages = await prisma.message.findMany({
        where: {
          OR: [
            { senderId: userId },
            { receiverId: userId },
          ],
        },
        include: {
          sender: {
            select: {
              id: true,
              username: true,
              name: true,
            },
          },
          receiver: {
            select: {
              id: true,
              username: true,
              name: true,
            },
          },
        },
      });
      userData.messages = messages;

      // Export activity logs
      const activities = await prisma.activity.findMany({
        where: { userId },
      });
      userData.activities = activities;

      // Create audit log
      await this.createAuditLog({
        userId,
        action: 'DATA_EXPORT',
        details: 'User data export completed',
        ipAddress: requestMetadata?.ipAddress,
        userAgent: requestMetadata?.userAgent,
      });

      return userData;
    } catch (error) {
      console.error('Failed to export user data:', error);
      throw new Error('Failed to export user data');
    }
  }

  async deleteUserData(userId: string, requestMetadata?: { ipAddress?: string; userAgent?: string }): Promise<void> {
    try {
      // Start transaction for complete deletion
      await prisma.$transaction(async (tx) => {
        // Delete user activities
        await tx.activity.deleteMany({
          where: { userId },
        });

        // Delete messages
        await tx.message.deleteMany({
          where: {
            OR: [
              { senderId: userId },
              { receiverId: userId },
            ],
          },
        });

        // Delete notifications
        await tx.notification.deleteMany({
          where: {
            OR: [
              { userId },
              { fromUserId: userId },
            ],
          },
        });

        // Delete follows
        await tx.follow.deleteMany({
          where: {
            OR: [
              { followerId: userId },
              { followingId: userId },
            ],
          },
        });

        // Delete likes
        await tx.like.deleteMany({
          where: { userId },
        });

        // Delete comments
        await tx.comment.deleteMany({
          where: { authorId: userId },
        });

        // Delete post media
        const userPosts = await tx.post.findMany({
          where: { authorId: userId },
          select: { id: true },
        });

        for (const post of userPosts) {
          await tx.media.deleteMany({
            where: { postId: post.id },
          });
        }

        // Delete posts
        await tx.post.deleteMany({
          where: { authorId: userId },
        });

        // Delete profile
        await tx.profile.delete({
          where: { userId },
        }).catch(() => {}); // Profile might not exist

        // Delete user sessions
        await tx.session.deleteMany({
          where: { userId },
        });

        // Finally delete the user
        await tx.user.delete({
          where: { id: userId },
        });
      });

      // Create audit log
      await this.createAuditLog({
        userId,
        action: 'DATA_DELETE',
        details: 'User data deletion completed',
        ipAddress: requestMetadata?.ipAddress,
        userAgent: requestMetadata?.userAgent,
      });
    } catch (error) {
      console.error('Failed to delete user data:', error);
      throw new Error('Failed to delete user data');
    }
  }

  packageUserDataForDownload(userData: UserData): string {
    const packagedData = {
      exportDate: new Date().toISOString(),
      dataType: 'Personal Data Export (GDPR)',
      user: {
        ...userData.user,
        dataIncluded: [
          'Profile Information',
          'Posts and Content',
          'Comments',
          'Likes and Interactions',
          'Following/Followers',
          'Messages',
          'Activity History'
        ]
      },
      profile: userData.profile,
      content: {
        posts: userData.posts,
        comments: userData.comments,
      },
      interactions: {
        likes: userData.likes,
        follows: userData.follows,
      },
      communications: {
        messages: userData.messages,
      },
      activities: userData.activities,
      metadata: {
        totalPosts: userData.posts?.length || 0,
        totalComments: userData.comments?.length || 0,
        totalLikes: userData.likes?.length || 0,
        totalMessages: userData.messages?.length || 0,
        exportFormat: 'JSON',
      }
    };

    return JSON.stringify(packagedData, null, 2);
  }

  async getAuditLogs(userId: string): Promise<AuditLogEntry[]> {
    try {
      const logs = await prisma.auditLog.findMany({
        where: { userId },
        orderBy: { timestamp: 'desc' },
      });

      return logs;
    } catch (error) {
      console.error('Failed to retrieve audit logs:', error);
      return [];
    }
  }

  validateDataExportRequest(userId: string): { isValid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (!userId || typeof userId !== 'string') {
      errors.push('Valid user ID is required');
    }

    if (userId.length < 1) {
      errors.push('User ID cannot be empty');
    }

    return {
      isValid: errors.length === 0,
      errors,
    };
  }

  async anonymizeUserData(userId: string): Promise<void> {
    try {
      await prisma.$transaction(async (tx) => {
        // Anonymize user data instead of deleting
        const anonymizedEmail = `deleted-user-${createHash('md5').update(userId).digest('hex').substring(0, 8)}@anonymized.local`;
        
        await tx.user.update({
          where: { id: userId },
          data: {
            email: anonymizedEmail,
            name: 'Deleted User',
            username: `deleted_user_${createHash('md5').update(userId).digest('hex').substring(0, 8)}`,
            bio: null,
            avatar: null,
            banner: null,
            website: null,
            location: null,
            birthDate: null,
            verified: false,
            private: true,
          },
        });

        // Anonymize posts content
        await tx.post.updateMany({
          where: { authorId: userId },
          data: {
            content: '[Content deleted by user]',
          },
        });

        // Anonymize comments
        await tx.comment.updateMany({
          where: { authorId: userId },
          data: {
            content: '[Comment deleted by user]',
          },
        });
      });

      await this.createAuditLog({
        userId,
        action: 'DATA_DELETE',
        details: 'User data anonymized',
      });
    } catch (error) {
      console.error('Failed to anonymize user data:', error);
      throw new Error('Failed to anonymize user data');
    }
  }
}

export const gdprService = new GDPRService();