import React, { useState } from 'react';
import { createHousehold, addMember, getHousehold } from '@/utils/household';

// Minimal household management UI (in-browser MVP)
export function Household() {
  const [name, setName] = useState('');
  const [owner, setOwner] = useState('');
  const [household, setHousehold] = useState<any | null>(null);
  const [member, setMember] = useState('');

  const onCreate = () => {
    const h = createHousehold(name || 'Household', owner || undefined);
    setHousehold(h);
  };

  const onAdd = () => {
    if (!household?.id) return;
    addMember(household.id, member);
    // refresh by re-fetching
    const h = getHousehold(household.id);
    setHousehold(h);
    setMember('');
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
          </div>
        )}
      </div>
    </div>
  );
}

export default Household;
