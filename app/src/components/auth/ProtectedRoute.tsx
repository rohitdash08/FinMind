import { Navigate, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  getToken,
  getRefreshToken,
  setToken,
  clearToken,
  clearRefreshToken,
  setCurrency,
} from '../../lib/auth';
import { type ReactNode } from 'react';
import { me, refresh } from '@/api/auth';

type Props = { children: ReactNode };

export function ProtectedRoute({ children }: Props) {
  const loc = useLocation();
  const [status, setStatus] = useState<'checking' | 'authed' | 'guest'>('checking');

  useEffect(() => {
    let active = true;
    const checkAuth = async () => {
      const access = getToken();
      if (access) {
        try {
          const profile = await me();
          setCurrency(profile.preferred_currency || 'INR');
        } catch {
          // Keep current local currency if profile fetch fails.
        }
        if (active) setStatus('authed');
        return;
      }
      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        if (active) setStatus('guest');
        return;
      }
      try {
        const data = await refresh(refreshToken);
        setToken(data.access_token);
        try {
          const profile = await me();
          setCurrency(profile.preferred_currency || 'INR');
        } catch {
          // Keep current local currency if profile fetch fails.
        }
        if (active) setStatus('authed');
      } catch {
        clearToken();
        clearRefreshToken();
        if (active) setStatus('guest');
      }
    };
    void checkAuth();
    return () => {
      active = false;
    };
  }, []);

  if (status === 'checking') {
    return null;
  }
  if (status === 'guest') {
    return <Navigate to="/signin" replace state={{ from: loc }} />;
  }
  return <>{children}</>;
}

export default ProtectedRoute;
