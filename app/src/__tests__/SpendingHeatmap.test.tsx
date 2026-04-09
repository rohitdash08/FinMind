import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SpendingHeatmap } from '@/components/insights/SpendingHeatmap';
import { getSpendingHeatmap } from '@/api/insights';
import { format, subDays, startOfMonth, endOfMonth, subMonths, addMonths } from 'date-fns';

// Mock the API call
jest.mock('@/api/insights', () => ({
  getSpendingHeatmap: jest.fn(),
}));

const mockGetSpendingHeatmap = getSpendingHeatmap as jest.Mock;

const queryClient = new QueryClient();

const renderComponent = () =>
  render(
    <QueryClientProvider client={queryClient}>
      <SpendingHeatmap />
    </QueryClientProvider>
  );

describe('SpendingHeatmap', () => {
  const defaultEndDate = new Date();
  const defaultStartDate = startOfMonth(subMonths(defaultEndDate, 2));

  beforeEach(() => {
    queryClient.clear(); // Clear cache before each test
    jest.clearAllMocks();
  });

  it('renders loading state initially', () => {
    mockGetSpendingHeatmap.mockReturnValue(new Promise(() => {})); // Never resolve
    renderComponent();
    expect(screen.getByText(/loading spending data/i)).toBeInTheDocument();
  });

  it('renders error state if data fetching fails', async () => {
    mockGetSpendingHeatmap.mockRejectedValue(new Error('Failed to fetch'));
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText(/error loading data: failed to fetch/i)).toBeInTheDocument();
    });
  });

  it('renders heatmap with data', async () => {
    const mockData = [
      { date: format(subDays(defaultEndDate, 5), 'yyyy-MM-dd'), total_amount: 100 },
      { date: format(subDays(defaultEndDate, 3), 'yyyy-MM-dd'), total_amount: 250 },
      { date: format(defaultEndDate, 'yyyy-MM-dd'), total_amount: 50 },
    ];
    mockGetSpendingHeatmap.mockResolvedValue(mockData);

    renderComponent();

    // Check for title and description
    await waitFor(() => {
      expect(screen.getByText(/spending trend heatmap/i)).toBeInTheDocument();
      expect(screen.getByText(/visualize your spending intensity over time/i)).toBeInTheDocument();
    });

    // Check if the API was called with default dates
    expect(mockGetSpendingHeatmap).toHaveBeenCalledWith({
      startDate: format(defaultStartDate, 'yyyy-MM-dd'),
      endDate: format(defaultEndDate, 'yyyy-MM-dd'),
    });

    // Check if day numbers are rendered (e.g., today's day number)
    // This is a bit tricky due to dynamic dates. Let's check for specific amounts instead.
    await waitFor(() => {
      expect(screen.getByTitle(`${format(subDays(defaultEndDate, 5), 'MMM dd, yyyy')}: $100.00`)).toBeInTheDocument();
      expect(screen.getByTitle(`${format(subDays(defaultEndDate, 3), 'MMM dd, yyyy')}: $250.00`)).toBeInTheDocument();
      expect(screen.getByTitle(`${format(defaultEndDate, 'MMM dd, yyyy')}: $50.00`)).toBeInTheDocument();
    });
  });

  it('allows changing date range via navigation buttons', async () => {
    mockGetSpendingHeatmap.mockResolvedValue([]); // Mock empty data for navigation
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/spending trend heatmap/i)).toBeInTheDocument();
    });

    const prevButton = screen.getByRole('button', { name: /previous/i });
    const nextButton = screen.getByRole('button', { name: /next/i });

    // Click previous month
    prevButton.click();

    // Expect API call with updated date range
    await waitFor(() => {
      const expectedPrevStartDate = startOfMonth(subMonths(defaultStartDate, 1));
      const expectedPrevEndDate = endOfMonth(subMonths(defaultEndDate, 1));
      expect(mockGetSpendingHeatmap).toHaveBeenCalledWith(
        expect.objectContaining({
          startDate: format(expectedPrevStartDate, 'yyyy-MM-dd'),
          endDate: format(expectedPrevEndDate, 'yyyy-MM-dd'),
        }),
      );
    });

    // Click next month (back to default)
    nextButton.click();
    await waitFor(() => {
        expect(mockGetSpendingHeatmap).toHaveBeenCalledWith(
            expect.objectContaining({
                startDate: format(defaultStartDate, 'yyyy-MM-dd'),
                endDate: format(defaultEndDate, 'yyyy-MM-dd'),
            }),
        );
    });

    // Click next month again (one month ahead of default)
    nextButton.click();
    await waitFor(() => {
        const expectedNextStartDate = startOfMonth(addMonths(defaultStartDate, 1));
        const expectedNextEndDate = endOfMonth(addMonths(defaultEndDate, 1));
        expect(mockGetSpendingHeatmap).toHaveBeenCalledWith(
            expect.objectContaining({
                startDate: format(expectedNextStartDate, 'yyyy-MM-dd'),
                endDate: format(expectedNextEndDate, 'yyyy-MM-dd'),
            }),
        );
    });
  });
});
