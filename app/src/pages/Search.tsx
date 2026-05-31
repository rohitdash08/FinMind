import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  search,
  type SearchParams,
  type SearchResult,
  type SavedSearch,
  getSavedSearches,
  saveSearch,
  deleteSavedSearch,
} from '@/api/search';
import { listCategories, type Category } from '@/api/categories';
import { formatMoney } from '@/lib/currency';
import {
  Search as SearchIcon,
  Save,
  Trash2,
  X,
  TrendingUp,
  TrendingDown,
  FileText,
} from 'lucide-react';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [amountMin, setAmountMin] = useState('');
  const [amountMax, setAmountMax] = useState('');
  const [searchType, setSearchType] = useState<'all' | 'transactions' | 'bills'>('all');
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [saveName, setSaveName] = useState('');
  const [showSave, setShowSave] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    listCategories()
      .then(setCategories)
      .catch(() => {});
    setSavedSearches(getSavedSearches());
  }, []);

  const buildParams = useCallback((): SearchParams => ({
    q: query || undefined,
    from: from || undefined,
    to: to || undefined,
    category_id: categoryId ? Number(categoryId) : undefined,
    amount_min: amountMin ? Number(amountMin) : undefined,
    amount_max: amountMax ? Number(amountMax) : undefined,
    type: searchType,
    page,
    page_size: 20,
  }), [query, from, to, categoryId, amountMin, amountMax, searchType, page]);

  async function doSearch() {
    setLoading(true);
    setError(null);
    try {
      const res = await search(buildParams());
      setResults(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  function handleSave() {
    if (!saveName.trim()) return;
    const updated = saveSearch(saveName.trim(), buildParams());
    setSavedSearches(updated);
    setSaveName('');
    setShowSave(false);
  }

  function loadSaved(s: SavedSearch) {
    setQuery(s.params.q || '');
    setFrom(s.params.from || '');
    setTo(s.params.to || '');
    setCategoryId(s.params.category_id ? String(s.params.category_id) : '');
    setAmountMin(s.params.amount_min ? String(s.params.amount_min) : '');
    setAmountMax(s.params.amount_max ? String(s.params.amount_max) : '');
    setSearchType(s.params.type || 'all');
    setPage(1);
  }

  function handleDelete(id: string) {
    const updated = deleteSavedSearch(id);
    setSavedSearches(updated);
  }

  function resetFilters() {
    setQuery('');
    setFrom('');
    setTo('');
    setCategoryId('');
    setAmountMin('');
    setAmountMax('');
    setSearchType('all');
    setPage(1);
    setResults(null);
  }

  return (
    <div className="page-wrap space-y-5">
      <div className="page-header">
        <h1 className="page-title">Advanced Search</h1>
        <p className="page-subtitle">Search across transactions and bills with multiple filters.</p>
      </div>

      <div className="card p-4 space-y-4 fade-in-up">
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <Label htmlFor="search-query" className="sr-only">Search query</Label>
            <Input
              id="search-query"
              placeholder="Search transactions and bills..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') doSearch(); }}
            />
          </div>
          <Button onClick={doSearch} disabled={loading}>
            <SearchIcon className="w-4 h-4 mr-1" />
            Search
          </Button>
          <Button variant="outline" onClick={() => setShowSave((v) => !v)}>
            <Save className="w-4 h-4 mr-1" />
            Save
          </Button>
        </div>

        {showSave && (
          <div className="flex items-center gap-2">
            <Input
              placeholder="Search name..."
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); }}
            />
            <Button size="sm" onClick={handleSave} disabled={!saveName.trim()}>
              Save Search
            </Button>
          </div>
        )}

        <details className="group">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground">
            Filters
          </summary>
          <div className="mt-3 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <div>
              <Label htmlFor="s-from">From</Label>
              <Input id="s-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="s-to">To</Label>
              <Input id="s-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="s-category">Category</Label>
              <select id="s-category" className="input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                <option value="">All</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="s-amin">Min Amount</Label>
              <Input id="s-amin" type="number" min="0" step="0.01" value={amountMin} onChange={(e) => setAmountMin(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="s-amax">Max Amount</Label>
              <Input id="s-amax" type="number" min="0" step="0.01" value={amountMax} onChange={(e) => setAmountMax(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="s-type">Type</Label>
              <select id="s-type" className="input" value={searchType} onChange={(e) => setSearchType(e.target.value as 'all' | 'transactions' | 'bills')}>
                <option value="all">All</option>
                <option value="transactions">Transactions</option>
                <option value="bills">Bills</option>
              </select>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <Button variant="outline" size="sm" onClick={resetFilters}>
              <X className="w-3.5 h-3.5 mr-1" />
              Reset
            </Button>
          </div>
        </details>
      </div>

      {savedSearches.length > 0 && (
        <div className="card p-3 fade-in-up">
          <h3 className="text-sm font-semibold mb-2">Saved Searches</h3>
          <div className="flex flex-wrap gap-2">
            {savedSearches.map((s) => (
              <div key={s.id} className="flex items-center gap-1 rounded-full border px-3 py-1 text-xs">
                <button
                  className="hover:text-primary"
                  onClick={() => { loadSaved(s); doSearch(); }}
                >
                  <Save className="w-3 h-3 inline mr-1" />
                  {s.name}
                </button>
                <button
                  className="text-muted-foreground hover:text-destructive ml-1"
                  onClick={() => handleDelete(s.id)}
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading && <div className="card">Searching...</div>}

      {error && <div className="error">{error}</div>}

      {results && !loading && (
        <div className="space-y-4 fade-in-up">
          <div className="text-sm text-muted-foreground">
            {results.total_count} result{results.total_count !== 1 ? 's' : ''} found
          </div>

          {results.transactions.map((t) => (
            <div key={`txn-${t.id}`} className="card card-interactive p-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                  t.expense_type === 'INCOME' ? 'bg-success-light text-success' : 'bg-destructive-light text-destructive'
                }`}>
                  {t.expense_type === 'INCOME' ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                </div>
                <div>
                  <div className="font-medium text-sm">{t.description}</div>
                  <div className="text-xs text-muted-foreground">{t.date} • Transaction</div>
                </div>
              </div>
              <div className={`font-semibold text-sm ${t.expense_type === 'INCOME' ? 'text-success' : ''}`}>
                {t.expense_type === 'INCOME' ? '+' : '-'}{formatMoney(t.amount, t.currency)}
              </div>
            </div>
          ))}

          {results.bills.map((b) => (
            <div key={`bill-${b.id}`} className="card card-interactive p-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-warning-light flex items-center justify-center">
                  <FileText className="w-4 h-4 text-warning" />
                </div>
                <div>
                  <div className="font-medium text-sm">{b.name}</div>
                  <div className="text-xs text-muted-foreground">{b.next_due_date} • Bill ({b.cadence})</div>
                </div>
              </div>
              <div className="font-semibold text-sm">{formatMoney(b.amount, b.currency)}</div>
            </div>
          ))}

          {results.transactions.length === 0 && results.bills.length === 0 && (
            <div className="card text-center py-6 text-muted-foreground">
              No results found. Try adjusting your filters.
            </div>
          )}

          {results.total_count > 20 && (
            <div className="flex justify-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                Previous
              </Button>
              <span className="text-sm text-muted-foreground self-center">Page {page}</span>
              <Button variant="outline" size="sm" onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
