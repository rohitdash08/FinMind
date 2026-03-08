import React, { useState, useEffect } from 'react';
import { createHousehold, addMember, getHousehold, removeMember } from '@/utils/household';

// Minimal household management UI (in-browser MVP)
export function Household() {
  const [name, setName] = useState('');
  const [owner, setOwner] = useState('');
  const [household, setHousehold] = useState<any | null>(null);
  const [member, setMember] = useState('');
  const [message, setMessage] = useState<string | null>(null);

  const onCreate = () => {
    const h = createHousehold(name || 'Household', owner || undefined);
    setHousehold(h);
    setMessage('Household created');
  };

  const onAdd = () => {
    if (!household?.id) return;
    const existed = household.members.includes(member);
    if (existed) {
      setMessage('Member already in household');
      return;
    }
    addMember(household.id, member);
    // refresh by re-fetching
    const h = getHousehold(household.id);
    setHousehold(h);
    setMember('');
    setMessage(null);
  };

  const onRemove = (m: string) => {
    if (!household?.id) return;
    removeMember(household.id, m);
    const h = getHousehold(household.id);
    setHousehold(h);
  };

  return (
    <div>
      <h2>Household (MVP)</h2>
      <div>
        <input placeholder="Household name" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="Owner (optional)" value={owner} onChange={(e) => setOwner(e.target.value)} />
        <button onClick={onCreate}>Create Household</button>
      </div>
      <div>
        {household && (
          <div>
            <h3>Household: {household.name}</h3>
            <p>ID: {household.id}</p>
            <p>Owner: {household.owner ?? 'N/A'}</p>
            <p>Members: {JSON.stringify(household.members)}</p>
            <input placeholder="Add member (email)" value={member} onChange={(e) => setMember(e.target.value)} />
            <button onClick={onAdd}>Add Member</button>
            <div style={{ marginTop: 12 }}>
              <strong>Manage Members:</strong>
              <ul>
                {household.members.map((m: string) => (
                  <li key={m}>
                    {m} <button onClick={() => onRemove(m)}>Remove</button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
      {message && (
        <div style={{ color: 'green', marginTop: 8 }}>{message}</div>
      )}
    </div>
  );
}

export default Household;
