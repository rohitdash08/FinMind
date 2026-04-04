import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import WeeklyDigest from '@/pages/WeeklyDigest';

const getWeeklyDigestMock = jest.fn();
jest.mock('@/api/digest', () => ({
  getWeeklyDigest: (...args: unknown[]) => getWeeklyDigestMock(...args),
}));

// Recharts uses ResizeObserver
beforeAll(() => {
  (globalThis as any).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
});

describe('WeeklyDigest integration', () => {
  beforeEach(() => jest.clearAllMocks());

  it('renders digest data from backend', async () => {
    getWeeklyDigestMock.mockResolvedValue({
      total_spent: 420.5,
      last_week_total: 350,
      pct_change: 20.1,
      top_categories: [
        { name: 'Food', amount: 200 },
        { name: 'Transport', amount: 120 },
      ],
      biggest_expense: { description: 'Groceries', amount: 95.0, date: '2026-04-02' },
      savings_rate: 35.2,
      insight: 'Keep it up!',
      week_start: '2026-03-29',
      week_end: '2026-04-04',
    });

    render(
      <MemoryRouter initialEntries={['/weekly-digest']}>
        <Routes>
          <Route path="/weekly-digest" element={<WeeklyDigest />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getWeeklyDigestMock).toHaveBeenCalled());
    expect(screen.getByText(/weekly digest/i)).toBeInTheDocument();
    expect(screen.getByText('$420.50')).toBeInTheDocument();
    expect(screen.getByText('+20.1%')).toBeInTheDocument();
    expect(screen.getByText('35.2%')).toBeInTheDocument();
    expect(screen.getByText(/groceries/i)).toBeInTheDocument();
    expect(screen.getByText(/keep it up/i)).toBeInTheDocument();
  });

  it('shows error on failure', async () => {
    getWeeklyDigestMock.mockRejectedValue(new Error('Network error'));

    render(
      <MemoryRouter initialEntries={['/weekly-digest']}>
        <Routes>
          <Route path="/weekly-digest" element={<WeeklyDigest />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/network error/i)).toBeInTheDocument());
  });
});
