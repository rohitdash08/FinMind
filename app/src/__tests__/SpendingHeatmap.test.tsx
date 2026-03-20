import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  FinancialCardTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
}));

const getSpendingHeatmapMock = jest.fn();
jest.mock('@/api/expenses', () => ({
  getSpendingHeatmap: (...args: unknown[]) => getSpendingHeatmapMock(...args),
}));

import { SpendingHeatmap } from '@/components/ui/SpendingHeatmap';

describe('SpendingHeatmap', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows loading state initially', () => {
    getSpendingHeatmapMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<SpendingHeatmap />);
    expect(screen.getByText(/loading heatmap/i)).toBeInTheDocument();
  });

  it('renders heatmap grid with data', async () => {
    const today = new Date().toISOString().slice(0, 10);
    getSpendingHeatmapMock.mockResolvedValue([
      { date: today, amount: 42.5 },
    ]);

    render(<SpendingHeatmap />);
    await waitFor(() => {
      expect(screen.getByTestId('heatmap-grid')).toBeInTheDocument();
    });

    // Should render 52 * 7 = 364 cells
    const cells = screen.getAllByTestId('heatmap-cell');
    expect(cells.length).toBe(364);
  });

  it('shows tooltip on hover', async () => {
    const today = new Date().toISOString().slice(0, 10);
    getSpendingHeatmapMock.mockResolvedValue([
      { date: today, amount: 25.0 },
    ]);

    render(<SpendingHeatmap />);
    await waitFor(() => {
      expect(screen.getByTestId('heatmap-grid')).toBeInTheDocument();
    });

    const cells = screen.getAllByTestId('heatmap-cell');
    fireEvent.mouseEnter(cells[cells.length - 1]); // last cell is today
    expect(screen.getByTestId('heatmap-tooltip')).toBeInTheDocument();

    fireEvent.mouseLeave(cells[cells.length - 1]);
    expect(screen.queryByTestId('heatmap-tooltip')).not.toBeInTheDocument();
  });

  it('shows error state on API failure', async () => {
    getSpendingHeatmapMock.mockRejectedValue(new Error('Network error'));

    render(<SpendingHeatmap />);
    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('renders legend', async () => {
    getSpendingHeatmapMock.mockResolvedValue([]);

    render(<SpendingHeatmap />);
    await waitFor(() => {
      expect(screen.getByTestId('heatmap-grid')).toBeInTheDocument();
    });

    expect(screen.getByText('Less')).toBeInTheDocument();
    expect(screen.getByText('More')).toBeInTheDocument();
  });
});
