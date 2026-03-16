import { useEffect, useState } from "react";
import {
  listMerchants,
  createMerchant,
  updateMerchant,
  deleteMerchant,
  addAlias,
  removeAlias,
  mergeMerchants,
  suggestMerchants,
  Merchant,
} from "../api/merchants";

export default function Merchants() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [newName, setNewName] = useState("");
  const [newAliases, setNewAliases] = useState("");
  const [creating, setCreating] = useState(false);

  // alias modal state
  const [aliasTarget, setAliasTarget] = useState<Merchant | null>(null);
  const [aliasInput, setAliasInput] = useState("");

  // merge modal state
  const [mergeSource, setMergeSource] = useState<number | "">("");
  const [mergeTarget, setMergeTarget] = useState<number | "">("");

  // suggest state
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const load = (q?: string) => {
    setLoading(true);
    listMerchants(q)
      .then(setMerchants)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    load(search || undefined);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const aliases = newAliases
        .split(",")
        .map((a) => a.trim())
        .filter(Boolean);
      await createMerchant(newName.trim(), aliases.length ? aliases : undefined);
      setNewName("");
      setNewAliases("");
      load(search || undefined);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this merchant and all its aliases?")) return;
    try {
      await deleteMerchant(id);
      load(search || undefined);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  const handleAddAlias = async () => {
    if (!aliasTarget || !aliasInput.trim()) return;
    try {
      await addAlias(aliasTarget.id, aliasInput.trim());
      setAliasInput("");
      setAliasTarget(null);
      load(search || undefined);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  const handleRemoveAlias = async (merchant: Merchant, aliasId: number) => {
    try {
      await removeAlias(merchant.id, aliasId);
      load(search || undefined);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  const handleMerge = async () => {
    if (!mergeTarget || !mergeSource) return;
    try {
      await mergeMerchants(Number(mergeTarget), Number(mergeSource));
      setMergeSource("");
      setMergeTarget("");
      load(search || undefined);
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  };

  const handleSuggest = async () => {
    const res = await suggestMerchants(search, 10);
    setSuggestions(res.suggestions);
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Merchant & Payee Aliases</h1>
        <p className="text-gray-500 mt-1">
          Define canonical merchant names and map raw payee strings to them.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 p-3 text-red-700 text-sm">
          {error}
          <button className="ml-2 underline" onClick={() => setError(null)}>
            dismiss
          </button>
        </div>
      )}

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2 mb-4">
        <input
          className="flex-1 border rounded px-3 py-2 text-sm"
          placeholder="Search merchants…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button
          type="submit"
          className="px-4 py-2 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700"
        >
          Search
        </button>
        <button
          type="button"
          onClick={handleSuggest}
          className="px-4 py-2 border rounded text-sm font-medium hover:bg-gray-50"
        >
          Suggest from expenses
        </button>
      </form>

      {suggestions.length > 0 && (
        <div className="mb-4 rounded-lg bg-blue-50 border border-blue-200 p-3">
          <p className="text-xs font-medium text-blue-700 mb-2">Suggestions from expenses:</p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => { setNewName(s); setSuggestions([]); }}
                className="px-2 py-1 bg-white border border-blue-300 rounded text-xs hover:bg-blue-50"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Create form */}
      <form
        onSubmit={handleCreate}
        className="mb-6 rounded-lg border bg-gray-50 p-4 flex flex-col gap-3"
      >
        <p className="font-medium text-sm text-gray-700">Add new merchant</p>
        <div className="flex gap-2">
          <input
            className="flex-1 border rounded px-3 py-2 text-sm"
            placeholder="Canonical name (e.g. Starbucks)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            required
          />
        </div>
        <input
          className="border rounded px-3 py-2 text-sm"
          placeholder="Aliases (comma-separated, optional)"
          value={newAliases}
          onChange={(e) => setNewAliases(e.target.value)}
        />
        <button
          type="submit"
          disabled={creating}
          className="self-start px-4 py-2 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {creating ? "Adding…" : "Add Merchant"}
        </button>
      </form>

      {/* Merge form */}
      <div className="mb-6 rounded-lg border p-4">
        <p className="font-medium text-sm text-gray-700 mb-3">Merge merchants</p>
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Source (will be deleted)</label>
            <select
              className="border rounded px-2 py-1 text-sm"
              value={mergeSource}
              onChange={(e) => setMergeSource(Number(e.target.value) || "")}
            >
              <option value="">Select…</option>
              {merchants.map((m) => (
                <option key={m.id} value={m.id}>{m.canonical_name}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Target (kept)</label>
            <select
              className="border rounded px-2 py-1 text-sm"
              value={mergeTarget}
              onChange={(e) => setMergeTarget(Number(e.target.value) || "")}
            >
              <option value="">Select…</option>
              {merchants.map((m) => (
                <option key={m.id} value={m.id}>{m.canonical_name}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleMerge}
            disabled={!mergeSource || !mergeTarget}
            className="px-4 py-2 bg-amber-600 text-white rounded text-sm font-medium hover:bg-amber-700 disabled:opacity-50"
          >
            Merge →
          </button>
        </div>
      </div>

      {/* Merchant list */}
      {loading ? (
        <div className="flex h-32 items-center justify-center text-gray-500">Loading…</div>
      ) : merchants.length === 0 ? (
        <div className="flex h-32 items-center justify-center text-gray-400 text-sm">
          No merchants yet. Add one above or use "Suggest from expenses".
        </div>
      ) : (
        <div className="space-y-3">
          {merchants.map((m) => (
            <div key={m.id} className="rounded-lg border bg-white p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-gray-900">{m.canonical_name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{m.aliases.length} aliases</p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setAliasTarget(m); setAliasInput(""); }}
                    className="px-2 py-1 border rounded text-xs hover:bg-gray-50"
                  >
                    + Alias
                  </button>
                  <button
                    onClick={() => handleDelete(m.id)}
                    className="px-2 py-1 border border-red-200 text-red-600 rounded text-xs hover:bg-red-50"
                  >
                    Delete
                  </button>
                </div>
              </div>
              {m.aliases.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {m.aliases.map((a) => (
                    <span
                      key={a.id}
                      className="flex items-center gap-1 bg-gray-100 rounded-full px-2 py-0.5 text-xs text-gray-700"
                    >
                      {a.alias}
                      <button
                        onClick={() => handleRemoveAlias(m, a.id)}
                        className="text-gray-400 hover:text-red-500 leading-none"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {/* Inline alias input */}
              {aliasTarget?.id === m.id && (
                <div className="mt-3 flex gap-2">
                  <input
                    autoFocus
                    className="flex-1 border rounded px-2 py-1 text-sm"
                    placeholder="New alias…"
                    value={aliasInput}
                    onChange={(e) => setAliasInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAddAlias()}
                  />
                  <button
                    onClick={handleAddAlias}
                    className="px-3 py-1 bg-indigo-600 text-white rounded text-sm"
                  >
                    Add
                  </button>
                  <button
                    onClick={() => setAliasTarget(null)}
                    className="px-3 py-1 border rounded text-sm"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
