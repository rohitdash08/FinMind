import { Outlet, useLocation } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Footer } from './Footer';
import { Toaster } from '@/components/ui/toaster';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { KeyboardShortcutHelp } from '@/components/KeyboardShortcutHelp';

export function Layout() {
  const location = useLocation();
  const isAuthPage = location.pathname === '/signin' || location.pathname === '/register';
  
  const { showHelp, setShowHelp, shortcuts } = useKeyboardShortcuts();

  return (
    <div className="min-h-screen flex flex-col">
      {!isAuthPage && <Navbar />}
      <main className="flex-1 relative">
        <Outlet />
      </main>
      {!isAuthPage && <Footer />}
      <Toaster />
      <KeyboardShortcutHelp
        shortcuts={shortcuts}
        open={showHelp}
        onClose={() => setShowHelp(false)}
      />
    </div>
  );
}
