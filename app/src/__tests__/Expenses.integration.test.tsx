import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Expenses from '@/pages/Expenses';

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
jest.mock('@/components/ui/pagination', () => ({
  Pagination: ({ children }: React.PropsWithChildren) => <nav>{children}</nav>,
  PaginationContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  PaginationItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  PaginationLink: ({ children }: React.PropsWithChildren) => <a href="#">{children}</a>,
  PaginationNext: ({ ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a href="#" {...props}>Next</a>,
  PaginationPrevious: ({ ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a href="#" {...props}>Prev</a>,
}));

const listExpensesMock = jest.fn();
const createExpenseMock = jest.fn();
const updateExpenseMock = jest.fn();
const deleteExpenseMock = jest.fn();
const previewImportMock = jest.fn();
const commitImportMock = jest.fn();
const listRecurringMock = jest.fn();
const createRecurringMock = jest.fn();
const generateRecurringMock = jest.fn();
jest.mock('@/api/expenses', () => ({
  listExpenses: (...args: unknown[]) => listExpensesMock(...args),
  createExpense: (...args: unknown[]) => createExpenseMock(...args),
  updateExpense: (...args: unknown[]) => updateExpenseMock(...args),
  deleteExpense: (...args: unknown[]) => deleteExpenseMock(...args),
  previewExpenseImport: (...args: unknown[]) => previewImportMock(...args),
  commitExpenseImport: (...args: unknown[]) => commitImportMock(...args),
  listRecurringExpenses: (...args: unknown[]) => listRecurringMock(...args),
  createRecurringExpense: (...args: unknown[]) => createRecurringMock(...args),
  generateRecurringExpenses: (...args: unknown[]) => generateRecurringMock(...args),
}));

const listCategoriesMock = jest.fn();
jest.mock('@/api/categories', () => ({
  listCategories: (...args: unknown[]) => listCategoriesMock(...args),
}));

describe('Expenses page integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    listExpensesMock.mockResolvedValue([]);
    listCategoriesMock.mockResolvedValue([{ id: 1, name: 'Food' }]);
    createExpenseMock.mockResolvedValue({
      id: 10,
      amount: 20,
      description: 'Dinner',
      category_id: 1,
      date: '2026-02-15',
    });
    previewImportMock.mockResolvedValue({
      total: 1,
      duplicates: 0,
      transactions: [{ date: '2026-02-10', amount: 14.2, description: 'Taxi', category_id: null }],
    });
    commitImportMock.mockResolvedValue({ inserted: 1, duplicates: 0 });
    listRecurringMock.mockResolvedValue([]);
    createRecurringMock.mockResolvedValue({
      id: 77,
      amount: 100,
      currency: 'INR',
      expense_type: 'EXPENSE',
      category_id: null,
      description: 'Gym',
      cadence: 'MONTHLY',
      start_date: '2026-02-01',
      end_date: null,
      active: true,
    });
    generateRecurringMock.mockResolvedValue({ inserted: 1 });
  });

  it('creates expense from quick add form', async () => {
    render(<Expenses />);
    await waitFor(() => expect(listExpensesMock).toHaveBeenCalled());

    const amountInput = document.getElementById('q-amount') as HTMLInputElement;
    const descInput = document.getElementById('q-description') as HTMLInputElement;
    await userEvent.type(amountInput, '20');
    await userEvent.type(descInput, 'Dinner');
    await userEvent.click(screen.getByRole('button', { name: /save expense/i }));

    await waitFor(() => expect(createExpenseMock).toHaveBeenCalled());
    expect(createExpenseMock).toHaveBeenCalledWith(
      expect.objectContaining({ amount: 20, description: 'Dinner' }),
    );
  });

  it('previews and confirms statement import', async () => {
    render(<Expenses />);
    await waitFor(() => expect(listExpensesMock).toHaveBeenCalled());

    const file = new File(['date,amount,description\n2026-02-10,14.2,Taxi'], 'statement.csv', {
      type: 'text/csv',
    });
    const input = screen.getByLabelText(/statement file/i) as HTMLInputElement;
    await userEvent.upload(input, file);

    await userEvent.click(screen.getByRole('button', { name: /preview import/i }));
    await waitFor(() => expect(previewImportMock).toHaveBeenCalled());
    expect(screen.getByText(/preview rows:/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /confirm import/i }));
    await waitFor(() => expect(commitImportMock).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ description: 'Taxi', amount: 14.2 }),
      ]),
    ));
  });

  it('creates recurring expense from recurring form', async () => {
    render(<Expenses />);
    await waitFor(() => expect(listExpensesMock).toHaveBeenCalled());

    await userEvent.type(screen.getByLabelText(/recurring amount/i), '100');
    await userEvent.type(screen.getByLabelText(/recurring description/i), 'Gym');
    await userEvent.click(screen.getByRole('button', { name: /add recurring/i }));

    await waitFor(() => expect(createRecurringMock).toHaveBeenCalled());
    expect(createRecurringMock).toHaveBeenCalledWith(
      expect.objectContaining({
        amount: 100,
        description: 'Gym',
        cadence: 'MONTHLY',
      }),
    );
  });
});
