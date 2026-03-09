import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { login, me } from '@/api/auth';
import { setToken, setRefreshToken, setCurrency } from '@/lib/auth';
import { useToast } from '@/components/ui/use-toast';
import { checkUnusualLogin } from '@/utils/login-detection';

// Lightweight SignIn component tailored for bounty-hunt tests
export function SignIn() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();
  const location = useLocation();
  type LocState = { from?: { pathname: string } } | null;
  const from = (location?.state as unknown as LocState)?.from?.pathname ?? '/dashboard';

  const { toast } = useToast();

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await login(email.trim(), password);
      setToken(res.access_token);
      if (res.refresh_token) setRefreshToken(res.refresh_token);
      try {
        const profile = await me();
        setCurrency(profile.preferred_currency || 'INR');
        // Unusual login detection after obtaining user profile
        const isUnusual = checkUnusualLogin(profile.id, {
          userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
        });
        if (isUnusual) {
          toast({
            title: 'Unusual login detected',
            description: 'Login from a new device or location detected.',
            variant: 'warning' as const,
          });
        }
      } catch {
        // ignore profile fetch failures
      }
      toast({ title: 'Welcome back', description: 'You have successfully signed in.' });
      navigate(from, { replace: true });
    } catch (err) {
      setError('Invalid credentials');
      toast({ variant: 'destructive', title: 'Login failed' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={onSubmit} aria-label="sign-in-form">
        <div>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
          />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
          />
        </div>
        <button type="submit" disabled={loading}>
          Sign in to your account
        </button>
        {error && <div role="alert">{error}</div>}
      </form>
    </div>
  );
}
