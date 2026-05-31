import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import SearchPage from '@/pages/Search';

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

const searchMock = jest.fn();
const listCategoriesMock = jest.fn();
jest.mock('@/api/search', () => ({
  search: (...args: unknown[]) => searchMock(...args),
  getSavedSearches: () => [],
  saveSearch: (...args: unknown[]) => { return [{ id: 's1', name: args[0], params: args[1], created_at: new Date().toISOString() }]; },
  deleteSavedSearch: (id: string) => [],
}));

jest.mock('@/api/categories', () => ({
  listCategories: (...args: unknown[]) => listCategoriesMock(...args),
}));

describe('Search integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    listCategoriesMock.mockResolvedValue([{ id: 1, name: 'Food' }]);
    searchMock.mockResolvedValue({
      transactions: [
        { id: 1, type: 'expense', description: 'Test Expense', amount: 100, date: '2026-02-15', expense_type: 'EXPENSE', category_id: null, currency: 'USD' },
      ],
      bills: [
        { id: 1, type: 'bill', name: 'Test Bill', amount: 200, next_due_date: '2026-03-01', cadence: 'MONTHLY', currency: 'USD' },
      ],
      total_count: 2,
    });
  });

  it('renders search page with filters', async () => {
    render(
      <MemoryRouter initialEntries={['/search']}>
        <Routes>
          <Route path="/search" element={<SearchPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(listCategoriesMock).toHaveBeenCalled());
    expect(screen.getByText(/advanced search/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search transactions/i)).toBeInTheDocument();
  });

  it('performs search and shows results', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/search']}>
        <Routes>
          <Route path="/search" element={<SearchPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(listCategoriesMock).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /search/i }));
    await waitFor(() => expect(searchMock).toHaveBeenCalled());
    expect(screen.getByText(/test expense/i)).toBeInTheDocument();
    expect(screen.getByText(/test bill/i)).toBeInTheDocument();
  });
});
