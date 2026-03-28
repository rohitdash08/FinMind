import React from 'react';
import { render, screen } from '@testing-library/react';
import { WeeklySummaryPage } from '@/pages/WeeklySummary';

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
jest.mock('@/components/ui/input', () => ({
  Input: ({ ...props }: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));
jest.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.PropsWithChildren & React.LabelHTMLAttributes<HTMLLabelElement>) => (
    <label {...props}>{children}</label>
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

describe('WeeklySummaryPage', () => {
  it('renders the page title', () => {
    render(<WeeklySummaryPage />);
    expect(screen.getByText('Weekly Summary')).toBeInTheDocument();
    expect(screen.getByText('Financial trends and insights at a glance.')).toBeInTheDocument();
  });

  it('renders summary cards', () => {
    render(<WeeklySummaryPage />);
    // Income appears in summary card AND trend legend; use getAllByText
    expect(screen.getAllByText('Income').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Expenses').length).toBeGreaterThan(0);
    expect(screen.getByText('Net Savings')).toBeInTheDocument();
    expect(screen.getByText('Budget')).toBeInTheDocument();
  });

  it('renders spending by category section', () => {
    render(<WeeklySummaryPage />);
    expect(screen.getByText('Spending by Category')).toBeInTheDocument();
  });

  it('renders insights section', () => {
    render(<WeeklySummaryPage />);
    expect(screen.getByText('Insights & Tips')).toBeInTheDocument();
  });

  it('renders 12-week trend chart', () => {
    render(<WeeklySummaryPage />);
    expect(screen.getByText('12-Week Trend')).toBeInTheDocument();
    expect(screen.getByText('Income vs Expenses over the past 12 weeks')).toBeInTheDocument();
  });

  it('renders week navigation', () => {
    render(<WeeklySummaryPage />);
    expect(screen.getByText('Current')).toBeInTheDocument();
  });

  it('displays category breakdown items', () => {
    render(<WeeklySummaryPage />);
    expect(screen.getByText('Housing')).toBeInTheDocument();
    expect(screen.getByText('Food')).toBeInTheDocument();
    expect(screen.getByText('Transportation')).toBeInTheDocument();
  });

  it('shows budget status badge', () => {
    render(<WeeklySummaryPage />);
    const budgetBadges = screen.getAllByText(/Under Budget|On Track|Over Budget/);
    expect(budgetBadges.length).toBeGreaterThan(0);
  });

  it('renders trend legend', () => {
    render(<WeeklySummaryPage />);
    // Income and Expenses appear in summary cards AND legend
    expect(screen.getAllByText('Income').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Expenses').length).toBeGreaterThan(0);
  });

  it('formats currency amounts', () => {
    render(<WeeklySummaryPage />);
    const dollarElements = screen.getAllByText(/\$[\d,]+/);
    expect(dollarElements.length).toBeGreaterThan(0);
  });
});
