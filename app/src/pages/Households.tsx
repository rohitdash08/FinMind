import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { Users, Plus, Home, Mail, Crown } from 'lucide-react';

interface Household {
  id: number;
  name: string;
  role: string;
  members_count?: number;
  joined_at?: string;
}

interface Member {
  id: number;
  user_id: number;
  email: string;
  role: string;
  joined_at: string;
}

export default function Households() {
  const [households, setHouseholds] = useState<Household[]>([]);
  const [selectedHousehold, setSelectedHousehold] = useState<Household | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isJoinOpen, setIsJoinOpen] = useState(false);
  const [newHouseholdName, setNewHouseholdName] = useState('');
  const [joinHouseholdId, setJoinHouseholdId] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [loading, setLoading] = useState(true);

  const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

  const fetchHouseholds = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/household/households`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setHouseholds(data);
      }
    } catch (error) {
      console.error('Failed to fetch households:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchMembers = async (householdId: number) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/household/households/${householdId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMembers(data.members || []);
      }
    } catch (error) {
      console.error('Failed to fetch members:', error);
    }
  };

  useEffect(() => {
    fetchHouseholds();
  }, []);

  const createHousehold = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/household/households`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: newHouseholdName })
      });
      if (res.ok) {
        setNewHouseholdName('');
        setIsCreateOpen(false);
        fetchHouseholds();
      }
    } catch (error) {
      console.error('Failed to create household:', error);
    }
  };

  const joinHousehold = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/household/households/${joinHouseholdId}/join`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });
      if (res.ok) {
        setJoinHouseholdId('');
        setIsJoinOpen(false);
        fetchHouseholds();
      }
    } catch (error) {
      console.error('Failed to join household:', error);
    }
  };

  const addMember = async () => {
    if (!selectedHousehold || !inviteEmail) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/household/households/${selectedHousehold.id}/members`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: inviteEmail })
      });
      if (res.ok) {
        setInviteEmail('');
        fetchMembers(selectedHousehold.id);
      }
    } catch (error) {
      console.error('Failed to add member:', error);
    }
  };

  const openHousehold = async (household: Household) => {
    setSelectedHousehold(household);
    fetchMembers(household.id);
  };

  if (loading) {
    return <div className="p-6">Loading...</div>;
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Users className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Households</h1>
        </div>
        <div className="flex gap-2">
          <Dialog open={isJoinOpen} onOpenChange={setIsJoinOpen}>
            <DialogTrigger asChild>
              <Button variant="outline">Join Household</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Join Household</DialogTitle>
              </DialogHeader>
              <div className="py-4">
                <Label>Household ID</Label>
                <Input 
                  value={joinHouseholdId}
                  onChange={(e) => setJoinHouseholdId(e.target.value)}
                  placeholder="Enter household ID"
                  className="mt-2"
                />
              </div>
              <DialogFooter>
                <Button onClick={joinHousehold}>Join</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button><Plus className="h-4 w-4 mr-2" />Create Household</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create New Household</DialogTitle>
              </DialogHeader>
              <div className="py-4">
                <Label>Household Name</Label>
                <Input 
                  value={newHouseholdName}
                  onChange={(e) => setNewHouseholdName(e.target.value)}
                  placeholder="e.g., Smith Family"
                  className="mt-2"
                />
              </div>
              <DialogFooter>
                <Button onClick={createHousehold}>Create</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {households.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <Home className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">No households yet. Create one to get started!</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {households.map((household) => (
            <Card 
              key={household.id} 
              className="cursor-pointer hover:bg-accent"
              onClick={() => openHousehold(household)}
            >
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Home className="h-5 w-5" />
                  {household.name}
                  {household.role === 'owner' && <Crown className="h-4 w-4 text-yellow-500" />}
                </CardTitle>
                <CardDescription>
                  {household.members_count} member{household.members_count !== 1 ? 's' : ''}
                </CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}

      {/* Household Details Dialog */}
      {selectedHousehold && (
        <Dialog open={!!selectedHousehold} onOpenChange={() => setSelectedHousehold(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Home className="h-5 w-5" />
                {selectedHousehold.name}
              </DialogTitle>
            </DialogHeader>
            <div className="py-4">
              <h3 className="font-semibold mb-3">Members</h3>
              <div className="space-y-2">
                {members.map((member) => (
                  <div key={member.id} className="flex items-center justify-between p-2 bg-muted rounded">
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-muted-foreground" />
                      <span>{member.email}</span>
                    </div>
                    {member.role === 'owner' && (
                      <span className="text-yellow-500 text-sm flex items-center gap-1">
                        <Crown className="h-3 w-3" /> Owner
                      </span>
                    )}
                  </div>
                ))}
              </div>
              
              {selectedHousehold.role === 'owner' && (
                <div className="mt-4 pt-4 border-t">
                  <Label>Invite Member</Label>
                  <div className="flex gap-2 mt-2">
                    <Input 
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      placeholder="user@example.com"
                    />
                    <Button onClick={addMember} variant="secondary">Add</Button>
                  </div>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
