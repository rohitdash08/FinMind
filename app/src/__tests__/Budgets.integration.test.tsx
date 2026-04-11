import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Budgets } from '@/pages/Budgets';

describe('Budgets savings goals', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('renders responsive savings goal progress with visible percentages', () => {
    render(<Budgets />);

    expect(screen.getByRole('heading', { name: /savings goals/i })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /emergency fund progress/i })).toHaveAttribute('aria-valuenow', '73');
    expect(screen.getByLabelText(/emergency fund progress percentage/i)).toHaveTextContent('73%');
    expect(screen.getAllByText(/next milestone 75%/i).length).toBeGreaterThan(0);
  });

  it('adds a new savings goal and persists it locally', async () => {
    const user = userEvent.setup();
    render(<Budgets />);

    await user.type(screen.getByLabelText(/goal name/i), 'House Deposit');
    await user.type(screen.getByLabelText(/target amount/i), '50000');
    const savedSoFarInput = screen.getByLabelText(/saved so far/i);
    await user.clear(savedSoFarInput);
    await user.type(savedSoFarInput, '12000');
    await user.clear(screen.getByLabelText(/target date/i));
    await user.type(screen.getByLabelText(/target date/i), '2027-12-31');
    await user.click(screen.getByRole('button', { name: /add new goal/i }));

    expect(screen.getByText('House Deposit')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /house deposit progress/i })).toHaveAttribute('aria-valuenow', '24');

    const stored = window.localStorage.getItem('finmind.savings-goals');
    expect(stored).toContain('House Deposit');
  });
});
