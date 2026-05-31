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
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';
import { useToast } from '@/hooks/use-toast';
import {
  listExpenses,
  createExpense,
  updateExpense,
  deleteExpense,
  previewExpenseImport,
  commitExpenseImport,
  listRecurringExpenses,
  createRecurringExpense,
  generateRecurringExpenses,
  type Expense,
  type ImportTransaction,
  type RecurringExpense,
} from '@/api/expenses';
import { listCategories, type Category } from '@/api/categories';
import { formatMoney } from '@/lib/currency';

export default function Expenses() {
  const { toast } = useToast();
  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;
  const [items, setItems] = useState<Expense[]>([]);
  const [allItems, setAllItems] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [categories, setCategories] = useState<Category[]>([]);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Expense | null>(null);

  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [date, setDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [categoryId, setCategoryId] = useState<string>('');
  const [saving, setSaving] = useState(false);

  const [importFile, setImportFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportTransaction[]>([]);
  const [previewDuplicates, setPreviewDuplicates] = useState<number>(0);
  const [importLoading, setImportLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [recurringItems, setRecurringItems] = useState<RecurringExpense[]>([]);
  const [recurringAmount, setRecurringAmount] = useState('');
  const [recurringDescription, setRecurringDescription] = useState('');
  const [recurringCadence, setRecurringCadence] =
    useState<'DAILY' | 'WEEKLY' | 'MONTHLY' | 'YEARLY'>('MONTHLY');
  const [recurringStartDate, setRecurringStartDate] = useState<string>(
    () => new Date().toISOString().slice(0, 10),
  );
  const [recurringEndDate, setRecurringEndDate] = useState<string>('');
  const [recurringSaving, setRecurringSaving] = useState(false);

  const [from, setFrom] = useState<string>('');
  const [to, setTo] = useState<string>('');
  const [filterCategoryId, setFilterCategoryId] = useState<string>('');
  const [search, setSearch] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listExpenses({
        from: from || undefined,
        to: to || undefined,
        category_id: filterCategoryId ? Number(filterCategoryId) : undefined,
        search: search || undefined,
        page,
        page_size: pageSize,
      });
      setAllItems(data);
      setItems(data.slice(0, pageSize));
      setPage(1);
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to load expenses');
      setError(message);
      toast({ title: 'Failed to load expenses', description: message || 'Please try again.' });
    } finally {
      setLoading(false);
    }
  }, [filterCategoryId, from, page, pageSize, search, to, toast]);

  const loadCategories = useCallback(async () => {
    try {
      const cats = await listCategories();
      setCategories(cats);
    } catch {
      toast({ title: 'Failed to load categories', description: 'Please try again.' });
    }
  }, [toast]);

  const loadRecurring = useCallback(async () => {
    try {
      const data = await listRecurringExpenses();
      setRecurringItems(data);
    } catch {
      toast({
        title: 'Failed to load recurring expenses',
        description: 'Please try again.',
      });
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
    void loadCategories();
    void loadRecurring();
  }, [refresh, loadCategories, loadRecurring]);

  function resetForm() {
    setAmount('');
    setDescription('');
    setDate(new Date().toISOString().slice(0, 10));
    setCategoryId('');
    setEditing(null);
  }

  function openCreate() {
    resetForm();
    setOpen(true);
  }

  function openEdit(exp: Expense) {
    setEditing(exp);
    setAmount(String(exp.amount));
    setDescription(exp.description || '');
    setDate(exp.date.slice(0, 10));
    setCategoryId(exp.category_id ? String(exp.category_id) : '');
    setOpen(true);
  }

  function validateForm() {
    if (!amount || isNaN(Number(amount)) || Number(amount) <= 0) {
      return 'Please enter a valid amount greater than 0';
    }
    if (!description.trim()) {
      return 'Description is required';
    }
    if (!date) {
      return 'Date is required';
    }
    return null;
  }

  async function onSubmit() {
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (editing) {
        const updated = await updateExpense(editing.id, {
          amount: Number(amount),
          description,
          date,
          category_id: categoryId ? Number(categoryId) : null,
        });
        setAllItems((prev) => prev.map((x) => (x.id === editing.id ? updated : x)));
        setItems((prev) => prev.map((x) => (x.id === editing.id ? updated : x)));
        toast({ title: 'Expense updated' });
      } else {
        const created = await createExpense({
          amount: Number(amount),
          description,
          date,
          category_id: categoryId ? Number(categoryId) : null,
        });
        setAllItems((prev) => [created, ...prev]);
        setItems((prev) => (page === 1 ? [created, ...prev].slice(0, pageSize) : prev));
        toast({ title: 'Expense created' });
      }
      setOpen(false);
      resetForm();
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to save expense');
      setError(message);
      toast({ title: 'Failed to save expense', description: message || 'Please try again.' });
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: number) {
    setSaving(true);
    try {
      await deleteExpense(id);
      const newAll = allItems.filter((x) => x.id !== id);
      setAllItems(newAll);
      const newTotalPages = Math.max(1, Math.ceil(newAll.length / pageSize));
      const nextPage = Math.min(page, newTotalPages);
      const start = (nextPage - 1) * pageSize;
      const end = start + pageSize;
      setItems(newAll.slice(start, end));
      setPage(nextPage);
      toast({ title: 'Expense deleted' });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to delete');
      setError(message);
      toast({ title: 'Failed to delete expense', description: message || 'Please try again.' });
    } finally {
      setSaving(false);
    }
  }

  async function onPreviewImport() {
    if (!importFile) {
      setError('Choose a PDF or CSV file before previewing import');
      return;
    }
    setImportLoading(true);
    setError(null);
    try {
      const data = await previewExpenseImport(importFile);
      setPreview(data.transactions);
      setPreviewDuplicates(data.duplicates);
      toast({ title: 'Import preview ready', description: `${data.total} rows parsed.` });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to preview import');
      setError(message);
      toast({ title: 'Failed to preview import', description: message || 'Please try again.' });
    } finally {
      setImportLoading(false);
    }
  }

  async function onCommitImport() {
    if (preview.length === 0) {
      setError('No preview rows to import');
      return;
    }
    setImporting(true);
    setError(null);
    try {
      const res = await commitExpenseImport(preview);
      toast({
        title: 'Import complete',
        description: `${res.inserted} added, ${res.duplicates} duplicates skipped.`,
      });
      setPreview([]);
      setPreviewDuplicates(0);
      setImportFile(null);
      await refresh();
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to import expenses');
      setError(message);
      toast({ title: 'Failed to import expenses', description: message || 'Please try again.' });
    } finally {
      setImporting(false);
    }
  }

  async function onCreateRecurring() {
    if (!recurringDescription.trim() || !recurringAmount || Number(recurringAmount) <= 0) {
      setError('Recurring expense requires valid amount and description');
      return;
    }
    setRecurringSaving(true);
    try {
      const created = await createRecurringExpense({
        amount: Number(recurringAmount),
        description: recurringDescription.trim(),
        category_id: categoryId ? Number(categoryId) : null,
        cadence: recurringCadence,
        start_date: recurringStartDate,
        end_date: recurringEndDate || null,
      });
      setRecurringItems((prev) => [created, ...prev]);
      setRecurringAmount('');
      setRecurringDescription('');
      setRecurringCadence('MONTHLY');
      setRecurringStartDate(new Date().toISOString().slice(0, 10));
      setRecurringEndDate('');
      toast({ title: 'Recurring expense created' });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to create recurring expense');
      setError(message);
      toast({ title: 'Failed to create recurring expense', description: message || 'Please try again.' });
    } finally {
      setRecurringSaving(false);
    }
  }

  async function onGenerateRecurring(id: number) {
    setRecurringSaving(true);
    try {
      const throughDate = new Date().toISOString().slice(0, 10);
      const result = await generateRecurringExpenses(id, throughDate);
      toast({
        title: 'Recurring generation complete',
        description: `${result.inserted} transactions generated.`,
      });
      await refresh();
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to generate recurring expenses');
      setError(message);
      toast({ title: 'Failed to generate recurring expenses', description: message || 'Please try again.' });
    } finally {
      setRecurringSaving(false);
    }
  }

  const categoryMap = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories]);
  const totals = useMemo(() => {
    const sum = allItems.reduce((acc, e) => acc + Number(e.amount || 0), 0);
    return { sum };
  }, [allItems]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(allItems.length / pageSize)), [allItems.length, pageSize]);

  function goToPage(target: number) {
    const p = Math.min(Math.max(1, target), totalPages);
    setPage(p);
    const start = (p - 1) * pageSize;
    const end = start + pageSize;
    setItems(allItems.slice(start, end));
  }

  return (
    <div className="page-wrap space-y-5">
      <div className="page-header">
      <div className="relative flex items-center justify-between gap-4">
        <div>
          <h2 className="page-title text-2xl md:text-3xl">Expenses</h2>
          <p className="page-subtitle">Track spending manually or import statements from PDF/CSV.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button onClick={openCreate}>Open Full Form</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editing ? 'Edit Expense' : 'New Expense'}</DialogTitle>
              <DialogDescription>Enter amount, description, date and category.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="amount">Amount</Label>
                  <Input id="amount" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} min="0" step="0.01" />
                </div>
                <div>
                  <Label htmlFor="date">Date</Label>
                  <Input id="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
                </div>
              </div>
              <div>
                <Label htmlFor="description">Description</Label>
                <Input id="description" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g., Groceries at Walmart" />
              </div>
              <div>
                <Label htmlFor="category">Category</Label>
                <select id="category" className="input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                  <option value="">Uncategorized</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            </div>
            {error && <div className="error">{error}</div>}
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
              <Button onClick={onSubmit} disabled={saving}>{editing ? 'Save' : 'Create'}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card card-interactive p-4 space-y-3 fade-in-up">
          <h3 className="text-base font-semibold">Quick Add</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="q-amount">Amount</Label>
              <Input id="q-amount" type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="q-date">Date</Label>
              <Input id="q-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
          </div>
          <div>
            <Label htmlFor="q-description">Description</Label>
            <Input id="q-description" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Add merchant or note" />
          </div>
          <div>
            <Label htmlFor="q-category">Category</Label>
            <select id="q-category" className="input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">Uncategorized</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <Button onClick={onSubmit} disabled={saving}>Save Expense</Button>
        </div>

        <div className="card card-interactive p-4 space-y-3 fade-in-up">
          <h3 className="text-base font-semibold">Import Bank Statement</h3>
          <p className="text-sm text-muted-foreground">Upload PDF or CSV, review parsed rows, then confirm import.</p>
          <Input
            aria-label="statement file"
            type="file"
            accept=".pdf,.csv,application/pdf,text/csv"
            onChange={(e) => setImportFile(e.target.files?.[0] || null)}
          />
          <div className="flex gap-2">
            <Button variant="outline" onClick={onPreviewImport} disabled={importLoading || !importFile}>Preview Import</Button>
            <Button onClick={onCommitImport} disabled={importing || preview.length === 0}>Confirm Import</Button>
          </div>
          {preview.length > 0 && (
            <div className="rounded-md border p-3">
              <div className="mb-2 text-sm text-muted-foreground">
                Preview rows: {preview.length} | Detected duplicates: {previewDuplicates}
              </div>
              <div className="max-h-40 overflow-y-auto text-sm">
                {preview.slice(0, 10).map((row, idx) => (
                  <div key={`${row.date}-${row.amount}-${idx}`} className="grid grid-cols-3 gap-2 border-b py-1">
                    <span>{row.date}</span>
                    <span>{row.description}</span>
                    <span className="text-right">{formatMoney(Number(row.amount))}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="card card-interactive p-4 space-y-4 fade-in-up">
        <h3 className="text-base font-semibold">Recurring Expenses</h3>
        <div className="grid gap-3 md:grid-cols-6">
          <Input
            aria-label="recurring amount"
            type="number"
            min="0"
            step="0.01"
            placeholder="Amount"
            value={recurringAmount}
            onChange={(e) => setRecurringAmount(e.target.value)}
          />
          <Input
            aria-label="recurring description"
            placeholder="Description"
            value={recurringDescription}
            onChange={(e) => setRecurringDescription(e.target.value)}
          />
          <select
            aria-label="recurring cadence"
            className="input"
            value={recurringCadence}
            onChange={(e) => setRecurringCadence(e.target.value as 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'YEARLY')}
          >
            <option value="DAILY">Daily</option>
            <option value="WEEKLY">Weekly</option>
            <option value="MONTHLY">Monthly</option>
            <option value="YEARLY">Yearly</option>
          </select>
          <Input
            aria-label="recurring start date"
            type="date"
            value={recurringStartDate}
            onChange={(e) => setRecurringStartDate(e.target.value)}
          />
          <Input
            aria-label="recurring end date"
            type="date"
            value={recurringEndDate}
            onChange={(e) => setRecurringEndDate(e.target.value)}
          />
          <Button onClick={onCreateRecurring} disabled={recurringSaving}>
            Add Recurring
          </Button>
        </div>
        <div className="space-y-2">
          {recurringItems.length === 0 ? (
            <div className="text-sm text-muted-foreground">No recurring expenses configured.</div>
          ) : (
            recurringItems.map((r) => (
              <div key={r.id} className="interactive-row flex items-center justify-between border-b py-2">
                <div className="text-sm">
                  {r.description} • {r.cadence} • {formatMoney(r.amount, r.currency)}
                </div>
                <Button variant="outline" onClick={() => onGenerateRecurring(r.id)} disabled={recurringSaving}>
                  Generate Now
                </Button>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="card p-4 grid md:grid-cols-5 gap-3 fade-in-up">
        <div>
          <Label htmlFor="from">From</Label>
          <Input id="from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="to">To</Label>
          <Input id="to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="fcat">Category</Label>
          <select id="fcat" className="input" value={filterCategoryId} onChange={(e) => setFilterCategoryId(e.target.value)}>
            <option value="">All</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="search">Search</Label>
          <Input id="search" placeholder="description contains..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="flex items-end gap-2">
          <Button variant="outline" onClick={() => { setFrom(''); setTo(''); setFilterCategoryId(''); setSearch(''); setPage(1); }}>Reset</Button>
          <Button onClick={() => { setPage(1); refresh(); }}>Apply</Button>
        </div>
      </div>

      {loading ? (
        <div className="card">Loading...</div>
      ) : (
        <div className="card fade-in-up">
          {items.length === 0 ? (
            <div className="text-sm text-muted-foreground">No expenses yet. Add your first one.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="py-2">Date</th>
                    <th className="py-2">Description</th>
                    <th className="py-2">Category</th>
                    <th className="py-2">Amount</th>
                    <th className="py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((e) => (
                    <tr key={e.id} className="border-t transition-colors hover:bg-muted/30">
                      <td className="py-2">{e.date.slice(0, 10)}</td>
                      <td className="py-2">{e.description}</td>
                      <td className="py-2">{e.category_id ? categoryMap.get(e.category_id) : '—'}</td>
                      <td className="py-2 font-medium">{formatMoney(e.amount, e.currency)}</td>
                      <td className="py-2">
                        <div className="flex gap-2 justify-end">
                          <Button variant="outline" onClick={() => openEdit(e)}>Edit</Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button variant="outline">Delete</Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>Delete expense?</AlertDialogTitle>
                                <AlertDialogDescription>
                                  This action cannot be undone. This will permanently delete this expense.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={() => onDelete(e.id)}>Delete</AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </div>
                      </td>
                    </tr>
                  ))}
                  <tr className="border-t bg-muted/30">
                    <td className="py-2" colSpan={3}>Total</td>
                    <td className="py-2 font-semibold">{formatMoney(totals.sum)}</td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-4 flex items-center justify-between">
            <div className="text-xs text-muted-foreground">Page {page}</div>
            <Pagination>
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious href="#" onClick={(e) => { e.preventDefault(); if (page > 1) { goToPage(page - 1); } }} />
                </PaginationItem>
                <PaginationItem>
                  <PaginationLink href="#" isActive>
                    {page}
                  </PaginationLink>
                </PaginationItem>
                <PaginationItem>
                  <PaginationNext href="#" onClick={(e) => { e.preventDefault(); if (page < totalPages) { goToPage(page + 1); } }} />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
            <div className="flex items-center gap-2">
              <Label htmlFor="ps">Page size</Label>
              <select id="ps" className="input" value={pageSize} onChange={(e) => {
                const size = Number(e.target.value);
                setPageSize(size);
                setItems(allItems.slice(0, size));
                setPage(1);
              }}>
                {[10, 20, 50].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}
      {error && <div className="text-sm text-red-600">{error}</div>}
    </div>
  );
}
