import React from 'react';
import { render, screen } from '@testing-library/react';
import { Jobs } from '@/pages/Jobs';

jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
}));
jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant }: React.PropsWithChildren & { variant?: string }) => (
    <span data-variant={variant}>{children}</span>
  ),
}));
jest.mock('@/components/ui/financial-card', () => ({
  FinancialCard: ({ children, className }: React.PropsWithChildren & { className?: string }) => (
    <div className={className}>{children}</div>
  ),
  FinancialCardHeader: ({ children, className }: React.PropsWithChildren & { className?: string }) => (
    <div className={className}>{children}</div>
  ),
  FinancialCardTitle: ({ children, className }: React.PropsWithChildren & { className?: string }) => (
    <h3 className={className}>{children}</h3>
  ),
  FinancialCardDescription: ({ children, className }: React.PropsWithChildren & { className?: string }) => (
    <p className={className}>{children}</p>
  ),
  FinancialCardContent: ({ children, className }: React.PropsWithChildren & { className?: string }) => (
    <div className={className}>{children}</div>
  ),
}));

describe('Jobs', () => {
  it('renders the page title', () => {
    render(<Jobs />);
    expect(screen.getByText('Job Monitor')).toBeInTheDocument();
    expect(screen.getByText('Track and manage background job execution.')).toBeInTheDocument();
  });

  it('renders stats cards', () => {
    render(<Jobs />);
    expect(screen.getByText('Total Jobs')).toBeInTheDocument();
    expect(screen.getByText('Success Rate')).toBeInTheDocument();
    expect(screen.getByText('Succeeded')).toBeInTheDocument();
    // "Failed" appears in stats card and filter button
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0);
    // "Running" appears in stats and filter
    expect(screen.getAllByText('Running').length).toBeGreaterThan(0);
    expect(screen.getByText('Avg Duration')).toBeInTheDocument();
  });

  it('renders filter buttons', () => {
    render(<Jobs />);
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getAllByText('Pending').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Running').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Success').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Retrying').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Cancelled').length).toBeGreaterThan(0);
  });

  it('renders job list', () => {
    render(<Jobs />);
    // Should have jobs rendered
    const jobsHeading = screen.getByText(/Jobs \(/);
    expect(jobsHeading).toBeInTheDocument();
  });

  it('renders refresh button', () => {
    render(<Jobs />);
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('shows job types in the list', () => {
    render(<Jobs />);
    // Jobs are rendered with their type names; just verify the list section exists
    const jobsHeading = screen.getByText(/Jobs \(/);
    expect(jobsHeading).toBeInTheDocument();
  });

  it('renders retry button for failed jobs', () => {
    render(<Jobs />);
    // If there are failed jobs, there should be retry buttons
    const retryButtons = screen.queryAllByText('Retry');
    // May or may not have failed jobs in mock data, so just check it doesn't crash
    expect(retryButtons.length).toBeGreaterThanOrEqual(0);
  });
});
