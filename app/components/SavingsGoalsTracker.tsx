'use client';

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, Target, Calendar, DollarSign, Trophy, Edit, Trash2 } from 'lucide-react';

interface Milestone {
  id: string;
  amount: number;
  description: string;
  achieved: boolean;
  achievedDate?: string;
}

interface SavingsGoal {
  id: string;
  title: string;
  description: string;
  targetAmount: number;
  currentAmount: number;
  targetDate: string;
  category: string;
  milestones: Milestone[];
  createdDate: string;
  priority: 'low' | 'medium' | 'high';
}

const SavingsGoalsTracker: React.FC = () => {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<SavingsGoal | null>(null);
  const [newGoal, setNewGoal] = useState<Partial<SavingsGoal>>({
    title: '',
    description: '',
    targetAmount: 0,
    currentAmount: 0,
    targetDate: '',
    category: '',
    priority: 'medium',
    milestones: []
  });

  const categories = [
    'Emergency Fund',
    'Vacation',
    'Home Purchase',
    'Car Purchase',
    'Education',
    'Retirement',
    'Investment',
    'Other'
  ];

  useEffect(() => {
    loadGoals();
  }, []);

  const loadGoals = () => {
    const savedGoals = localStorage.getItem('savingsGoals');
    if (savedGoals) {
      setGoals(JSON.parse(savedGoals));
    }
  };

  const saveGoals = (updatedGoals: SavingsGoal[]) => {
    setGoals(updatedGoals);
    localStorage.setItem('savingsGoals', JSON.stringify(updatedGoals));
  };

  const createGoal = () => {
    if (!newGoal.title || !newGoal.targetAmount || !newGoal.targetDate) return;

    const goal: SavingsGoal = {
      ...newGoal as SavingsGoal,
      id: Date.now().toString(),
      currentAmount: newGoal.currentAmount || 0,
      milestones: generateMilestones(newGoal.targetAmount || 0),
      createdDate: new Date().toISOString()
    };

    const updatedGoals = [...goals, goal];
    saveGoals(updatedGoals);
    setNewGoal({
      title: '',
      description: '',
      targetAmount: 0,
      currentAmount: 0,
      targetDate: '',
      category: '',
      priority: 'medium',
      milestones: []
    });
    setIsCreateDialogOpen(false);
  };

  const generateMilestones = (targetAmount: number): Milestone[] => {
    const percentages = [25, 50, 75, 90];
    return percentages.map((percentage, index) => ({
      id: `milestone-${index}`,
      amount: Math.round((targetAmount * percentage) / 100),
      description: `${percentage}% of target reached`,
      achieved: false
    }));
  };

  const updateGoal = () => {
    if (!editingGoal) return;

    const updatedGoals = goals.map(goal =>
      goal.id === editingGoal.id ? editingGoal : goal
    );
    saveGoals(updatedGoals);
    setEditingGoal(null);
    setIsEditDialogOpen(false);
  };

  const deleteGoal = (goalId: string) => {
    const updatedGoals = goals.filter(goal => goal.id !== goalId);
    saveGoals(updatedGoals);
  };

  const updateCurrentAmount = (goalId: string, amount: number) => {
    const updatedGoals = goals.map(goal => {
      if (goal.id === goalId) {
        const updatedGoal = { ...goal, currentAmount: amount };
        
        // Update milestone achievements
        updatedGoal.milestones = goal.milestones.map(milestone => ({
          ...milestone,
          achieved: amount >= milestone.amount,
          achievedDate: amount >= milestone.amount && !milestone.achieved 
            ? new Date().toISOString() 
            : milestone.achievedDate
        }));

        return updatedGoal;
      }
      return goal;
    });
    saveGoals(updatedGoals);
  };

  const getProgressPercentage = (goal: SavingsGoal): number => {
    return Math.min((goal.currentAmount / goal.targetAmount) * 100, 100);
  };

  const getDaysRemaining = (targetDate: string): number => {
    const target = new Date(targetDate);
    const today = new Date();
    const diffTime = target.getTime() - today.getTime();
    return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  };

  const getPriorityColor = (priority: string): string => {
    switch (priority) {
      case 'high': return 'bg-red-100 text-red-800';
      case 'medium': return 'bg-yellow-100 text-yellow-800';
      case 'low': return 'bg-green-100 text-green-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Savings Goals</h1>
          <p className="text-gray-600 mt-1">Track your financial goals and celebrate milestones</p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button className="flex items-center gap-2">
              <Plus className="h-4 w-4" />
              New Goal
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Create New Savings Goal</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label htmlFor="title">Goal Title</Label>
                <Input
                  id="title"
                  value={newGoal.title || ''}
                  onChange={(e) => setNewGoal({ ...newGoal, title: e.target.value })}
                  placeholder="e.g., Emergency Fund"
                />
              </div>
              <div>
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={newGoal.description || ''}
                  onChange={(e) => setNewGoal({ ...newGoal, description: e.target.value })}
                  placeholder="Describe your goal..."
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="targetAmount">Target Amount</Label>
                  <Input
                    id="targetAmount"
                    type="number"
                    value={newGoal.targetAmount || ''}
                    onChange={(e) => setNewGoal({ ...newGoal, targetAmount: Number(e.target.value) })}
                    placeholder="0"
                  />
                </div>
                <div>
                  <Label htmlFor="currentAmount">Current Amount</Label>
                  <Input
                    id="currentAmount"
                    type="number"
                    value={newGoal.currentAmount || ''}
                    onChange={(e) => setNewGoal({ ...newGoal, currentAmount: Number(e.target.value) })}
                    placeholder="0"
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="targetDate">Target Date</Label>
                <Input
                  id="targetDate"
                  type="date"
                  value={newGoal.targetDate || ''}
                  onChange={(e) => setNewGoal({ ...newGoal, targetDate: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="category">Category</Label>
                  <Select onValueChange={(value) => setNewGoal({ ...newGoal, category: value })}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select category" />
                    </SelectTrigger>
                    <SelectContent>
                      {categories.map(category => (
                        <SelectItem key={category} value={category}>
                          {category}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="priority">Priority</Label>
                  <Select onValueChange={(value: 'low' | 'medium' | 'high') => setNewGoal({ ...newGoal, priority: value })}>
                    <SelectTrigger>
                      <SelectValue placeholder="Medium" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={createGoal}>Create Goal</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Goals Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {goals.map(goal => (
          <Card key={goal.id} className="hover:shadow-lg transition-shadow">
            <CardHeader className="pb-3">
              <div className="flex justify-between items-start">
                <div>
                  <CardTitle className="text-lg">{goal.title}</CardTitle>
                  <p className="text-sm text-gray-600 mt-1">{goal.description}</p>
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setEditingGoal(goal);
                      setIsEditDialogOpen(true);
                    }}
                  >
                    <Edit className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteGoal(goal.id)}
                  >
                    <Trash2 className="h-4 w-4 text-red-500" />
                  </Button>
                </div>
              </div>
              <div className="flex gap-2 mt-2">
                <Badge variant="secondary">{goal.category}</Badge>
                <Badge className={getPriorityColor(goal.priority)}>
                  {goal.priority}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {/* Progress Section */}
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Progress</span>
                  <span className="text-sm font-semibold">
                    {getProgressPercentage(goal).toFixed(1)}%
                  </span>
                </div>
                <Progress value={getProgressPercentage(goal)} className="h-2" />
                <div className="flex justify-between text-sm">
                  <span>${goal.currentAmount.toLocaleString()}</span>
                  <span>${goal.targetAmount.toLocaleString()}</span>
                </div>
              </div>

              {/* Amount Input */}
              <div className="mt-4">
                <Label htmlFor={`amount-${goal.id}`} className="text-sm">Update Amount</Label>
                <div className="flex gap-2 mt-1">
                  <Input
                    id={`amount-${goal.id}`}
                    type="number"
                    placeholder="Enter amount"
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        const input = e.target as HTMLInputElement;
                        updateCurrentAmount(goal.id, Number(input.value));
                        input.value = '';
                      }
                    }}
                  />
                  <Button
                    size="sm"
                    onClick={() => {
                      const input = document.getElementById(`amount-${goal.id}`) as HTMLInputElement;
                      updateCurrentAmount(goal.id, Number(input.value));
                      input.value = '';
                    }}
                  >
                    Update
                  </Button>
                </div>
              </div>

              {/* Milestones */}
              <div className="mt-4">
                <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <Trophy className="h-4 w-4" />
                  Milestones
                </h4>
                <div className="space-y-2">
                  {goal.milestones.map((milestone, index) => (
                    <div
                      key={milestone.id}
                      className={`flex items-center justify-between p-2 rounded text-sm ${
                        milestone.achieved
                          ? 'bg-green-50 text-green-800'
                          : 'bg-gray-50 text-gray-600'
                      }`}
                    >
                      <span>{milestone.description}</span>
                      <div className="flex items-center gap-2">
                        <span>${milestone.amount.toLocaleString()}</span>
                        {milestone.achieved && <Trophy className="h-3 w-3 text-green-600" />}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Goal Info */}
              <div className="mt-4 pt-3 border-t space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-gray-600">
                    <Calendar className="h-4 w-4" />
                    Target Date
                  </span>
                  <span>{new Date(goal.targetDate).toLocaleDateString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-gray-600">
                    <Target className="h-4 w-4" />
                    Days Remaining
                  </span>
                  <span className={getDaysRemaining(goal.targetDate) < 30 ? 'text-red-600 font-semibold' : ''}>
                    {getDaysRemaining(goal.targetDate)} days
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-gray-600">
                    <DollarSign className="h-4 w-4" />
                    Remaining
                  </span>
                  <span>${(goal.targetAmount - goal.currentAmount).toLocaleString()}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {goals.length === 0 && (
        <div className="text-center py-12">
          <Target className="h-16 w-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">No savings goals yet</h3>
          <p className="text-gray-600 mb-4">Create your first savings goal to start tracking your progress</p>
          <Button onClick={() => setIsCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Create Your First Goal
          </Button>
        </div>
      )}

      {/* Edit Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Savings Goal</DialogTitle>
          </DialogHeader>
          {editingGoal && (
            <div className="space-y-4">
              <div>
                <Label htmlFor="edit-title">Goal Title</Label>
                <Input
                  id="edit-title"
                  value={editingGoal.title}
                  onChange={(e) => setEditingGoal({ ...editingGoal, title: e.target.value })}
                />
              </div>
              <div>
                <Label htmlFor="edit-description">Description</Label>
                <Textarea
                  id="edit-description"
                  value={editingGoal.description}
                  onChange={(e) => setEditingGoal({ ...editingGoal, description: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="edit-targetAmount">Target Amount</Label>
                  <Input
                    id="edit-targetAmount"
                    type="number"
                    value={editingGoal.targetAmount}
                    onChange={(e) => setEditingGoal({ ...editingGoal, targetAmount: Number(e.target.value) })}
                  />
                </div>
                <div>
                  <Label htmlFor="edit-currentAmount">Current Amount</Label>
                  <Input
                    id="edit-currentAmount"
                    type="number"
                    value={editingGoal.currentAmount}
                    onChange={(e) => setEditingGoal({ ...editingGoal, currentAmount: Number(e.target.value) })}
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="edit-targetDate">Target Date</Label>
                <Input
                  id="edit-targetDate"
                  type="date"
                  value={editingGoal.targetDate}
                  onChange={(e) => setEditingGoal({ ...editingGoal, targetDate: e.target.value })}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={updateGoal}>Update Goal</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SavingsGoalsTracker;