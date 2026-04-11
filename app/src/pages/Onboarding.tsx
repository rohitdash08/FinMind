import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Target,
  User,
  DollarSign,
  Tag,
  Bell,
  CheckCircle,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
} from '@/components/ui/financial-card';
import { useToast } from '@/hooks/use-toast';
import {
  type FinancialGoal,
  type LifestyleProfile,
  type SpendingCategory,
  type NotificationChannel,
  type OnboardingProfile,
  completeOnboarding,
  saveOnboardingDraft,
  loadOnboardingDraft,
  markOnboardingComplete,
  isOnboardingComplete,
  DEFAULT_SPENDING_CATEGORIES,
} from '@/api/onboarding';

const TOTAL_STEPS = 6;

const GOALS: { value: FinancialGoal; label: string; description: string }[] = [
  { value: 'save_for_emergency', label: 'Emergency Fund', description: 'Build a 3-6 month safety net' },
  { value: 'pay_off_debt', label: 'Pay Off Debt', description: 'Eliminate credit cards or loans' },
  { value: 'build_investments', label: 'Build Investments', description: 'Grow wealth over time' },
  { value: 'track_spending', label: 'Track Spending', description: 'Understand where money goes' },
  { value: 'save_for_goal', label: 'Save for a Goal', description: 'Buy a car, travel, or a home' },
  { value: 'retirement', label: 'Plan for Retirement', description: 'Secure your future' },
];

const LIFESTYLES: { value: LifestyleProfile; label: string; emoji: string }[] = [
  { value: 'student', label: 'Student', emoji: '🎓' },
  { value: 'early_career', label: 'Early Career', emoji: '💼' },
  { value: 'family', label: 'Managing a Family', emoji: '🏠' },
  { value: 'freelancer', label: 'Freelancer / Self-Employed', emoji: '🧑‍💻' },
  { value: 'retired', label: 'Retired', emoji: '🌅' },
];

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'KES', 'NGN', 'ZAR', 'GHS', 'UGX', 'CAD', 'AUD'];

const REMINDER_DAYS = [1, 2, 3, 5, 7];

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-8" aria-label={`Step ${current} of ${total}`}>
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`h-2 rounded-full transition-all duration-300 ${
            i < current ? 'bg-primary w-6' : i === current - 1 ? 'bg-primary w-8' : 'bg-muted w-4'
          }`}
        />
      ))}
    </div>
  );
}

export function Onboarding() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);

  // Wizard state — initialise from saved draft
  const [selectedGoals, setSelectedGoals] = useState<FinancialGoal[]>([]);
  const [lifestyle, setLifestyle] = useState<LifestyleProfile | ''>('');
  const [monthlyIncome, setMonthlyIncome] = useState('');
  const [monthlyExpense, setMonthlyExpense] = useState('');
  const [currency, setCurrency] = useState('INR');
  const [categories, setCategories] = useState<SpendingCategory[]>(DEFAULT_SPENDING_CATEGORIES);
  const [notificationChannel, setNotificationChannel] = useState<NotificationChannel>('email');
  const [billReminderDays, setBillReminderDays] = useState(3);

  // Redirect if already onboarded
  useEffect(() => {
    if (isOnboardingComplete()) {
      navigate('/dashboard', { replace: true });
    }
  }, [navigate]);

  // Restore draft
  useEffect(() => {
    const draft = loadOnboardingDraft();
    if (!draft) return;
    if (draft.financial_goals?.length) setSelectedGoals(draft.financial_goals);
    if (draft.lifestyle) setLifestyle(draft.lifestyle);
    if (draft.monthly_income != null) setMonthlyIncome(String(draft.monthly_income));
    if (draft.monthly_expense_estimate != null)
      setMonthlyExpense(String(draft.monthly_expense_estimate));
    if (draft.preferred_currency) setCurrency(draft.preferred_currency);
    if (draft.spending_categories?.length) setCategories(draft.spending_categories);
    if (draft.notification_channel) setNotificationChannel(draft.notification_channel);
    if (draft.bill_reminder_days != null) setBillReminderDays(draft.bill_reminder_days);
  }, []);

  function buildDraft(): Partial<OnboardingProfile> {
    return {
      financial_goals: selectedGoals,
      lifestyle: lifestyle || undefined,
      monthly_income: monthlyIncome ? Number(monthlyIncome) : undefined,
      monthly_expense_estimate: monthlyExpense ? Number(monthlyExpense) : undefined,
      preferred_currency: currency,
      spending_categories: categories,
      notification_channel: notificationChannel,
      bill_reminder_days: billReminderDays,
    };
  }

  function persistDraft() {
    saveOnboardingDraft(buildDraft());
  }

  function toggleGoal(goal: FinancialGoal) {
    setSelectedGoals((prev) =>
      prev.includes(goal) ? prev.filter((g) => g !== goal) : [...prev, goal],
    );
  }

  function toggleCategory(index: number) {
    setCategories((prev) =>
      prev.map((cat, i) => (i === index ? { ...cat, enabled: !cat.enabled } : cat)),
    );
  }

  function updateCategoryBudget(index: number, value: string) {
    setCategories((prev) =>
      prev.map((cat, i) =>
        i === index ? { ...cat, monthly_budget: value ? Number(value) : undefined } : cat,
      ),
    );
  }

  function canAdvance(): boolean {
    switch (step) {
      case 1:
        return true; // welcome — always can proceed
      case 2:
        return selectedGoals.length > 0;
      case 3:
        return lifestyle !== '';
      case 4:
        return true; // income is optional
      case 5:
        return categories.some((c) => c.enabled);
      case 6:
        return true;
      default:
        return true;
    }
  }

  function handleNext() {
    if (!canAdvance()) return;
    persistDraft();
    if (step < TOTAL_STEPS) {
      setStep((s) => s + 1);
    }
  }

  function handleBack() {
    if (step > 1) setStep((s) => s - 1);
  }

  async function handleComplete() {
    if (!lifestyle) return;
    setLoading(true);
    persistDraft();
    const profile: OnboardingProfile = {
      financial_goals: selectedGoals,
      lifestyle: lifestyle as LifestyleProfile,
      monthly_income: monthlyIncome ? Number(monthlyIncome) : undefined,
      monthly_expense_estimate: monthlyExpense ? Number(monthlyExpense) : undefined,
      preferred_currency: currency,
      spending_categories: categories,
      notification_channel: notificationChannel,
      bill_reminder_days: billReminderDays,
    };
    try {
      await completeOnboarding(profile);
    } catch {
      // API may be unavailable in dev; still mark complete locally
    }
    markOnboardingComplete();
    toast({ title: 'Setup complete!', description: 'Your financial profile is ready.' });
    navigate('/dashboard', { replace: true });
    setLoading(false);
  }

  const isLastStep = step === TOTAL_STEPS;

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-muted flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <StepIndicator current={step} total={TOTAL_STEPS} />

        {/* Step 1: Welcome */}
        {step === 1 && (
          <FinancialCard>
            <FinancialCardHeader>
              <FinancialCardTitle className="text-2xl text-center">
                Welcome to FinMind
              </FinancialCardTitle>
              <FinancialCardDescription className="text-center text-base">
                Let's personalise your experience. This takes about 2 minutes and helps FinMind
                give you smarter insights from day one.
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent className="flex flex-col items-center gap-6 py-6">
              <div className="grid grid-cols-3 gap-4 w-full text-center text-sm text-muted-foreground">
                <div className="flex flex-col items-center gap-2">
                  <Target className="h-8 w-8 text-primary" />
                  <span>Set goals</span>
                </div>
                <div className="flex flex-col items-center gap-2">
                  <DollarSign className="h-8 w-8 text-primary" />
                  <span>Track income</span>
                </div>
                <div className="flex flex-col items-center gap-2">
                  <Bell className="h-8 w-8 text-primary" />
                  <span>Get reminders</span>
                </div>
              </div>
            </FinancialCardContent>
          </FinancialCard>
        )}

        {/* Step 2: Financial Goals */}
        {step === 2 && (
          <FinancialCard>
            <FinancialCardHeader>
              <div className="flex items-center gap-2 mb-1">
                <Target className="h-5 w-5 text-primary" />
                <FinancialCardTitle>What are your financial goals?</FinancialCardTitle>
              </div>
              <FinancialCardDescription>Select all that apply.</FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {GOALS.map((goal) => {
                  const active = selectedGoals.includes(goal.value);
                  return (
                    <button
                      key={goal.value}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleGoal(goal.value)}
                      className={`text-left p-4 rounded-lg border-2 transition-colors cursor-pointer ${
                        active
                          ? 'border-primary bg-primary/10'
                          : 'border-border bg-card hover:border-primary/50'
                      }`}
                    >
                      <div className="font-medium text-sm">{goal.label}</div>
                      <div className="text-xs text-muted-foreground mt-1">{goal.description}</div>
                    </button>
                  );
                })}
              </div>
            </FinancialCardContent>
          </FinancialCard>
        )}

        {/* Step 3: Lifestyle */}
        {step === 3 && (
          <FinancialCard>
            <FinancialCardHeader>
              <div className="flex items-center gap-2 mb-1">
                <User className="h-5 w-5 text-primary" />
                <FinancialCardTitle>Which best describes you?</FinancialCardTitle>
              </div>
              <FinancialCardDescription>
                This helps us tailor budget suggestions to your situation.
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="flex flex-col gap-3">
                {LIFESTYLES.map((ls) => (
                  <button
                    key={ls.value}
                    type="button"
                    aria-pressed={lifestyle === ls.value}
                    onClick={() => setLifestyle(ls.value)}
                    className={`flex items-center gap-3 p-4 rounded-lg border-2 transition-colors cursor-pointer ${
                      lifestyle === ls.value
                        ? 'border-primary bg-primary/10'
                        : 'border-border bg-card hover:border-primary/50'
                    }`}
                  >
                    <span className="text-2xl">{ls.emoji}</span>
                    <span className="font-medium">{ls.label}</span>
                  </button>
                ))}
              </div>
            </FinancialCardContent>
          </FinancialCard>
        )}

        {/* Step 4: Income & Expense */}
        {step === 4 && (
          <FinancialCard>
            <FinancialCardHeader>
              <div className="flex items-center gap-2 mb-1">
                <DollarSign className="h-5 w-5 text-primary" />
                <FinancialCardTitle>Income & Expense Estimates</FinancialCardTitle>
              </div>
              <FinancialCardDescription>
                Approximate figures are fine. You can update them any time.
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent className="flex flex-col gap-5">
              <div className="flex flex-col gap-2">
                <Label htmlFor="currency">Preferred Currency</Label>
                <select
                  id="currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="monthly-income">Monthly Income (optional)</Label>
                <Input
                  id="monthly-income"
                  type="number"
                  min="0"
                  placeholder="e.g. 5000"
                  value={monthlyIncome}
                  onChange={(e) => setMonthlyIncome(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="monthly-expense">Estimated Monthly Expenses (optional)</Label>
                <Input
                  id="monthly-expense"
                  type="number"
                  min="0"
                  placeholder="e.g. 3500"
                  value={monthlyExpense}
                  onChange={(e) => setMonthlyExpense(e.target.value)}
                />
              </div>
            </FinancialCardContent>
          </FinancialCard>
        )}

        {/* Step 5: Spending Categories */}
        {step === 5 && (
          <FinancialCard>
            <FinancialCardHeader>
              <div className="flex items-center gap-2 mb-1">
                <Tag className="h-5 w-5 text-primary" />
                <FinancialCardTitle>Spending Categories</FinancialCardTitle>
              </div>
              <FinancialCardDescription>
                Enable the categories you spend in and set optional monthly budgets.
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent>
              <div className="flex flex-col gap-3 max-h-80 overflow-y-auto pr-1">
                {categories.map((cat, i) => (
                  <div key={cat.name} className="flex items-center gap-3">
                    <button
                      type="button"
                      aria-pressed={cat.enabled}
                      onClick={() => toggleCategory(i)}
                      className={`w-5 h-5 rounded border-2 flex-shrink-0 transition-colors ${
                        cat.enabled ? 'bg-primary border-primary' : 'border-border'
                      }`}
                      aria-label={`Toggle ${cat.name}`}
                    />
                    <span className="flex-1 text-sm font-medium">{cat.name}</span>
                    {cat.enabled && (
                      <Input
                        type="number"
                        min="0"
                        placeholder="Budget"
                        value={cat.monthly_budget ?? ''}
                        onChange={(e) => updateCategoryBudget(i, e.target.value)}
                        className="w-28 h-8 text-sm"
                        aria-label={`${cat.name} monthly budget`}
                      />
                    )}
                  </div>
                ))}
              </div>
            </FinancialCardContent>
          </FinancialCard>
        )}

        {/* Step 6: Notifications */}
        {step === 6 && (
          <FinancialCard>
            <FinancialCardHeader>
              <div className="flex items-center gap-2 mb-1">
                <Bell className="h-5 w-5 text-primary" />
                <FinancialCardTitle>Notification Preferences</FinancialCardTitle>
              </div>
              <FinancialCardDescription>
                Choose how you want to be reminded about upcoming bills and budget alerts.
              </FinancialCardDescription>
            </FinancialCardHeader>
            <FinancialCardContent className="flex flex-col gap-6">
              <div className="flex flex-col gap-3">
                <Label>Reminder Channel</Label>
                {(['email', 'whatsapp', 'none'] as NotificationChannel[]).map((channel) => (
                  <button
                    key={channel}
                    type="button"
                    aria-pressed={notificationChannel === channel}
                    onClick={() => setNotificationChannel(channel)}
                    className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-colors capitalize ${
                      notificationChannel === channel
                        ? 'border-primary bg-primary/10'
                        : 'border-border hover:border-primary/50'
                    }`}
                  >
                    <div
                      className={`w-4 h-4 rounded-full border-2 ${
                        notificationChannel === channel ? 'bg-primary border-primary' : 'border-border'
                      }`}
                    />
                    <span className="text-sm font-medium">
                      {channel === 'none' ? 'No reminders' : channel.charAt(0).toUpperCase() + channel.slice(1)}
                    </span>
                  </button>
                ))}
              </div>
              {notificationChannel !== 'none' && (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="reminder-days">Remind me how many days before a bill is due?</Label>
                  <div className="flex gap-2 flex-wrap">
                    {REMINDER_DAYS.map((d) => (
                      <button
                        key={d}
                        type="button"
                        aria-pressed={billReminderDays === d}
                        onClick={() => setBillReminderDays(d)}
                        className={`px-4 py-2 rounded-md text-sm border-2 transition-colors ${
                          billReminderDays === d
                            ? 'border-primary bg-primary text-primary-foreground'
                            : 'border-border hover:border-primary/50'
                        }`}
                      >
                        {d} {d === 1 ? 'day' : 'days'}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="bg-muted/50 rounded-lg p-4 text-sm text-muted-foreground">
                <CheckCircle className="inline h-4 w-4 mr-2 text-primary" />
                You're all set! Click <strong>Finish Setup</strong> to start tracking your finances.
              </div>
            </FinancialCardContent>
          </FinancialCard>
        )}

        {/* Navigation */}
        <div className="flex justify-between mt-6">
          <Button
            variant="ghost"
            onClick={handleBack}
            disabled={step === 1}
            className="flex items-center gap-1"
          >
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>
          {isLastStep ? (
            <Button onClick={handleComplete} disabled={loading || !canAdvance()}>
              {loading ? 'Saving...' : 'Finish Setup'}
              <CheckCircle className="h-4 w-4 ml-2" />
            </Button>
          ) : (
            <Button onClick={handleNext} disabled={!canAdvance()}>
              Next
              <ChevronRight className="h-4 w-4 ml-2" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export default Onboarding;
