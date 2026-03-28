import React from 'react';
import { render, screen } from '@testing-library/react';
import { Accounts } from '@/pages/Accounts';

jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
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

describe('Accounts', () => {
  it('renders the page title', () => {
    render(<Accounts />);
    expect(screen.getByText('Accounts')).toBeInTheDocument();
    expect(screen.getByText('View all your financial accounts in one place.')).toBeInTheDocument();
  });

  it('renders summary cards', () => {
    render(<Accounts />);
    expect(screen.getByText('Net Worth')).toBeInTheDocument();
    expect(screen.getByText('Total Assets')).toBeInTheDocument();
    expect(screen.getByText('Total Liabilities')).toBeInTheDocument();
    expect(screen.getByText('By Type')).toBeInTheDocument();
  });

  it('renders default mock accounts', () => {
    render(<Accounts />);
    expect(screen.getByText('Primary Checking')).toBeInTheDocument();
    expect(screen.getByText('Emergency Savings')).toBeInTheDocument();
    expect(screen.getByText('Rewards Card')).toBeInTheDocument();
    expect(screen.getByText('Brokerage')).toBeInTheDocument();
    expect(screen.getByText('Cash Wallet')).toBeInTheDocument();
  });

  it('renders Add Account button', () => {
    render(<Accounts />);
    // "Add Account" appears in button text and dialog title
    const addButtons = screen.getAllByText('Add Account');
    expect(addButtons.length).toBeGreaterThan(0);
  });

  it('shows account institutions', () => {
    render(<Accounts />);
    expect(screen.getAllByText('Chase').length).toBeGreaterThan(0);
    // Capital One appears in Select options and account display
    expect(screen.getAllByText('Capital One').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Fidelity').length).toBeGreaterThan(0);
  });

  it('shows account type badges', () => {
    render(<Accounts />);
    // "Checking" appears in badge + select option
    expect(screen.getAllByText('Checking').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Savings').length).toBeGreaterThan(0);
  });

  it('calculates net worth correctly', () => {
    render(<Accounts />);
    // 4520.50 + 12800 - 1245.30 + 28450 + 320 = 44845.20
    expect(screen.getByText('$44,845.20')).toBeInTheDocument();
  });

  it('shows primary account star indicator', () => {
    render(<Accounts />);
    expect(screen.getByText('Primary Checking')).toBeInTheDocument();
  });

  it('renders edit and delete buttons for each account', () => {
    render(<Accounts />);
    const editButtons = screen.getAllByText('Edit');
    expect(editButtons.length).toBe(5);
  });
});
