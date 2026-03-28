import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SavingsGoals } from '@/pages/SavingsGoals';

const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
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
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
jest.mock('@/components/ui/alert-dailog', () => ({
  AlertDialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));
jest.mock('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value }: React.PropsWithChildren & { value: string }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
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
  FinancialCardFooter: ({ children, className }: React.PropsWithChildren & { className?: string }) => (
    <div className={className}>{children}</div>
  ),
}));

describe('SavingsGoals', () => {
  beforeEach(() => {
    toastMock.mockClear();
  });

  it('renders the page title and summary cards', () => {
    render(<SavingsGoals />);

    expect(screen.getByText('Savings Goals')).toBeInTheDocument();
    expect(screen.getByText('Total Saved')).toBeInTheDocument();
    expect(screen.getByText('Monthly Savings')).toBeInTheDocument();
    // "On Track" appears both as summary label and as badge; use getAllByText
    expect(screen.getAllByText('On Track').length).toBeGreaterThan(0);
    expect(screen.getByText('Needs Attention')).toBeInTheDocument();
  });

  it('renders default savings goals', () => {
    render(<SavingsGoals />);

    // "Emergency Fund" appears both as goal name and category option; use getAllByText
    expect(screen.getAllByText('Emergency Fund').length).toBeGreaterThan(0);
    expect(screen.getByText('Vacation to Japan')).toBeInTheDocument();
    expect(screen.getByText('New Car Down Payment')).toBeInTheDocument();
  });

  it('displays progress information for each goal', () => {
    render(<SavingsGoals />);

    // Check that percentage complete is shown
    expect(screen.getByText('72.5% complete')).toBeInTheDocument();
    expect(screen.getByText('36.0% complete')).toBeInTheDocument();
    expect(screen.getByText('21.3% complete')).toBeInTheDocument();
  });

  it('renders the New Goal button', () => {
    render(<SavingsGoals />);

    expect(screen.getByText('New Goal')).toBeInTheDocument();
  });

  it('renders contribute buttons for each goal', () => {
    render(<SavingsGoals />);

    // 3 goal cards + 1 contribute dialog button = 4
    const contributeButtons = screen.getAllByText('Contribute');
    expect(contributeButtons.length).toBeGreaterThanOrEqual(3);
  });

  it('shows milestone indicators for each goal', () => {
    render(<SavingsGoals />);

    // Emergency Fund is at 72.5%, so should show 25% and 50% as reached
    expect(screen.getAllByText('25%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('50%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('75%').length).toBeGreaterThan(0);
  });

  it('shows on-track or behind status badges', () => {
    render(<SavingsGoals />);

    const badges = screen.getAllByText(/On Track|Behind|Completed/);
    expect(badges.length).toBeGreaterThan(0);
  });

  it('calculates summary correctly with mock data', () => {
    render(<SavingsGoals />);

    // Total saved: 7250 + 1800 + 3200 = 12250
    expect(screen.getByText('$12,250')).toBeInTheDocument();

    // Monthly total: 500 + 400 + 600 = 1500
    expect(screen.getByText('$1,500')).toBeInTheDocument();
  });
});
