import { useEffect, useState, useCallback } from 'react';
import {
  FinancialCard,
  FinancialCardContent,
  FinancialCardDescription,
  FinancialCardHeader,
  FinancialCardTitle,
} from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import {
  ArrowUpRight,
  ArrowDownRight,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Lightbulb,
  BarChart3,
  Calendar,
  Receipt,
} from 'lucide-react';
import { getWeeklyDigest, type WeeklyDigest } from '@/api/digest';
import { formatMoney } from '@/lib/currency';
