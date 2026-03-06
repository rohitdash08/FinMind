import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Menu, X, TrendingUp, ShieldCheck } from 'lucide-react';
import { getToken, getRefreshToken, clearToken, clearRefreshToken } from '@/lib/auth';
import { useToast } from '@/components/ui/use-toast';
import { logout as logoutApi } from '@/api/auth';

const navigation = [
  { name: 'Dashboard', href: '/dashboard' },
  { name: 'Budgets', href: '/budgets' },
  { name: 'Bills', href: '/bills' },
  { name: 'Reminders', href: '/reminders' },
  { name: 'Expenses', href: '/expenses' },
  { name: 'Savings', href: '/savings' },
  { name: 'Analytics', href: '/analytics' },
];

export function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const [isAuthed, setIsAuthed] = useState<boolean>(!!getToken());
  const location = useLocation();
  const nav = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    const onChange = () => setIsAuthed(!!getToken());
    window.addEventListener('auth_changed', onChange);
    onChange();
    return () => window.removeEventListener('auth_changed', onChange);
  }, []);

  const handleLogout = async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await logoutApi(refreshToken);
      } catch {
        // Best-effort revoke; proceed with local logout regardless.
      }
    }
    clearToken();
    clearRefreshToken();
    toast({ title: 'Signed out', description: 'You have been logged out.' });
    nav('/signin');
  };
  const brandHref = isAuthed ? '/dashboard' : '/';

  return (
    <nav className="glass-nav">
      <div className="absolute inset-0 bg-gradient-to-r from-primary/8 via-transparent to-accent/10 pointer-events-none" />
      <div className="container-financial relative">
        <div className="flex h-16 items-center justify-between">
          <Link to={brandHref} className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-hero text-primary-foreground shadow-primary">
              <TrendingUp className="h-5 w-5" />
            </div>
            <div>
              <div className="text-base font-extrabold leading-none">FinMind</div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Money OS</div>
            </div>
          </Link>

          <div className="hidden items-center gap-1 md:flex">
            {navigation.map((item) => {
              const active = location.pathname === item.href;
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={
                    active
                      ? 'rounded-full bg-secondary px-4 py-2 text-xs font-semibold text-secondary-foreground shadow-sm'
                      : 'rounded-full px-4 py-2 text-xs font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground'
                  }
                >
                  {item.name}
                </Link>
              );
            })}
          </div>

          <div className="hidden items-center gap-3 md:flex">
            <div className="flex items-center gap-1 rounded-full border border-border/70 bg-white/70 px-3 py-1 text-[11px] text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 text-primary" />
              Enterprise-grade security
            </div>
            {isAuthed ? (
              <>
                <Button variant="outline" size="sm" asChild>
                  <Link to="/account">Account</Link>
                </Button>
                <Button variant="hero" size="sm" onClick={() => { void handleLogout(); }}>
                  Logout
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" size="sm" asChild>
                  <Link to="/signin">Sign In</Link>
                </Button>
                <Button variant="hero" size="sm" asChild>
                  <Link to="/register">Get Started</Link>
                </Button>
              </>
            )}
          </div>

          <div className="md:hidden">
            <Button variant="ghost" size="icon" onClick={() => setIsOpen((v) => !v)}>
              {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </div>
        </div>

        {isOpen && (
          <div className="md:hidden pb-4">
            <div className="space-y-2 rounded-2xl border border-border/60 bg-white/90 p-3 shadow-md">
              {navigation.map((item) => {
                const active = location.pathname === item.href;
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    onClick={() => setIsOpen(false)}
                    className={
                      active
                        ? 'block rounded-lg bg-secondary px-3 py-2 text-sm font-medium text-secondary-foreground'
                        : 'block rounded-lg px-3 py-2 text-sm font-medium text-foreground hover:bg-muted'
                    }
                  >
                    {item.name}
                  </Link>
                );
              })}
              <div className="grid grid-cols-2 gap-2 pt-2">
                {isAuthed ? (
                  <>
                    <Button variant="outline" size="sm" asChild onClick={() => setIsOpen(false)}>
                      <Link to="/account">Account</Link>
                    </Button>
                    <Button variant="hero" size="sm" onClick={() => { setIsOpen(false); void handleLogout(); }}>
                      Logout
                    </Button>
                  </>
                ) : (
                  <>
                    <Button variant="outline" size="sm" asChild onClick={() => setIsOpen(false)}>
                      <Link to="/signin">Sign In</Link>
                    </Button>
                    <Button variant="hero" size="sm" asChild onClick={() => setIsOpen(false)}>
                      <Link to="/register">Get Started</Link>
                    </Button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
