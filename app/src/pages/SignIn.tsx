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
  Apple,
  Shield,
  Zap,
  Users
} from 'lucide-react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { login, me } from '@/api/auth';
import { setToken, setRefreshToken, setCurrency } from '@/lib/auth';
import { useToast } from '@/components/ui/use-toast';

const socialProviders = [
  { name: 'Google', icon: Chrome, description: 'Sign in with Google' },
  { name: 'GitHub', icon: Github, description: 'Sign in with GitHub' },
  { name: 'Apple', icon: Apple, description: 'Sign in with Apple' },
];

const features = [
  { icon: Shield, title: 'Secure Login', description: 'Military-grade encryption' },
  { icon: Zap, title: 'Instant Access', description: 'Get started in seconds' },
  { icon: Users, title: 'Trusted by 10K+', description: 'Join our community' },
];

export function SignIn() {
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();
  type LocState = { from?: { pathname: string } } | null;
  const location = useLocation() as unknown as { state: LocState };
  const from = location?.state?.from?.pathname ?? '/dashboard';
  const { toast } = useToast();

  return (
    <div className="auth-shell auth-screen flex">
      {/* Left Side - Form */}
      <div className="auth-pane">
        {/* Background Pattern */}
        <div className="absolute inset-0 opacity-5">
          <div 
            className="w-full h-full"
            style={{
              backgroundImage: `
                radial-gradient(circle at 25% 25%, hsl(var(--primary)) 2px, transparent 2px),
                linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px),
                linear-gradient(hsl(var(--border)) 1px, transparent 1px)
              `,
              backgroundSize: '80px 80px, 20px 20px, 20px 20px'
            }}
          />
        </div>

        <div className="auth-content">
          {/* Header */}
          <div className="text-center mb-5 pt-3 md:pt-4">
            <Link to="/" className="inline-flex items-center space-x-2 mb-4">
              <div className="flex items-center justify-center w-12 h-12 bg-gradient-primary rounded-xl shadow-primary">
                <TrendingUp className="w-6 h-6 text-primary-foreground" />
              </div>
              <span className="text-2xl font-bold bg-gradient-hero bg-clip-text text-transparent">
                FinMind
              </span>
            </Link>
            
            <h1 className="text-2xl font-bold text-foreground mb-1">
              Welcome back
            </h1>
            <p className="text-sm text-muted-foreground">
              Sign in to your account to continue your financial journey
            </p>
          </div>

          {/* Social Login */}
          <div className="auth-social">
            {socialProviders.map((provider) => (
              <Button
                key={provider.name}
                variant="outline"
                className="w-full h-10 justify-start space-x-3"
              >
                <provider.icon className="w-5 h-5" />
                <span>{provider.description}</span>
              </Button>
            ))}
          </div>

          <div className="auth-divider">
            <Separator />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="bg-background px-4 text-sm text-muted-foreground">
                Or continue with email
              </span>
            </div>
          </div>

          {/* Form */}
          <FinancialCard variant="financial" className="auth-card">
            <FinancialCardContent className="p-5">
              <form
                className="space-y-4"
                onSubmit={async (e) => {
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
                    } catch {
                      // Keep existing local currency if profile fetch fails.
                    }
                    toast({
                      title: 'Welcome back 👋',
                      description: 'You have successfully signed in.',
                    });
                    nav(from, { replace: true });
                  } catch (err: unknown) {
                    const message = err instanceof Error ? err.message : 'Invalid email or password';
                    setError(message);
                    toast({
                      variant: 'destructive',
                      title: 'Sign in failed',
                      description: message,
                    });
                  } finally {
                    setLoading(false);
                  }
                }}
              >
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-sm font-medium">
                    Email address
                  </Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      placeholder="you@example.com"
                      className="pl-10 h-10"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password" className="text-sm font-medium">
                    Password
                  </Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      placeholder="Enter your password"
                      className="pl-10 pr-10 h-10"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <label className="flex items-center space-x-2 text-sm">
                    <input type="checkbox" className="rounded border-border" />
                    <span className="text-muted-foreground">Remember me</span>
                  </label>
                  <Link 
                    to="/forgot-password" 
                    className="text-sm text-primary hover:text-primary-hover transition-colors"
                  >
                    Forgot password?
                  </Link>
                </div>

                {error && (
                  <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
                    {error}
                  </div>
                )}

                <Button className="w-full h-10 group" type="submit" disabled={loading}>
                  {loading ? 'Signing in…' : 'Sign in to your account'}
                  <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                </Button>
              </form>
            </FinancialCardContent>
          </FinancialCard>

          {/* Footer */}
          <div className="auth-footer">
            <p className="text-sm text-muted-foreground">
              Don't have an account?{' '}
              <Link 
                to="/register" 
                className="text-primary hover:text-primary-hover font-medium transition-colors"
              >
                Sign up for free
              </Link>
            </p>
          </div>

          <div className="mt-3 hidden xl:flex items-center justify-center gap-2 text-xs text-muted-foreground">
            {features.map((feature, index) => (
              <div key={index} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-1">
                <feature.icon className="h-3.5 w-3.5 text-primary" />
                <span>{feature.title}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Side - Visual */}
      <div className="hidden xl:flex flex-1 bg-gradient-to-br from-secondary via-primary to-accent relative overflow-hidden">
        <div className="absolute inset-0 opacity-20" />
        <div className="absolute -top-28 left-8 h-72 w-72 rounded-full bg-white/20 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-80 w-80 rounded-full bg-white/10 blur-3xl" />

        <div className="flex items-center justify-center p-8 relative z-10">
          <div className="max-w-lg text-white">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/15 px-3 py-1 text-xs font-semibold tracking-wide">
              <span className="h-2 w-2 rounded-full bg-emerald-300" />
              SECURE FINANCE WORKSPACE
            </div>

            <h2 className="text-4xl font-extrabold leading-tight">
              Welcome back to your
              <span className="block text-white/85">financial command center.</span>
            </h2>

            <p className="mt-4 text-base text-white/85">
              Continue with live budgets, bill tracking, and AI-led spend insights designed to keep your money decisions sharp.
            </p>

            <div className="mt-6 grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-white/25 bg-white/15 p-3 text-center backdrop-blur-sm">
                <div className="text-2xl font-extrabold">$2.4M+</div>
                <div className="text-xs text-white/80">Managed spend</div>
              </div>
              <div className="rounded-xl border border-white/25 bg-white/15 p-3 text-center backdrop-blur-sm">
                <div className="text-2xl font-extrabold">99.9%</div>
                <div className="text-xs text-white/80">Reminder reliability</div>
              </div>
              <div className="rounded-xl border border-white/25 bg-white/15 p-3 text-center backdrop-blur-sm">
                <div className="text-2xl font-extrabold">4.9★</div>
                <div className="text-xs text-white/80">User satisfaction</div>
              </div>
            </div>

            <div className="mt-6 rounded-2xl border border-white/25 bg-white/12 p-5 backdrop-blur-sm">
              <div className="mb-3 text-sm font-semibold text-white/90">Today’s momentum</div>
              <div className="space-y-2 text-sm text-white/85">
                <div className="flex items-center justify-between rounded-lg bg-white/10 px-3 py-2">
                  <span>Expenses categorized</span>
                  <span className="font-bold">93%</span>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-white/10 px-3 py-2">
                  <span>Budget adherence</span>
                  <span className="font-bold">On Track</span>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-white/10 px-3 py-2">
                  <span>Next bill risk</span>
                  <span className="font-bold">Low</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
