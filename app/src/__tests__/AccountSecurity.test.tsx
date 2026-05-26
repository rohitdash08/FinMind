import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Account from '@/pages/Account';

const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

jest.mock('@/api/auth', () => ({
  acknowledgeSecurityAlert: jest.fn(),
  getSecurityAlerts: jest.fn(),
  me: jest.fn(),
  updateMe: jest.fn(),
}));

jest.mock('@/lib/auth', () => ({
  setCurrency: jest.fn(),
}));

import {
  acknowledgeSecurityAlert,
  getSecurityAlerts,
  me,
  updateMe,
} from '@/api/auth';

describe('Account security alerts', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (me as jest.Mock).mockResolvedValue({
      id: 1,
      email: 'demo@finmind.local',
      preferred_currency: 'USD',
    });
    (updateMe as jest.Mock).mockResolvedValue({
      id: 1,
      email: 'demo@finmind.local',
      preferred_currency: 'USD',
    });
    (getSecurityAlerts as jest.Mock).mockResolvedValue({
      unread_count: 1,
      alerts: [
        {
          id: 7,
          login_event_id: 3,
          alert_type: 'new_device',
          severity: 'medium',
          message: 'New device or browser detected.',
          details: {
            ip_address: '203.0.113.9',
            user_agent: 'NewBrowser/2',
          },
          acknowledged: false,
          created_at: '2026-05-26T05:00:00',
        },
      ],
    });
    (acknowledgeSecurityAlert as jest.Mock).mockResolvedValue({
      id: 7,
      acknowledged: true,
    });
  });

  it('shows recent login security alerts and lets users acknowledge them', async () => {
    render(<Account />);

    expect(await screen.findByText('Security Alerts')).toBeInTheDocument();
    expect(
      screen.getByText('New device or browser detected.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/203\.0\.113\.9/)).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole('button', { name: /mark reviewed/i }),
    );

    await waitFor(() => expect(acknowledgeSecurityAlert).toHaveBeenCalledWith(7));
  });
});
