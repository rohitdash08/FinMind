import { useNavigate } from 'react-router-dom';
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { HelpOverlay } from '@/components/ui/help-overlay';

export function ShortcutProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();

  useKeyboardShortcuts({
    navigate_dashboard: () => navigate('/dashboard'),
    navigate_budgets: () => navigate('/budgets'),
    navigate_bills: () => navigate('/bills'),
    navigate_expenses: () => navigate('/expenses'),
    navigate_analytics: () => navigate('/analytics'),
    navigate_reminders: () => navigate('/reminders'),
    navigate_search: () => navigate('/search'),
    navigate_review: () => navigate('/review'),
    navigate_account: () => navigate('/account'),
    search_focus: () => {
      const input = document.querySelector<HTMLInputElement>('#search-query, [aria-label="search"], input[type="search"]');
      input?.focus();
    },
    new_transaction: () => navigate('/expenses'),
  });

  return (
    <>
      {children}
      <HelpOverlay />
    </>
  );
}
