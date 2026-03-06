import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Budgets } from "./pages/Budgets";
import { Bills } from "./pages/Bills";
import { Analytics } from "./pages/Analytics";
import Reminders from "./pages/Reminders";
import Expenses from "./pages/Expenses";
import { SignIn } from "./pages/SignIn";
import { Register } from "./pages/Register";
import NotFound from "./pages/NotFound";
import { Landing } from "./pages/Landing";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import Account from "./pages/Account";
import SavingsGoals from "./pages/SavingsGoals";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
    },
  },
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Landing />} />
            <Route
              path="dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="budgets"
              element={
                <ProtectedRoute>
                  <Budgets />
                </ProtectedRoute>
              }
            />
            <Route
              path="bills"
              element={
                <ProtectedRoute>
                  <Bills />
                </ProtectedRoute>
              }
            />
            <Route
              path="expenses"
              element={
                <ProtectedRoute>
                  <Expenses />
                </ProtectedRoute>
              }
            />
            <Route
              path="analytics"
              element={
                <ProtectedRoute>
                  <Analytics />
                </ProtectedRoute>
              }
            />
            <Route
              path="reminders"
              element={
                <ProtectedRoute>
                  <Reminders />
                </ProtectedRoute>
              }
            />
            <Route
              path="savings"
              element={
                <ProtectedRoute>
                  <SavingsGoals />
                </ProtectedRoute>
              }
            />
            <Route
              path="account"
              element={
                <ProtectedRoute>
                  <Account />
                </ProtectedRoute>
              }
            />
          </Route>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/register" element={<Register />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
