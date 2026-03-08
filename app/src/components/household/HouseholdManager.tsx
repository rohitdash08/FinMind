import React, { useEffect, useState } from 'react';
import { getMembers, addMember, removeMember } from '../../utils/household';

type HouseholdMember = {
  email: string;
  name?: string;
  role?: string;
  joinedAt: string;
};

const HouseholdManager: React.FC = () => {
  const [members, setMembers] = useState<HouseholdMember[]>([]);
  const [email, setEmail] = useState<string>('');
  const [name, setName] = useState<string>('');
  const [role, setRole] = useState<string>('');

  useEffect(() => {
    setMembers(getMembers() as HouseholdMember[]);
  }, []);

  const handleAdd = () => {
    const trimmed = email.trim();
    if (!trimmed) return;
    addMember(trimmed, name.trim() || undefined, role.trim() || undefined);
    setEmail('');
    setName('');
    setRole('');
    setMembers(getMembers() as HouseholdMember[]);
  };

  const handleRemove = (e: string) => {
    removeMember(e);
    setMembers(getMembers() as HouseholdMember[]);
  };

  return (
    <section aria-label="Household Collaboration" style={{ border: '1px solid #e5e7eb', padding: 16, borderRadius: 8, margin: 16 }}>
      <h3>Household Collaboration</h3>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input
          placeholder="Email of member"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{ padding: '8px 10px', borderRadius: 4, border: '1px solid #d1d5db' }}
        />
        <input
          placeholder="Name (optional)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{ padding: '8px 10px', borderRadius: 4, border: '1px solid #d1d5db' }}
        />
        <input
          placeholder="Role (optional)"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          style={{ padding: '8px 10px', borderRadius: 4, border: '1px solid #d1d5db' }}
        />
        <button onClick={handleAdd} style={{ padding: '8px 12px', borderRadius: 4, border: 'none', background: '#4f46e5', color: '#fff' }}>
          Add Member
        </button>
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {members.map((m) => (
          <li key={m.email} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f0f0f0' }}>
            <span>
              {m.email} {m.name ? `(${m.name})` : ''} {m.role ? `- ${m.role}` : ''}
              <span style={{ marginLeft: 8, color: '#6b7280', fontSize: 12 }}>
                joined {new Date(m.joinedAt).toLocaleDateString()}
              </span>
            </span>
            <button onClick={() => handleRemove(m.email)} style={{ padding: '4px 8px', borderRadius: 4, border: 'none', background: '#f87171', color: '#fff' }}>
              Remove
            </button>
          </li>
        ))}
        {members.length === 0 && (
          <li style={{ color: '#6b7280' }}>No members yet. Add someone to collaborate on this FinMind household.</li>
        )}
      </ul>
    </section>
  );
};

export default HouseholdManager;
