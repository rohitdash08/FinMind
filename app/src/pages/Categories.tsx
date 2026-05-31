import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Category } from '../api/categories';
import { listCategories, createCategory, updateCategory, deleteCategory } from '../api/categories';
import { getToken } from '../lib/auth';
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
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

export default function Categories() {
  const { toast } = useToast();
  const nav = useNavigate();
  const [items, setItems] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');

  useEffect(() => {
    if (!getToken()) {
      nav('/signin', { replace: true });
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const data = await listCategories();
      setItems(data);
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to load categories');
      setError(message);
      toast({ title: 'Failed to load categories', description: message || 'Please try again.' });
    } finally {
      setLoading(false);
    }
  }

  async function onAdd() {
    if (!newName.trim()) return;
    setSaving(true);
    try {
      const created = await createCategory(newName.trim());
      setItems((prev) => [created, ...prev]);
      setNewName('');
      toast({ title: 'Category created' });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to create');
      setError(message);
      toast({ title: 'Failed to create category', description: message || 'Please try again.' });
    } finally {
      setSaving(false);
    }
  }

  async function onSaveEdit(id: number) {
    if (!editName.trim()) return;
    setSaving(true);
    try {
      const updated = await updateCategory(id, editName.trim());
      setItems((prev) => prev.map((x) => (x.id === id ? updated : x)));
      setEditingId(null);
      setEditName('');
      toast({ title: 'Category updated' });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to update');
      setError(message);
      toast({ title: 'Failed to update category', description: message || 'Please try again.' });
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: number) {
    setSaving(true);
    try {
      await deleteCategory(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
      toast({ title: 'Category deleted' });
    } catch (error: unknown) {
      const message = getErrorMessage(error, 'Failed to delete');
      setError(message);
      toast({ title: 'Failed to delete category', description: message || 'Please try again.' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap space-y-6">
      <div className="page-header">
        <div className="relative">
          <h2 className="page-title text-2xl md:text-3xl">Categories</h2>
          <p className="page-subtitle">Create and manage categories to keep expense insights clean and useful.</p>
        </div>
      </div>

      <div className="card card-interactive space-y-3 fade-in-up">
        <Label htmlFor="new-category">New category</Label>
        <div className="flex gap-2">
          <Input
            id="new-category"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="e.g., Groceries"
          />
          <Button onClick={onAdd} disabled={saving || !newName.trim()}>Add</Button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {loading ? (
        <div className="card">Loading...</div>
      ) : (
        <div className="space-y-3">
          {items.map((c) => (
            <div key={c.id} className="card card-interactive flex items-center justify-between gap-3 fade-in-up">
              {editingId === c.id ? (
                <div className="flex w-full items-center gap-2">
                  <Input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder="Category name" />
                  <Button onClick={() => onSaveEdit(c.id)} disabled={saving || !editName.trim()}>Save</Button>
                  <Button variant="outline" onClick={() => { setEditingId(null); setEditName(''); }}>
                    Cancel
                  </Button>
                </div>
              ) : (
                <>
                  <div className="font-medium text-foreground">{c.name}</div>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => { setEditingId(c.id); setEditName(c.name); }}>
                      Edit
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="outline">Delete</Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete category?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This action cannot be undone. This will permanently delete the category "{c.name}".
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={() => onDelete(c.id)}>Delete</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </>
              )}
            </div>
          ))}
          {items.length === 0 && <div className="card text-sm text-muted-foreground">No categories yet. Create your first one above.</div>}
        </div>
      )}
    </div>
  );
}
  const getErrorMessage = (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback;
