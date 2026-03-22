import { useState, useEffect, useCallback } from 'react';
import {
  listGoals, createGoal, depositToGoal, deleteGoal,
  SavingsGoal, SavingsGoalCreate,
} from '../api/goals';

interface GoalCardProps { goal: SavingsGoal; onDeposit: (id: number) => void; onDelete: (id: number) => void; }

function MilestoneTrack({ goal }: { goal: SavingsGoal }) {
  return (
    <div className="mt-3">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{goal.current_amount.toLocaleString()} {goal.currency}</span>
        <span>{goal.target_amount.toLocaleString()} {goal.currency}</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
        <div
          className="bg-emerald-500 h-2.5 rounded-full transition-all duration-500"
          style={{ width: `${Math.min(goal.progress_pct, 100)}%` }}
        />
      </div>
      <div className="flex justify-between mt-2">
        {goal.milestones.map((ms) => (
          <div key={ms.percentage} className="flex flex-col items-center text-xs">
            <div className={`w-5 h-5 rounded-full flex items-center justify-center font-bold
              ${ms.reached ? 'bg-emerald-500 text-white' : 'bg-gray-200 text-gray-400'}`}>
              {ms.reached ? '✓' : ms.percentage}
            </div>
            <span className="text-gray-400 mt-0.5">{ms.percentage}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function GoalCard({ goal, onDeposit, onDelete }: GoalCardProps) {
  return (
    <div className={`p-4 rounded-xl border ${goal.is_completed
      ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-900/20'
      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{goal.icon}</span>
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">{goal.name}</h3>
            {goal.description && (
              <p className="text-xs text-gray-500 dark:text-gray-400">{goal.description}</p>
            )}
          </div>
        </div>
        <div className="flex gap-1">
          {!goal.is_completed && (
            <button onClick={() => onDeposit(goal.id)}
              className="text-xs px-2 py-1 bg-emerald-100 hover:bg-emerald-200 text-emerald-700 rounded-lg transition-colors">
              + Deposit
            </button>
          )}
          <button onClick={() => onDelete(goal.id)}
            className="text-xs px-2 py-1 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg transition-colors">
            ✕
          </button>
        </div>
      </div>
      <MilestoneTrack goal={goal} />
      {goal.is_completed && (
        <div className="mt-2 text-center text-emerald-600 font-semibold text-sm">🎉 Goal reached!</div>
      )}
      {goal.deadline && (
        <p className="mt-1 text-xs text-gray-400">
          Deadline: {new Date(goal.deadline).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}

function CreateGoalModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState<SavingsGoalCreate>({ name: '', target_amount: 0, currency: 'INR', icon: '🎯' });
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr('');
    if (!form.name.trim()) return setErr('Name is required');
    if (form.target_amount <= 0) return setErr('Target amount must be positive');
    setLoading(true);
    try {
      await createGoal(form);
      onCreated();
      onClose();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed to create goal');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <form onSubmit={handleSubmit}
        className="bg-white dark:bg-gray-800 rounded-2xl p-6 w-full max-w-md shadow-xl space-y-4">
        <h2 className="text-lg font-semibold">New Savings Goal</h2>
        {err && <p className="text-red-500 text-sm">{err}</p>}
        <div className="flex gap-2">
          <input value={form.icon} onChange={e => setForm(f => ({ ...f, icon: e.target.value }))}
            className="border rounded-lg p-2 w-14 text-center text-2xl" maxLength={2} />
          <input placeholder="Goal name" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            className="border rounded-lg p-2 flex-1 dark:bg-gray-700 dark:border-gray-600" required />
        </div>
        <input type="number" placeholder="Target amount" value={form.target_amount || ''}
          onChange={e => setForm(f => ({ ...f, target_amount: parseFloat(e.target.value) || 0 }))}
          className="border rounded-lg p-2 w-full dark:bg-gray-700 dark:border-gray-600" min="1" required />
        <input type="text" placeholder="Currency (e.g. USD)" value={form.currency}
          onChange={e => setForm(f => ({ ...f, currency: e.target.value.toUpperCase() }))}
          className="border rounded-lg p-2 w-full dark:bg-gray-700 dark:border-gray-600" maxLength={3} />
        <input type="date" placeholder="Deadline (optional)" value={form.deadline || ''}
          onChange={e => setForm(f => ({ ...f, deadline: e.target.value || null }))}
          className="border rounded-lg p-2 w-full dark:bg-gray-700 dark:border-gray-600" />
        <textarea placeholder="Description (optional)" value={form.description || ''}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          className="border rounded-lg p-2 w-full dark:bg-gray-700 dark:border-gray-600 resize-none" rows={2} />
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-lg border text-gray-600 hover:bg-gray-50">Cancel</button>
          <button type="submit" disabled={loading}
            className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white font-medium disabled:opacity-60">
            {loading ? 'Creating…' : 'Create Goal'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function GoalsPage() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [depositGoalId, setDepositGoalId] = useState<number | null>(null);
  const [depositAmount, setDepositAmount] = useState('');

  const fetchGoals = useCallback(async () => {
    setLoading(true);
    try { setGoals(await listGoals()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchGoals(); }, [fetchGoals]);

  async function handleDeposit() {
    if (!depositGoalId || !depositAmount) return;
    await depositToGoal(depositGoalId, parseFloat(depositAmount));
    setDepositGoalId(null);
    setDepositAmount('');
    fetchGoals();
  }

  async function handleDelete(id: number) {
    if (confirm('Delete this goal?')) { await deleteGoal(id); fetchGoals(); }
  }

  const active    = goals.filter(g => !g.is_completed);
  const completed = goals.filter(g => g.is_completed);

  return (
    <div className="max-w-2xl mx-auto p-4 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">💰 Savings Goals</h1>
        <button onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl font-medium">
          + New Goal
        </button>
      </div>

      {loading ? (
        <p className="text-gray-400 text-center py-8">Loading goals…</p>
      ) : goals.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p className="text-4xl mb-2">🎯</p>
          <p className="font-medium">No savings goals yet</p>
          <p className="text-sm">Create your first goal to start tracking progress</p>
        </div>
      ) : (
        <>
          {active.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Active</h2>
              {active.map(g => (
                <GoalCard key={g.id} goal={g}
                  onDeposit={id => setDepositGoalId(id)}
                  onDelete={handleDelete} />
              ))}
            </section>
          )}
          {completed.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Completed 🎉</h2>
              {completed.map(g => (
                <GoalCard key={g.id} goal={g} onDeposit={() => {}} onDelete={handleDelete} />
              ))}
            </section>
          )}
        </>
      )}

      {showCreate && (
        <CreateGoalModal onClose={() => setShowCreate(false)} onCreated={fetchGoals} />
      )}

      {depositGoalId !== null && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 w-full max-w-sm shadow-xl space-y-4">
            <h2 className="text-lg font-semibold">Add Deposit</h2>
            <input type="number" placeholder="Amount" value={depositAmount}
              onChange={e => setDepositAmount(e.target.value)}
              className="border rounded-lg p-2 w-full dark:bg-gray-700 dark:border-gray-600" min="1" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setDepositGoalId(null)}
                className="px-4 py-2 rounded-lg border text-gray-600">Cancel</button>
              <button onClick={handleDeposit}
                className="px-4 py-2 rounded-lg bg-emerald-500 text-white font-medium">
                Deposit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
