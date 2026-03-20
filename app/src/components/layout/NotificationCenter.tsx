import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Bell, Check, CheckCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  type NotificationItem,
  type NotificationPriority,
} from '@/api/notifications';
import { getToken } from '@/lib/auth';

const PRIORITY_STYLES: Record<NotificationPriority, string> = {
  critical: 'bg-red-100 text-red-800 border-red-200',
  high: 'bg-orange-100 text-orange-800 border-orange-200',
  medium: 'bg-blue-100 text-blue-800 border-blue-200',
  low: 'bg-gray-100 text-gray-600 border-gray-200',
};

const GROUP_LABELS: Record<string, string> = {
  bills: 'Bills & Payments',
  budgets: 'Budget Alerts',
  savings: 'Savings Opportunities',
  summary: 'Weekly Summary',
};

// Sort groups by priority: budgets (critical) first, then bills, savings, summary
const GROUP_ORDER = ['budgets', 'bills', 'savings', 'summary'];

function PriorityBadge({ priority }: { priority: NotificationPriority }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${PRIORITY_STYLES[priority]}`}
    >
      {priority}
    </span>
  );
}

function NotificationRow({
  notification,
  onMarkRead,
}: {
  notification: NotificationItem;
  onMarkRead: (id: number) => void;
}) {
  return (
    <div
      className={`flex items-start gap-2 rounded-lg px-3 py-2 text-sm transition ${
        notification.read ? 'opacity-60' : 'bg-muted/40'
      }`}
    >
      <div className="flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <PriorityBadge priority={notification.priority} />
          <span className="text-[11px] text-muted-foreground">
            {new Date(notification.created_at).toLocaleDateString()}
          </span>
        </div>
        <p className="text-xs leading-relaxed text-foreground">{notification.message}</p>
      </div>
      {!notification.read && (
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          onClick={() => onMarkRead(notification.id)}
          title="Mark as read"
        >
          <Check className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const isAuthed = !!getToken();

  const { data } = useQuery({
    queryKey: ['notifications'],
    queryFn: listNotifications,
    enabled: isAuthed && open,
    refetchInterval: open ? 30_000 : false,
  });

  // Also poll unread count when popover is closed
  const { data: countData } = useQuery({
    queryKey: ['notifications-count'],
    queryFn: listNotifications,
    enabled: isAuthed,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const unreadCount = data?.unread_count ?? countData?.unread_count ?? 0;
  const groups = data?.notifications ?? {};

  const markReadMutation = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      void queryClient.invalidateQueries({ queryKey: ['notifications-count'] });
    },
  });

  const markAllMutation = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      void queryClient.invalidateQueries({ queryKey: ['notifications-count'] });
    },
  });

  const handleMarkRead = useCallback(
    (id: number) => {
      markReadMutation.mutate(id);
    },
    [markReadMutation],
  );

  if (!isAuthed) return null;

  const sortedGroups = GROUP_ORDER.filter((g) => groups[g]?.length);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative h-9 w-9">
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center p-0 text-[10px]"
            >
              {unreadCount > 99 ? '99+' : unreadCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px] p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h3 className="text-sm font-semibold">Notifications</h3>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => markAllMutation.mutate()}
            >
              <CheckCheck className="h-3.5 w-3.5" />
              Mark all read
            </Button>
          )}
        </div>
        <ScrollArea className="max-h-[400px]">
          {sortedGroups.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              No notifications
            </div>
          ) : (
            <div className="space-y-1 p-2">
              {sortedGroups.map((groupKey) => (
                <div key={groupKey}>
                  <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {GROUP_LABELS[groupKey] ?? groupKey}
                  </div>
                  {groups[groupKey].map((n) => (
                    <NotificationRow key={n.id} notification={n} onMarkRead={handleMarkRead} />
                  ))}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}
