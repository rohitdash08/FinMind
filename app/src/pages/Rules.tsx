import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dailog';
import { useToast } from '@/hooks/use-toast';
import {
  listRules,
  createRule,
  updateRule,
  deleteRule,
  type AutoTagRule,
  type RuleCondition,
  type ConditionType,
} from '@/api/rules';
import { listCategories, type Category } from '@/api/categories';

const CONDITION_LABELS: Record<ConditionType, string> = {
  keyword_match: 'Keyword Match (notes)',
  merchant_match: 'Merchant Match (notes)',
  amount_range: 'Amount Range',
};

export default function Rules() {
  const { toast } = useToast();
  const [rules, setRules] = useState<AutoTagRule[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<AutoTagRule | null>(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [targetCategoryId, setTargetCategoryId] = useState('');
  const [priority, setPriority] = useState('0');
  const [conditions, setConditions] = useState<RuleCondition[]>([
    { type: 'keyword_match', value: '' },
  ]);

  const categoryMap = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [r, c] = await Promise.all([listRules(), listCategories()]);
      setRules(r);
      setCategories(c);
    } catch {
      toast({ title: 'Failed to load rules' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { void refresh(); }, [refresh]);

  function resetForm() {
    setName('');
    setTargetCategoryId('');
    setPriority('0');
    setConditions([{ type: 'keyword_match', value: '' }]);
    setEditing(null);
  }

  function openCreate() {
    resetForm();
    setOpen(true);
  }

  function openEdit(rule: AutoTagRule) {
    setEditing(rule);
    setName(rule.name);
    setTargetCategoryId(String(rule.target_category_id));
    setPriority(String(rule.priority));
    setConditions(rule.conditions.length > 0 ? [...rule.conditions] : [{ type: 'keyword_match', value: '' }]);
    setOpen(true);
  }

  function addCondition() {
    setConditions((prev) => [...prev, { type: 'keyword_match', value: '' }]);
  }

  function removeCondition(idx: number) {
    setConditions((prev) => prev.filter((_, i) => i !== idx));
  }

  function updateCondition(idx: number, patch: Partial<RuleCondition>) {
    setConditions((prev) => prev.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
  }
