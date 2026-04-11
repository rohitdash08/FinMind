import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type {
  AutoTagRule,
  RuleCondition,
  RuleActions,
  DryRunResult,
} from '../api/rules';
import {
  listRules,
  createRule,
  updateRule,
  deleteRule,
  testRule,
  applyAllRules,
} from '../api/rules';
import { listCategories } from '../api/categories';
import type { Category } from '../api/categories';
import { getToken } from '../lib/auth';
import { useToast } from '@/hooks/use-toast';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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

// ── types ──────────────────────────────────────────────────────────────────────

type ConditionField = RuleCondition['field'];
type ConditionOperator = RuleCondition['operator'];

const FIELDS: { value: ConditionField; label: string }[] = [
  { value: 'description', label: 'Description' },
  { value: 'amount', label: 'Amount' },
  { value: 'expense_type', label: 'Expense type' },
];

const OPERATORS: Record<ConditionField, { value: ConditionOperator; label: string }[]> = {
  description: [
    { value: 'contains', label: 'contains' },
    { value: 'not_contains', label: 'does not contain' },
    { value: 'equals', label: 'equals' },
    { value: 'regex', label: 'matches regex' },
  ],
  amount: [
    { value: 'gt', label: 'greater than' },
    { value: 'lt', label: 'less than' },
    { value: 'equals', label: 'equals' },
    { value: 'between', label: 'between' },
  ],
  expense_type: [
    { value: 'equals', label: 'equals' },
  ],
};

interface DraftCondition {
  field: ConditionField;
  operator: ConditionOperator;
  value: string;
  valueTo: string; // for "between"
}

interface DraftRule {
  name: string;
  priority: string;
  conditions: DraftCondition[];
  actions: {
    set_category_id: string;
    add_tags: string; // comma-separated
    set_expense_type: string;
  };
  active: boolean;
}

const emptyCondition = (): DraftCondition => ({
  field: 'description',
  operator: 'contains',
  value: '',
  valueTo: '',
});

const emptyDraft = (): DraftRule => ({
  name: '',
  priority: '0',
  conditions: [emptyCondition()],
  actions: { set_category_id: '', add_tags: '', set_expense_type: '' },
  active: true,
});

// ── helpers ────────────────────────────────────────────────────────────────────

function draftToPayload(draft: DraftRule): { conditions: RuleCondition[]; actions: RuleActions } {
  const conditions: RuleCondition[] = draft.conditions
    .filter((c) => c.value.trim() !== '')
    .map((c) => {
      const value: RuleCondition['value'] =
        c.operator === 'between'
          ? [parseFloat(c.value) || 0, parseFloat(c.valueTo) || 0]
          : c.field === 'amount' && c.operator !== 'regex'
          ? parseFloat(c.value) || 0
          : c.value.trim();
      return { field: c.field, operator: c.operator, value } as RuleCondition;
    });

  const actions: RuleActions = {};
  if (draft.actions.set_category_id) {
    actions.set_category_id = parseInt(draft.actions.set_category_id, 10);
  }
  const tags = draft.actions.add_tags
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  if (tags.length > 0) actions.add_tags = tags;
  if (draft.actions.set_expense_type) {
    actions.set_expense_type = draft.actions.set_expense_type as 'EXPENSE' | 'INCOME';
  }
  return { conditions, actions };
}

function ruleToDraft(rule: AutoTagRule): DraftRule {
  return {
    name: rule.name,
    priority: String(rule.priority),
    active: rule.active,
    conditions:
      rule.conditions.length > 0
        ? rule.conditions.map((c) => ({
            field: c.field,
            operator: c.operator,
            value: Array.isArray(c.value) ? String(c.value[0]) : String(c.value),
            valueTo: Array.isArray(c.value) ? String(c.value[1]) : '',
          }))
        : [emptyCondition()],
    actions: {
      set_category_id: rule.actions.set_category_id != null ? String(rule.actions.set_category_id) : '',
      add_tags: (rule.actions.add_tags || []).join(', '),
      set_expense_type: rule.actions.set_expense_type || '',
    },
  };
}

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

// ── RuleForm ──────────────────────────────────────────────────────────────────

function RuleForm({
  draft,
  onChange,
  categories,
}: {
  draft: DraftRule;
  onChange: (d: DraftRule) => void;
  categories: Category[];
}) {
  function setField<K extends keyof DraftRule>(k: K, v: DraftRule[K]) {
    onChange({ ...draft, [k]: v });
  }

  function updateCondition(i: number, partial: Partial<DraftCondition>) {
    const updated = draft.conditions.map((c, idx) =>
      idx === i ? { ...c, ...partial } : c,
    );
    onChange({ ...draft, conditions: updated });
  }

  function addCondition() {
    onChange({ ...draft, conditions: [...draft.conditions, emptyCondition()] });
  }

  function removeCondition(i: number) {
    onChange({ ...draft, conditions: draft.conditions.filter((_, idx) => idx !== i) });
  }

  function updateAction<K extends keyof DraftRule['actions']>(k: K, v: string) {
    onChange({ ...draft, actions: { ...draft.actions, [k]: v } });
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label>Rule name</Label>
          <Input
            value={draft.name}
            onChange={(e) => setField('name', e.target.value)}
            placeholder="e.g., Coffee purchases"
          />
        </div>
        <div className="space-y-1">
          <Label>Priority (lower = higher priority)</Label>
          <Input
            type="number"
            value={draft.priority}
            onChange={(e) => setField('priority', e.target.value)}
            placeholder="0"
          />
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <Label>Conditions (ALL must match)</Label>
          <Button variant="outline" size="sm" onClick={addCondition}>
            + Add condition
          </Button>
        </div>
        <div className="space-y-2">
          {draft.conditions.map((cond, i) => (
            <div
              key={i}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-border/60 bg-muted/30 p-2"
            >
              <select
                className="rounded border border-border bg-background px-2 py-1 text-sm"
                value={cond.field}
                onChange={(e) =>
                  updateCondition(i, {
                    field: e.target.value as ConditionField,
                    operator: OPERATORS[e.target.value as ConditionField][0].value,
                  })
                }
              >
                {FIELDS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>

              <select
                className="rounded border border-border bg-background px-2 py-1 text-sm"
                value={cond.operator}
                onChange={(e) =>
                  updateCondition(i, { operator: e.target.value as ConditionOperator })
                }
              >
                {OPERATORS[cond.field].map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>

              {cond.field === 'expense_type' ? (
                <select
                  className="rounded border border-border bg-background px-2 py-1 text-sm"
                  value={cond.value}
                  onChange={(e) => updateCondition(i, { value: e.target.value })}
                >
                  <option value="">—</option>
                  <option value="EXPENSE">EXPENSE</option>
                  <option value="INCOME">INCOME</option>
                </select>
              ) : cond.operator === 'between' ? (
                <>
                  <Input
                    type="number"
                    className="w-24 text-sm"
                    placeholder="min"
                    value={cond.value}
                    onChange={(e) => updateCondition(i, { value: e.target.value })}
                  />
                  <span className="text-sm text-muted-foreground">and</span>
                  <Input
                    type="number"
                    className="w-24 text-sm"
                    placeholder="max"
                    value={cond.valueTo}
                    onChange={(e) => updateCondition(i, { valueTo: e.target.value })}
                  />
                </>
              ) : (
                <Input
                  className="w-44 text-sm"
                  type={['gt', 'lt', 'equals'].includes(cond.operator) && cond.field === 'amount' ? 'number' : 'text'}
                  value={cond.value}
                  onChange={(e) => updateCondition(i, { value: e.target.value })}
                  placeholder={cond.field === 'description' ? 'e.g., starbucks' : 'value'}
                />
              )}

              {draft.conditions.length > 1 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => removeCondition(i)}
                  className="ml-auto text-destructive"
                >
                  Remove
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div>
        <Label className="mb-2 block">Actions (applied when all conditions match)</Label>
        <div className="space-y-2 rounded-lg border border-border/60 bg-muted/30 p-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Set category</Label>
              <select
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
                value={draft.actions.set_category_id}
                onChange={(e) => updateAction('set_category_id', e.target.value)}
              >
                <option value="">— no change —</option>
                {categories.map((c) => (
                  <option key={c.id} value={String(c.id)}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Set expense type</Label>
              <select
                className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
                value={draft.actions.set_expense_type}
                onChange={(e) => updateAction('set_expense_type', e.target.value)}
              >
                <option value="">— no change —</option>
                <option value="EXPENSE">EXPENSE</option>
                <option value="INCOME">INCOME</option>
              </select>
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Add tags (comma-separated)</Label>
            <Input
              value={draft.actions.add_tags}
              onChange={(e) => updateAction('add_tags', e.target.value)}
              placeholder="e.g., food, dining, coffee"
            />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          id="rule-active"
          type="checkbox"
          checked={draft.active}
          onChange={(e) => setField('active', e.target.checked)}
          className="h-4 w-4 rounded border-border"
        />
        <Label htmlFor="rule-active" className="text-sm">
          Active (rule fires automatically on new transactions)
        </Label>
      </div>
    </div>
  );
}

// ── DryRun panel ───────────────────────────────────────────────────────────────

function DryRunPanel({ categories }: { categories: Category[] }) {
  const { toast } = useToast();
  const [desc, setDesc] = useState('');
  const [amount, setAmount] = useState('');
  const [result, setResult] = useState<DryRunResult | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    if (!desc && !amount) return;
    setLoading(true);
    try {
      const res = await testRule({
        description: desc || undefined,
        amount: amount ? parseFloat(amount) : undefined,
      });
      setResult(res);
    } catch (err) {
      toast({ title: 'Dry-run failed', description: getErrorMessage(err, 'Unknown error') });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card space-y-3 fade-in-up">
      <h3 className="font-semibold text-foreground">Dry-run tester</h3>
      <p className="text-sm text-muted-foreground">
        Enter a transaction and see which rules would match without saving anything.
      </p>
      <div className="flex flex-wrap gap-2">
        <Input
          className="flex-1 min-w-40"
          placeholder="Description (e.g., Starbucks)"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
        />
        <Input
          className="w-32"
          type="number"
          placeholder="Amount"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <Button onClick={run} disabled={loading || (!desc && !amount)}>
          Test
        </Button>
      </div>

      {result && (
        <div className="rounded-lg border border-border/60 bg-muted/40 p-3 text-sm space-y-1">
          <div>
            <span className="font-medium">Matched rules:</span>{' '}
            {result.matched_rule_ids.length > 0
              ? result.matched_rule_ids.join(', ')
              : 'none'}
          </div>
          <div>
            <span className="font-medium">Category:</span>{' '}
            {result.changes.set_category_id != null
              ? categories.find((c) => c.id === result.changes.set_category_id)?.name ??
                `ID ${result.changes.set_category_id}`
              : 'unchanged'}
          </div>
          <div>
            <span className="font-medium">Tags:</span>{' '}
            {result.changes.add_tags.length > 0
              ? result.changes.add_tags.join(', ')
              : 'none'}
          </div>
          <div>
            <span className="font-medium">Expense type:</span>{' '}
            {result.changes.set_expense_type ?? 'unchanged'}
          </div>
        </div>
      )}
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function Rules() {
  const { toast } = useToast();
  const nav = useNavigate();
  const [rules, setRules] = useState<AutoTagRule[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<DraftRule>(emptyDraft());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<DraftRule>(emptyDraft());

  useEffect(() => {
    if (!getToken()) {
      nav('/signin', { replace: true });
      return;
    }
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    setLoading(true);
    try {
      const [r, cats] = await Promise.all([listRules(), listCategories()]);
      setRules(r);
      setCategories(cats);
    } catch (err) {
      toast({ title: 'Failed to load rules', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setLoading(false);
    }
  }

  async function onCreate() {
    const { conditions, actions } = draftToPayload(draft);
    if (!Object.keys(actions).length) {
      toast({ title: 'At least one action required', description: 'Set a category, tags, or expense type.' });
      return;
    }
    setSaving(true);
    try {
      const rule = await createRule({
        name: draft.name.trim(),
        priority: parseInt(draft.priority, 10) || 0,
        conditions,
        actions,
        active: draft.active,
      });
      setRules((prev) => [...prev, rule].sort((a, b) => a.priority - b.priority));
      setDraft(emptyDraft());
      setShowCreate(false);
      toast({ title: 'Rule created' });
    } catch (err) {
      toast({ title: 'Failed to create rule', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  async function onUpdate(id: number) {
    const { conditions, actions } = draftToPayload(editDraft);
    setSaving(true);
    try {
      const updated = await updateRule(id, {
        name: editDraft.name.trim(),
        priority: parseInt(editDraft.priority, 10) || 0,
        conditions,
        actions,
        active: editDraft.active,
      });
      setRules((prev) => prev.map((r) => (r.id === id ? updated : r)));
      setEditingId(null);
      toast({ title: 'Rule updated' });
    } catch (err) {
      toast({ title: 'Failed to update rule', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: number) {
    setSaving(true);
    try {
      await deleteRule(id);
      setRules((prev) => prev.filter((r) => r.id !== id));
      toast({ title: 'Rule deleted' });
    } catch (err) {
      toast({ title: 'Failed to delete rule', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  async function onApplyAll() {
    setSaving(true);
    try {
      const result = await applyAllRules();
      toast({
        title: 'Rules applied',
        description: `${result.updated} expense${result.updated !== 1 ? 's' : ''} updated, ${result.skipped} skipped.`,
      });
    } catch (err) {
      toast({ title: 'Apply failed', description: getErrorMessage(err, 'Please try again.') });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h2 className="page-title text-2xl md:text-3xl">Auto-tagging rules</h2>
          <p className="page-subtitle">
            Define rules to automatically categorize and tag transactions when they are created or
            updated.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void onApplyAll()} disabled={saving}>
            Apply to existing
          </Button>
          <Button onClick={() => { setShowCreate(true); setDraft(emptyDraft()); }} disabled={showCreate}>
            New rule
          </Button>
        </div>
      </div>

      {showCreate && (
        <div className="card card-interactive space-y-4 fade-in-up">
          <h3 className="font-semibold text-foreground">New rule</h3>
          <RuleForm draft={draft} onChange={setDraft} categories={categories} />
          <div className="flex gap-2">
            <Button onClick={() => void onCreate()} disabled={saving || !draft.name.trim()}>
              Create rule
            </Button>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <DryRunPanel categories={categories} />

      {loading ? (
        <div className="card">Loading...</div>
      ) : rules.length === 0 ? (
        <div className="card text-sm text-muted-foreground">
          No rules yet. Create your first rule above.
        </div>
      ) : (
        <div className="space-y-3">
          {rules.map((rule) => (
            <div key={rule.id} className="card card-interactive fade-in-up">
              {editingId === rule.id ? (
                <div className="space-y-4">
                  <RuleForm draft={editDraft} onChange={setEditDraft} categories={categories} />
                  <div className="flex gap-2">
                    <Button
                      onClick={() => void onUpdate(rule.id)}
                      disabled={saving || !editDraft.name.trim()}
                    >
                      Save
                    </Button>
                    <Button variant="outline" onClick={() => setEditingId(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-foreground">{rule.name}</span>
                      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        p{rule.priority}
                      </span>
                      {!rule.active && (
                        <span className="rounded-full bg-destructive/15 px-2 py-0.5 text-xs text-destructive">
                          inactive
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground space-y-0.5">
                      {rule.conditions.length > 0 ? (
                        rule.conditions.map((c, i) => (
                          <div key={i}>
                            <span className="font-mono">{c.field}</span>{' '}
                            <span className="italic">{c.operator}</span>{' '}
                            <span className="font-mono">
                              {Array.isArray(c.value) ? c.value.join(' – ') : String(c.value)}
                            </span>
                          </div>
                        ))
                      ) : (
                        <div className="italic">matches everything</div>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs mt-1">
                      {rule.actions.set_category_id != null && (
                        <span className="rounded bg-primary/10 px-2 py-0.5 text-primary">
                          category:{' '}
                          {categories.find((c) => c.id === rule.actions.set_category_id)?.name ??
                            `#${rule.actions.set_category_id}`}
                        </span>
                      )}
                      {(rule.actions.add_tags || []).map((tag) => (
                        <span key={tag} className="rounded bg-secondary/60 px-2 py-0.5 text-secondary-foreground">
                          #{tag}
                        </span>
                      ))}
                      {rule.actions.set_expense_type && (
                        <span className="rounded bg-accent/20 px-2 py-0.5 text-accent-foreground">
                          type: {rule.actions.set_expense_type}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setEditingId(rule.id);
                        setEditDraft(ruleToDraft(rule));
                      }}
                    >
                      Edit
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="outline" size="sm">
                          Delete
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete rule?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This will permanently delete the rule &quot;{rule.name}&quot;. Transactions
                            already tagged will not be affected.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={() => void onDelete(rule.id)}>
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
