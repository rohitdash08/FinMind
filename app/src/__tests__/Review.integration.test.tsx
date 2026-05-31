import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Review from '@/pages/Review';

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

const getMonthlyReviewMock = jest.fn();
jest.mock('@/api/review', () => ({
  getMonthlyReview: (...args: unknown[]) => getMonthlyReviewMock(...args),
}));

function buildReviewData(overrides: Record<string, unknown> = {}) {
  return {
    period: '2026-02',
    previous_period: '2026-01',
    current: {
      total_income: 5000,
      total_expenses: 3500,
      net_flow: 1500,
      transaction_count: 12,
      categories: [
        { name: 'Food', amount: 1200 },
        { name: 'Transport', amount: 800 },
        { name: 'Entertainment', amount: 500 },
      ],
      bills_total: 300,
    },
    previous: {
      total_income: 4800,
      total_expenses: 4000,
      net_flow: 800,
      transaction_count: 10,
      categories: [
        { name: 'Rent', amount: 1500 },
        { name: 'Food', amount: 1000 },
        { name: 'Transport', amount: 700 },
      ],
      bills_total: 300,
    },
    reviews: [
      {
        type: 'spending_change',
        severity: 'medium',
        title: 'Expenses decreased by 12%',
        description: 'Your expenses went from $4000.00 to $3500.00.',
        change_pct: -12.5,
      },
      {
        type: 'top_category_shift',
        severity: 'medium',
        title: 'Top category shifted to Food',
        description: 'Your biggest expense category changed from Rent to Food.',
        category: 'Food',
      },
    ],
    recommendations: [
      {
        action: 'set_budget',
        priority: 'low',
        message: 'Set up category budgets to proactively manage spending.',
      },
      {
        action: 'trend_awareness',
        priority: 'medium',
        message: 'Your spending is decreasing. Great discipline!',
        trend: 'decreasing',
      },
    ],
    ...overrides,
  };
}

describe('Review integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders review page and steps through flow', async () => {
    const user = userEvent.setup();
    getMonthlyReviewMock.mockResolvedValue(buildReviewData());

    render(
      <MemoryRouter initialEntries={['/review']}>
        <Routes>
          <Route path="/review" element={<Review />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getMonthlyReviewMock).toHaveBeenCalled());
    expect(screen.getByText(/period overview/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText(/key findings/i)).toBeInTheDocument();
    expect(screen.getByText(/expenses decreased by 12%/i)).toBeInTheDocument();
  });

  it('shows recommendations after findings', async () => {
    const user = userEvent.setup();
    getMonthlyReviewMock.mockResolvedValue(buildReviewData());

    render(
      <MemoryRouter initialEntries={['/review']}>
        <Routes>
          <Route path="/review" element={<Review />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getMonthlyReviewMock).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText(/recommendations/i)).toBeInTheDocument();
    expect(screen.getByText(/set budget/i)).toBeInTheDocument();
  });

  it('shows review complete at the end', async () => {
    const user = userEvent.setup();
    getMonthlyReviewMock.mockResolvedValue(buildReviewData());

    render(
      <MemoryRouter initialEntries={['/review']}>
        <Routes>
          <Route path="/review" element={<Review />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getMonthlyReviewMock).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText(/review complete/i)).toBeInTheDocument();
  });

  it('handles missing data gracefully', async () => {
    getMonthlyReviewMock.mockResolvedValue(buildReviewData({
      reviews: [],
      recommendations: [],
    }));

    render(
      <MemoryRouter initialEntries={['/review']}>
        <Routes>
          <Route path="/review" element={<Review />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getMonthlyReviewMock).toHaveBeenCalled());
    expect(screen.getByText(/period overview/i)).toBeInTheDocument();
  });
});
