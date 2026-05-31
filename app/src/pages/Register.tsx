import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { FinancialCard, FinancialCardContent } from '@/components/ui/financial-card';
import {
  TrendingUp,
  Mail,
  Lock,
  Eye,
  EyeOff,
  ArrowRight,
  Chrome,
  Github,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useState, type FormEvent } from 'react';
import { register, login, me } from '@/api/auth';
import { setToken, setRefreshToken, setCurrency } from '@/lib/auth';
import { useToast } from '@/components/ui/use-toast';

const socialProviders = [
  { name: 'Google', icon: Chrome, description: 'Continue with Google' },
  { name: 'GitHub', icon: Github, description: 'Continue with GitHub' },
];

export function Register() {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();
  const { toast } = useToast();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!email.trim()) {
      setError('Email is required');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);
    try {
      await register(email.trim(), password);
      const auth = await login(email.trim(), password);
      setToken(auth.access_token);
      if (auth.refresh_token) setRefreshToken(auth.refresh_token);
      try {
        const profile = await me();
        setCurrency(profile.preferred_currency || 'INR');
      } catch {
        // Keep default local currency when profile fetch is unavailable.
      }
      toast({ title: 'Account created', description: 'Welcome to FinMind.' });
      nav('/dashboard', { replace: true });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to register';
      setError(message);
      toast({ variant: 'destructive', title: 'Registration failed', description: message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-shell auth-screen flex">
      <div className="hidden xl:flex flex-1 bg-gradient-to-br from-secondary via-primary to-accent relative overflow-hidden">
        <div className="absolute inset-0 opacity-20" />
        <div className="absolute -top-24 -right-16 h-72 w-72 rounded-full bg-white/20 blur-3xl" />
        <div className="absolute bottom-10 left-10 h-52 w-52 rounded-full bg-white/15 blur-2xl" />

        <div className="flex items-center justify-center p-8 relative z-10">
          <div className="max-w-lg text-white">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/15 px-3 py-1 text-xs font-semibold tracking-wide">
              <span className="h-2 w-2 rounded-full bg-emerald-300" />
              LIVE MONEY OPERATING SYSTEM
            </div>

            <h2 className="text-4xl font-extrabold leading-tight">
              Build wealth habits with
              <span className="block text-white/85">clarity, automation, and focus.</span>
            </h2>

            <p className="mt-4 text-base text-white/85">
              FinMind combines budgets, bills, and spending intelligence in one modern command center for your financial life.
            </p>

            <div className="mt-6 grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-white/25 bg-white/15 p-3 text-center backdrop-blur-sm">
                <div className="text-2xl font-extrabold">$2.8K</div>
                <div className="text-xs text-white/80">Avg yearly savings</div>
              </div>
              <div className="rounded-xl border border-white/25 bg-white/15 p-3 text-center backdrop-blur-sm">
                <div className="text-2xl font-extrabold">98%</div>
                <div className="text-xs text-white/80">Goal completion</div>
              </div>
              <div className="rounded-xl border border-white/25 bg-white/15 p-3 text-center backdrop-blur-sm">
                <div className="text-2xl font-extrabold">10k+</div>
                <div className="text-xs text-white/80">Active users</div>
              </div>
            </div>

            <div className="mt-6 rounded-2xl border border-white/25 bg-white/12 p-5 backdrop-blur-sm">
              <div className="mb-3 text-sm font-semibold text-white/90">Why teams and individuals choose FinMind</div>
              <div className="space-y-2 text-sm text-white/85">
                <div className="flex items-center justify-between rounded-lg bg-white/10 px-3 py-2">
                  <span>Automated expense intelligence</span>
                  <span className="font-bold">Real-time</span>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-white/10 px-3 py-2">
                  <span>Bill and reminder reliability</span>
                  <span className="font-bold">99.9%</span>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-white/10 px-3 py-2">
                  <span>Actionable AI summaries</span>
                  <span className="font-bold">Weekly</span>
                </div>
              </div>
              <div className="mt-4">
                <div className="mb-2 flex items-center justify-between text-xs text-white/80">
                  <span>Onboarding completion rate</span>
                  <span>96%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-white/20">
                  <div className="h-full w-[96%] rounded-full bg-white/80" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="auth-pane">
        <div className="auth-content">
          <div className="text-center mb-5">
            <Link to="/" className="inline-flex items-center space-x-2 mb-4">
              <div className="flex items-center justify-center w-10 h-10 bg-gradient-primary rounded-xl shadow-primary">
                <TrendingUp className="w-5 h-5 text-primary-foreground" />
              </div>
              <span className="text-2xl font-bold bg-gradient-hero bg-clip-text text-transparent">FinMind</span>
            </Link>
            <h1 className="text-2xl font-bold text-foreground mb-1">Create your account</h1>
            <p className="text-sm text-muted-foreground">Start managing your finances in minutes.</p>
          </div>

          <div className="auth-social">
            {socialProviders.map((provider) => (
              <Button key={provider.name} variant="outline" className="w-full h-10 justify-start space-x-3">
                <provider.icon className="w-4 h-4" />
                <span>{provider.description}</span>
              </Button>
            ))}
          </div>

          <div className="auth-divider">
            <Separator />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="bg-background px-3 text-xs text-muted-foreground">or sign up with email</span>
            </div>
          </div>

          <FinancialCard variant="financial" className="auth-card">
            <FinancialCardContent className="p-5">
              <form className="space-y-4" onSubmit={onSubmit}>
                <div className="space-y-1.5">
                  <Label htmlFor="email" className="text-sm font-medium">Email address</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input id="email" type="email" placeholder="you@example.com" className="pl-10 h-10" value={email} onChange={(e) => setEmail(e.target.value)} required />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="password" className="text-sm font-medium">Password</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input id="password" type={showPassword ? 'text' : 'password'} placeholder="At least 8 characters" className="pl-10 pr-10 h-10" value={password} onChange={(e) => setPassword(e.target.value)} required />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="confirmPassword" className="text-sm font-medium">Confirm password</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input id="confirmPassword" type={showConfirmPassword ? 'text' : 'password'} placeholder="Re-enter password" className="pl-10 pr-10 h-10" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
                    <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                      {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">{error}</div>}

                <Button className="w-full h-10 group" type="submit" disabled={loading}>
                  {loading ? 'Creating account…' : 'Create account'}
                  <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                </Button>
              </form>
            </FinancialCardContent>
          </FinancialCard>

          <div className="auth-footer">
            <p className="text-sm text-muted-foreground">
              Already have an account?{' '}
              <Link to="/signin" className="text-primary hover:text-primary-hover font-medium transition-colors">Sign in</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
