import { Outlet, useLocation } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Footer } from './Footer';
import { Toaster } from '@/components/ui/toaster';
import { useShortcuts } from '@/hooks/use-shortcuts';
import { ShortcutHelpModal } from '@/components/shortcut-help-modal';

export function Layout() {
  const location = useLocation();
  const isAuthPage = location.pathname === '/signin' || location.pathname === '/register';
  
  const { isHelpOpen, setIsHelpOpen, shortcuts } = useShortcuts();

  return (
    <div className="min-h-screen flex flex-col">
      {!isAuthPage && <Navbar />}
      <main className="flex-1 relative">
        <Outlet />
      </main>
      {!isAuthPage && <Footer />}
      <Toaster />
      <ShortcutHelpModal 
        isOpen={isHelpOpen} 
        onOpenChange={setIsHelpOpen} 
        shortcuts={shortcuts} 
      />
    </div>
  );
}
