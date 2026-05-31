import React from 'react';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Navbar } from '@/components/layout/Navbar';

// Mock toast
jest.mock('@/components/ui/use-toast', () => ({ useToast: () => ({ toast: jest.fn() }) }));

const renderNav = () => render(
  <BrowserRouter>
    <Navbar />
  </BrowserRouter>
);

describe('Navbar auth state', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('shows Sign In/Get Started when signed out', () => {
    renderNav();
    expect(screen.getByRole('link', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /get started/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /finmind/i })).toHaveAttribute('href', '/');
  });

  it('shows Account/Logout when signed in (token present)', () => {
    localStorage.setItem('fm_token', 'token');
    renderNav();
    expect(screen.getByRole('link', { name: /account/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /logout/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /finmind/i })).toHaveAttribute('href', '/dashboard');
  });

  it('logout clears token and returns to signed-out state', async () => {
    localStorage.setItem('fm_token', 'token');
    renderNav();
    const btn = screen.getByRole('button', { name: /logout/i });
    btn.click();
    // After logout, token should be removed and Sign In should appear again
    await screen.findByRole('link', { name: /sign in/i });
    expect(localStorage.getItem('fm_token')).toBeNull();
  });
});
