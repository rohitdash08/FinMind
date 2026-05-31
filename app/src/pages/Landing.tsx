import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FinancialCard, FinancialCardContent, FinancialCardDescription, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { ArrowRight, BarChart3, Bell, Brain, DollarSign, PieChart, Shield, Smartphone, TrendingUp, Users, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';

const features = [
  {
    icon: Brain,
    title: 'AI-Powered Insights',
    description: 'Get intelligent recommendations for optimizing your budget and reducing expenses.'
  },
  {
    icon: Bell,
    title: 'Smart Bill Tracking',
    description: 'Never miss a payment with automated bill detection and payment reminders.'
  },
  {
    icon: BarChart3,
    title: 'Advanced Analytics',
    description: 'Visualize your spending patterns with beautiful charts and detailed reports.'
  },
  {
    icon: Shield,
    title: 'Bank-Grade Security',
    description: 'Your financial data is protected with enterprise-level encryption.'
  },
  {
    icon: Smartphone,
    title: 'Mobile-First Design',
    description: 'Manage your finances seamlessly across all devices with our responsive design.'
  },
  {
    icon: Zap,
    title: 'Real-Time Sync',
    description: 'Instant updates across all platforms keep your financial data always current.'
  }
];

const stats = [
  { label: 'Average Savings', value: '$2,847', description: 'Per user annually' },
  { label: 'Bills Tracked', value: '10M+', description: 'Successfully managed' },
  { label: 'User Satisfaction', value: '98%', description: 'Highly recommended' },
  { label: 'Response Time', value: '<200ms', description: 'Lightning fast' }
];

export function Landing() {
  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Financial Grid Background */}
      <div className="absolute inset-0 opacity-30">
        <div className="absolute inset-0" 
             style={{
               backgroundImage: `
                 linear-gradient(hsl(var(--border)) 1px, transparent 1px),
                 linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px)
               `,
               backgroundSize: '80px 80px'
             }}>
        </div>
        <div className="absolute top-10 left-10 w-32 h-32 bg-primary/5 rounded-full blur-xl"></div>
        <div className="absolute top-1/3 right-20 w-48 h-48 bg-accent/5 rounded-full blur-xl"></div>
        <div className="absolute bottom-20 left-1/4 w-40 h-40 bg-success/5 rounded-full blur-xl"></div>
        <div className="absolute bottom-1/3 right-1/3 w-24 h-24 bg-warning/5 rounded-full blur-xl"></div>
      </div>
      {/* Hero Section */}
      <section className="section-padding bg-gradient-to-br from-background via-primary-light/20 to-accent-light/20 relative z-10">
        <div className="container-financial relative">
          {/* Floating Financial Elements */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none">
            <div className="absolute top-20 left-10 opacity-20">
              <div className="w-16 h-16 bg-primary/20 rounded-lg rotate-12 flex items-center justify-center">
                <DollarSign className="w-8 h-8 text-primary" />
              </div>
            </div>
            <div className="absolute top-40 right-20 opacity-20">
              <div className="w-20 h-20 bg-success/20 rounded-full -rotate-12 flex items-center justify-center">
                <TrendingUp className="w-10 h-10 text-success" />
              </div>
            </div>
            <div className="absolute bottom-40 left-1/4 opacity-20">
              <div className="w-12 h-12 bg-accent/20 rounded-lg rotate-45 flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-accent-foreground" />
              </div>
            </div>
            <div className="absolute top-60 right-1/3 opacity-20">
              <div className="w-14 h-14 bg-warning/20 rounded-xl -rotate-6 flex items-center justify-center">
                <PieChart className="w-7 h-7 text-warning-foreground" />
              </div>
            </div>
          </div>
          
          <div className="text-center max-w-4xl mx-auto relative z-10">
            <div className="flex justify-center items-center space-x-2 mb-6">
              <div className="flex items-center justify-center w-12 h-12 bg-gradient-primary rounded-xl shadow-primary">
                <TrendingUp className="w-6 h-6 text-primary-foreground" />
              </div>
              <span className="text-2xl font-bold bg-gradient-hero bg-clip-text text-transparent">
                FinMind
              </span>
            </div>
            
            <h1 className="text-5xl lg:text-7xl font-bold text-foreground mb-6 leading-tight">
              AI-Powered
              <span className="bg-gradient-hero bg-clip-text text-transparent block relative">
                Financial Intelligence
                <div className="absolute -top-2 -right-2 w-6 h-6 bg-accent rounded-full animate-pulse opacity-60"></div>
              </span>
            </h1>
            
            <p className="text-xl lg:text-2xl text-muted-foreground mb-8 max-w-3xl mx-auto leading-relaxed">
              Transform your financial life with intelligent budget tracking, automated bill management, 
              and AI-driven insights that help you save more and stress less.
            </p>
            
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
              <Button variant="hero" size="xl" className="group" asChild>
                <Link to="/dashboard">
                  Start Your Journey
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Link>
              </Button>
              <Button variant="outline" size="xl">
                Watch Demo
              </Button>
            </div>
            
            <div className="mt-12 text-sm text-muted-foreground flex flex-wrap justify-center items-center gap-8">
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-success rounded-full"></div>
                <span>Free 30-day trial</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-success rounded-full"></div>
                <span>No credit card required</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-success rounded-full"></div>
                <span>Cancel anytime</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-20 bg-muted/30 relative z-10">
        {/* Subtle pattern overlay */}
        <div className="absolute inset-0 opacity-10" 
             style={{
               backgroundImage: `radial-gradient(circle at 2px 2px, hsl(var(--primary)) 1px, transparent 0)`
             }}>
        </div>
        <div className="container-financial relative">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {stats.map((stat, index) => (
              <div key={index} className="text-center group">
                <div className="text-4xl lg:text-5xl font-bold text-primary mb-3 group-hover:scale-110 transition-transform duration-200">
                  {stat.value}
                </div>
                <div className="text-foreground font-semibold mb-2 text-lg">
                  {stat.label}
                </div>
                <div className="text-sm text-muted-foreground">
                  {stat.description}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="section-padding relative z-10 overflow-hidden">
        {/* Futuristic background elements */}
        <div className="absolute inset-0 opacity-5">
          <div className="absolute top-0 left-0 w-full h-full" 
               style={{
                 backgroundImage: `
                   radial-gradient(circle at 25% 25%, hsl(var(--primary)) 2px, transparent 2px),
                   radial-gradient(circle at 75% 75%, hsl(var(--accent)) 1px, transparent 1px),
                   linear-gradient(45deg, transparent 48%, hsl(var(--border)) 48%, hsl(var(--border)) 52%, transparent 52%)
                 `,
                 backgroundSize: '100px 100px, 50px 50px, 200px 200px'
               }}>
          </div>
          {/* Floating geometric shapes */}
          <div className="absolute top-20 left-10 w-32 h-32 border-2 border-primary/20 rounded-full animate-pulse"></div>
          <div className="absolute top-60 right-20 w-24 h-24 border border-accent/30 rotate-45"></div>
          <div className="absolute bottom-40 left-1/4 w-16 h-16 bg-gradient-to-br from-success/10 to-primary/10 rounded-xl rotate-12"></div>
        </div>

        <div className="container-financial">
          <div className="text-center max-w-5xl mx-auto mb-24">
            {/* Futuristic badge */}
            <div className="inline-flex items-center px-4 py-2 mb-6 bg-gradient-to-r from-primary/10 to-accent/10 border border-primary/20 rounded-full">
              <div className="w-2 h-2 bg-success rounded-full mr-2 animate-pulse"></div>
              <span className="text-sm font-medium text-primary">Next-Gen Financial Platform</span>
            </div>
            
            <h2 className="text-5xl lg:text-7xl font-bold mb-8 leading-tight">
              <span className="bg-gradient-to-r from-foreground via-primary to-accent bg-clip-text text-transparent">
                Financial Intelligence
              </span>
              <br />
              <span className="text-3xl lg:text-4xl text-muted-foreground font-medium">
                Redefined for the Digital Age
              </span>
            </h2>
            <p className="text-xl lg:text-2xl text-muted-foreground max-w-4xl mx-auto leading-relaxed">
              Experience the future of personal finance with AI-powered insights, 
              real-time analytics, and automation that adapts to your lifestyle.
            </p>
          </div>
          
          {/* Enhanced feature grid with real data examples */}
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8 relative">
            {features.map((feature, index) => {
              const realExamples = [
                { metric: "$1,247", label: "Avg Monthly Savings", trend: "+23%" },
                { metric: "12 Bills", label: "Auto-Tracked", trend: "100%" },
                { metric: "847 Users", label: "Insights Generated", trend: "+156%" },
                { metric: "256-bit", label: "Encryption Level", trend: "Military" },
                { metric: "99.9%", label: "Uptime SLA", trend: "24/7" },
                { metric: "<50ms", label: "Sync Speed", trend: "Real-time" }
              ];
              
              return (
                <FinancialCard 
                  key={index} 
                  variant="financial" 
                  className="group hover:scale-[1.03] hover:shadow-2xl hover:shadow-primary/10 transition-all duration-300 relative overflow-hidden border-2 hover:border-primary/30"
                >
                  {/* Animated background glow */}
                  <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-accent/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                  
                  <FinancialCardHeader className="relative z-10">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center space-x-3">
                        <div className="relative flex items-center justify-center w-14 h-14 bg-gradient-to-br from-primary-light to-primary/20 rounded-2xl group-hover:from-primary group-hover:to-primary-hover group-hover:text-primary-foreground transition-all duration-300 shadow-lg">
                          <feature.icon className="w-7 h-7 relative z-10" />
                          <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent rounded-2xl"></div>
                        </div>
                        <div>
                          <FinancialCardTitle className="text-xl font-bold group-hover:text-primary transition-colors">
                            {feature.title}
                          </FinancialCardTitle>
                          <div className="text-xs text-muted-foreground font-medium">
                            {realExamples[index].label}
                          </div>
                        </div>
                      </div>
                      {/* Real-time metric display */}
                      <div className="text-right">
                        <div className="text-lg font-bold text-success">
                          {realExamples[index].metric}
                        </div>
                        <div className="text-xs text-success/80 flex items-center">
                          <TrendingUp className="w-3 h-3 mr-1" />
                          {realExamples[index].trend}
                        </div>
                      </div>
                    </div>
                  </FinancialCardHeader>
                  
                  <FinancialCardContent className="relative z-10">
                    <FinancialCardDescription className="text-base leading-relaxed mb-4">
                      {feature.description}
                    </FinancialCardDescription>
                    
                    {/* Interactive progress indicator */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Performance</span>
                        <span>{90 + index * 2}%</span>
                      </div>
                      <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-primary to-accent transition-all duration-1000 group-hover:from-accent group-hover:to-primary"
                          style={{ width: `${90 + index * 2}%` }}
                        ></div>
                      </div>
                    </div>
                    
                    {/* Holographic effect line */}
                    <div className="absolute bottom-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                  </FinancialCardContent>
                </FinancialCard>
              );
            })}
          </div>
          
          {/* Real-time activity feed */}
          <div className="mt-20 text-center">
            <div className="inline-flex items-center space-x-8 p-6 bg-muted/30 backdrop-blur-sm border border-border/50 rounded-2xl">
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-success rounded-full animate-pulse"></div>
                <span className="text-sm text-muted-foreground">Live: 2,847 transactions processed</span>
              </div>
              <div className="w-px h-6 bg-border"></div>
              <div className="flex items-center space-x-2">
                <Users className="w-4 h-4 text-primary" />
                <span className="text-sm text-muted-foreground">124 users online now</span>
              </div>
              <div className="w-px h-6 bg-border"></div>
              <div className="flex items-center space-x-2">
                <Zap className="w-4 h-4 text-accent" />
                <span className="text-sm text-muted-foreground">AI processing 847 insights</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials Section */}
      <section className="section-padding bg-gradient-to-br from-muted/30 via-background to-primary/5 relative z-10">
        <div className="absolute inset-0 opacity-5">
          <div 
            className="w-full h-full"
            style={{
              backgroundImage: `
                radial-gradient(circle at 50% 50%, hsl(var(--accent)) 2px, transparent 2px),
                linear-gradient(60deg, transparent 48%, hsl(var(--border)) 48%, hsl(var(--border)) 52%, transparent 52%)
              `,
              backgroundSize: '150px 150px, 300px 300px'
            }}
          />
        </div>

        <div className="container-financial relative">
          <div className="text-center max-w-4xl mx-auto mb-16">
            <div className="inline-flex items-center px-4 py-2 mb-6 bg-gradient-to-r from-success/10 to-primary/10 border border-success/20 rounded-full">
              <Users className="w-4 h-4 mr-2 text-success" />
              <span className="text-sm font-medium text-success">Trusted by Thousands</span>
            </div>
            
            <h2 className="text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Loved by users worldwide
            </h2>
            <p className="text-xl text-muted-foreground">
              See what our customers say about their financial transformation
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                name: "Sarah Chen",
                role: "Software Engineer",
                company: "TechCorp",
                avatar: "SC",
                rating: 5,
                quote: "FinMind's AI insights helped me save $3,200 in just 6 months. The automated bill tracking is a game-changer!",
                savings: "$3,200 saved"
              },
              {
                name: "Marcus Johnson",
                role: "Marketing Director", 
                company: "StartupXYZ",
                avatar: "MJ",
                rating: 5,
                quote: "The real-time analytics and budget optimization features have completely transformed how I manage my finances.",
                savings: "$4,800 saved"
              },
              {
                name: "Emily Rodriguez",
                role: "Freelance Designer",
                company: "Independent",
                avatar: "ER", 
                rating: 5,
                quote: "As a freelancer, managing irregular income was tough. FinMind's smart budgeting made it effortless.",
                savings: "$2,100 saved"
              }
            ].map((testimonial, index) => (
              <FinancialCard key={index} variant="premium" className="group hover:scale-[1.02] transition-all duration-300">
                <FinancialCardContent className="p-6">
                  <div className="flex items-center space-x-1 mb-4">
                    {[...Array(testimonial.rating)].map((_, i) => (
                      <div key={i} className="w-4 h-4 bg-warning rounded-sm"></div>
                    ))}
                  </div>
                  
                  <blockquote className="text-foreground mb-6 leading-relaxed">
                    "{testimonial.quote}"
                  </blockquote>
                  
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="w-12 h-12 bg-gradient-to-br from-primary to-accent rounded-full flex items-center justify-center text-white font-semibold">
                        {testimonial.avatar}
                      </div>
                      <div>
                        <div className="font-semibold text-foreground">{testimonial.name}</div>
                        <div className="text-sm text-muted-foreground">{testimonial.role}</div>
                        <div className="text-xs text-muted-foreground">{testimonial.company}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-bold text-success">{testimonial.savings}</div>
                      <div className="text-xs text-muted-foreground">in 6 months</div>
                    </div>
                  </div>
                </FinancialCardContent>
              </FinancialCard>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="section-padding relative z-10">
        <div className="container-financial">
          <div className="text-center max-w-4xl mx-auto mb-16">
            <div className="inline-flex items-center px-4 py-2 mb-6 bg-gradient-to-r from-accent/10 to-warning/10 border border-accent/20 rounded-full">
              <DollarSign className="w-4 h-4 mr-2 text-accent" />
              <span className="text-sm font-medium text-accent">Simple Pricing</span>
            </div>
            
            <h2 className="text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Choose your plan
            </h2>
            <p className="text-xl text-muted-foreground">
              Start free, upgrade when you're ready. No hidden fees, ever.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {[
              {
                name: "Starter",
                price: "Free",
                period: "forever",
                description: "Perfect for getting started with financial tracking",
                features: [
                  "Basic expense tracking",
                  "5 bank account connections",
                  "Monthly financial reports",
                  "Email support",
                  "Mobile app access"
                ],
                popular: false,
                cta: "Get Started"
              },
              {
                name: "Pro",
                price: "$9.99",
                period: "/month",
                description: "Advanced features for serious financial management", 
                features: [
                  "Everything in Starter",
                  "AI-powered insights",
                  "Unlimited bank connections",
                  "Advanced analytics",
                  "Bill payment automation",
                  "Investment tracking",
                  "Priority support"
                ],
                popular: true,
                cta: "Start Free Trial"
              },
              {
                name: "Business",
                price: "$29.99", 
                period: "/month",
                description: "Built for businesses and power users",
                features: [
                  "Everything in Pro",
                  "Multi-entity management",
                  "Team collaboration",
                  "Custom reporting",
                  "API access",
                  "Dedicated account manager",
                  "24/7 phone support"
                ],
                popular: false,
                cta: "Contact Sales"
              }
            ].map((plan, index) => (
              <FinancialCard 
                key={index} 
                variant={plan.popular ? "premium" : "financial"}
                className={`relative group hover:scale-[1.02] transition-all duration-300 ${
                  plan.popular ? 'border-2 border-primary shadow-2xl shadow-primary/20' : ''
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 transform -translate-x-1/2">
                    <div className="bg-gradient-to-r from-primary to-accent text-white px-4 py-1 rounded-full text-sm font-medium">
                      Most Popular
                    </div>
                  </div>
                )}
                
                <FinancialCardHeader>
                  <div className="text-center">
                    <h3 className="text-xl font-bold text-foreground mb-2">{plan.name}</h3>
                    <div className="flex items-baseline justify-center space-x-1 mb-2">
                      <span className="text-3xl font-bold text-foreground">{plan.price}</span>
                      <span className="text-muted-foreground">{plan.period}</span>
                    </div>
                    <p className="text-sm text-muted-foreground">{plan.description}</p>
                  </div>
                </FinancialCardHeader>
                
                <FinancialCardContent>
                  <ul className="space-y-3 mb-8">
                    {plan.features.map((feature, featureIndex) => (
                      <li key={featureIndex} className="flex items-center space-x-3">
                        <div className="w-5 h-5 bg-success/20 rounded-full flex items-center justify-center">
                          <div className="w-2 h-2 bg-success rounded-full"></div>
                        </div>
                        <span className="text-sm text-foreground">{feature}</span>
                      </li>
                    ))}
                  </ul>
                  
                  <Button 
                    variant={plan.popular ? "hero" : "outline"} 
                    className="w-full h-12"
                    asChild
                  >
                    <Link to="/register">
                      {plan.cta}
                    </Link>
                  </Button>
                </FinancialCardContent>
              </FinancialCard>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="section-padding bg-muted/30 relative z-10">
        <div className="container-financial">
          <div className="text-center max-w-4xl mx-auto mb-16">
            <h2 className="text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Frequently asked questions
            </h2>
            <p className="text-xl text-muted-foreground">
              Everything you need to know about FinMind
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
            {[
              {
                question: "How secure is my financial data?",
                answer: "We use bank-grade 256-bit encryption and never store your login credentials. Your data is processed securely and we're SOC 2 Type II certified."
              },
              {
                question: "Which banks and financial institutions do you support?",
                answer: "We support over 12,000 financial institutions across the US, Canada, and Europe, including all major banks and credit unions."
              },
              {
                question: "Can I cancel my subscription at any time?",
                answer: "Yes, you can cancel your subscription at any time. There are no cancellation fees and you'll retain access until the end of your billing period."
              },
              {
                question: "How does the AI-powered insights feature work?",
                answer: "Our AI analyzes your spending patterns, income trends, and financial goals to provide personalized recommendations for saving money and optimizing your budget."
              },
              {
                question: "Is there a mobile app available?",
                answer: "Yes, we have native iOS and Android apps that sync in real-time with the web platform, so you can manage your finances on the go."
              },
              {
                question: "Do you offer customer support?",
                answer: "We offer email support for all users, priority support for Pro users, and 24/7 phone support for Business plan subscribers."
              }
            ].map((faq, index) => (
              <FinancialCard key={index} variant="financial" className="group hover:shadow-lg transition-all duration-200">
                <FinancialCardContent className="p-6">
                  <h3 className="font-semibold text-foreground mb-3 group-hover:text-primary transition-colors">
                    {faq.question}
                  </h3>
                  <p className="text-muted-foreground leading-relaxed">
                    {faq.answer}
                  </p>
                </FinancialCardContent>
              </FinancialCard>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="section-padding relative z-10">
        <div className="container-financial">
          <div className="subscribe-panel">
            <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Subscribe</p>
                <h3 className="mt-2 text-2xl font-extrabold text-foreground">Get weekly financial intelligence in your inbox</h3>
                <p className="mt-1 text-sm text-muted-foreground">Only one email per week. No spam, no noise, just practical money moves.</p>
              </div>
              <div className="flex w-full max-w-md gap-2">
                <Input type="email" placeholder="you@company.com" className="bg-white" />
                <Button variant="hero">Subscribe</Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section-padding bg-gradient-to-r from-secondary to-secondary-hover relative z-10">
        <div className="container-financial text-center relative">
          {/* CTA Background Elements */}
          <div className="absolute inset-0 overflow-hidden opacity-10">
            <div className="absolute top-10 left-10 w-32 h-32 border border-secondary-foreground/20 rounded-full"></div>
            <div className="absolute bottom-10 right-10 w-40 h-40 border border-secondary-foreground/20 rounded-lg rotate-45"></div>
            <div className="absolute top-1/2 left-1/4 w-6 h-6 bg-secondary-foreground/20 rounded-full"></div>
            <div className="absolute top-1/3 right-1/4 w-8 h-8 bg-secondary-foreground/20 rounded-sm rotate-12"></div>
          </div>
          
          <div className="max-w-3xl mx-auto relative z-10">
            <h2 className="text-4xl lg:text-5xl font-bold text-secondary-foreground mb-8">
              Ready to take control of your finances?
            </h2>
            <p className="text-xl lg:text-2xl text-secondary-foreground/80 mb-10">
              Join thousands of users who have already transformed their financial lives with FinMind.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Button variant="hero" size="xl" asChild>
                <Link to="/register">
                  Get Started for Free
                </Link>
              </Button>
              <Button variant="outline" size="xl" className="border-secondary-foreground/20 text-secondary-foreground hover:bg-secondary-foreground/10">
                Schedule Demo
              </Button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
