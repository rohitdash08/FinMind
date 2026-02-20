import { useState, useEffect } from 'react';
import {
  getHousehold,
  createHousehold,
  getInviteCode,
  joinHousehold,
  getMembers,
  getHouseholdExpenses,
  Household as HouseholdType,
  HouseholdMember,
  HouseholdExpense,
} from '@/api/household';

export default function Household() {
  const [household, setHousehold] = useState<HouseholdType | null>(null);
  const [members, setMembers] = useState<HouseholdMember[]>([]);
  const [expenses, setExpenses] = useState<HouseholdExpense[]>([]);
  const [inviteCode, setInviteCode] = useState('');
  const [name, setName] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const loadHousehold = async () => {
    try {
      const h = await getHousehold();
      setHousehold(h);
      const [m, e] = await Promise.all([getMembers(), getHouseholdExpenses()]);
      setMembers(m);
      setExpenses(e);
    } catch {
      setHousehold(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadHousehold(); }, []);

  const handleCreate = async () => {
    setError('');
    try {
      await createHousehold(name);
      await loadHousehold();
    } catch (e: any) { setError(e.message); }
  };

  const handleJoin = async () => {
    setError('');
    try {
      await joinHousehold(joinCode);
      await loadHousehold();
    } catch (e: any) { setError(e.message); }
  };

  const handleInvite = async () => {
    try {
      const res = await getInviteCode();
      setInviteCode(res.invite_code);
    } catch (e: any) { setError(e.message); }
  };

  if (loading) return <div className="p-8">Loading...</div>;

  if (!household) {
    return (
      <div className="max-w-lg mx-auto p-8 space-y-6">
        <h1 className="text-2xl font-bold">Household Budgeting</h1>
        {error && <p className="text-red-500">{error}</p>}

        <div className="space-y-2">
          <h2 className="text-lg font-semibold">Create a Household</h2>
          <input
            className="border rounded px-3 py-2 w-full"
            placeholder="Household name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            className="bg-blue-600 text-white px-4 py-2 rounded"
            onClick={handleCreate}
          >
            Create
          </button>
        </div>

        <div className="space-y-2">
          <h2 className="text-lg font-semibold">Join a Household</h2>
          <input
            className="border rounded px-3 py-2 w-full"
            placeholder="Invite code"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
          />
          <button
            className="bg-green-600 text-white px-4 py-2 rounded"
            onClick={handleJoin}
          >
            Join
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">{household.name}</h1>
      {error && <p className="text-red-500">{error}</p>}

      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Members</h2>
        <ul className="space-y-1">
          {members.map((m) => (
            <li key={m.user_id} className="flex justify-between border-b py-1">
              <span>{m.email}</span>
              <span className="text-sm text-gray-500">{m.role}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Invite</h2>
        <button
          className="bg-blue-600 text-white px-4 py-2 rounded"
          onClick={handleInvite}
        >
          Get Invite Code
        </button>
        {inviteCode && (
          <p className="font-mono bg-gray-100 p-2 rounded">{inviteCode}</p>
        )}
      </div>

      <div className="space-y-2">
        <h2 className="text-lg font-semibold">Shared Expenses</h2>
        {expenses.length === 0 ? (
          <p className="text-gray-500">No shared expenses yet. Add expenses with your household ID.</p>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b">
                <th className="py-1">Date</th>
                <th>Description</th>
                <th>Amount</th>
                <th>Currency</th>
              </tr>
            </thead>
            <tbody>
              {expenses.map((e) => (
                <tr key={e.id} className="border-b">
                  <td className="py-1">{e.date}</td>
                  <td>{e.description}</td>
                  <td>{e.amount.toFixed(2)}</td>
                  <td>{e.currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
