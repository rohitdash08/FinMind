import { Outlet, useLocation } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Footer } from './Footer';
import { Toaster } from '@/components/ui/toaster';
import { ShortcutProvider } from '@/components/shortcuts/ShortcutProvider';

export function Layout() {
  const location = useLocation();
  const isAuthPage = location.pathname === '/signin' || location.pathname === '/register';
  
  return (
    <div className="min-h-screen flex flex-col">
      {!isAuthPage && <Navbar />}
      <main className="flex-1 relative">
        <ShortcutProvider>
          <Outlet />
        </ShortcutProvider>
      </main>
      {!isAuthPage && <Footer />}
      <Toaster />
    </div>
  );
}
