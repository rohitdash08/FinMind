import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import { CheckCircle, XCircle, AlertCircle, Search, Filter, TrendingUp, Brain } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface Transaction {
  id: string;
  description: string;
  amount: number;
  date: string;
  merchantName?: string;
  suggestedCategory: string;
  confidence: number;
  actualCategory?: string;
  status: 'pending' | 'confirmed' | 'corrected';
  subcategory?: string;
  tags?: string[];
}

interface Category {
  id: string;
  name: string;
  subcategories: string[];
  color: string;
}

const DEFAULT_CATEGORIES: Category[] = [
  { id: 'food', name: 'Food & Dining', subcategories: ['Restaurants', 'Groceries', 'Coffee', 'Fast Food'], color: 'bg-orange-500' },
  { id: 'transport', name: 'Transportation', subcategories: ['Gas', 'Public Transit', 'Uber/Lyft', 'Parking'], color: 'bg-blue-500' },
  { id: 'shopping', name: 'Shopping', subcategories: ['Clothing', 'Electronics', 'Home & Garden', 'Books'], color: 'bg-purple-500' },
  { id: 'bills', name: 'Bills & Utilities', subcategories: ['Electricity', 'Internet', 'Phone', 'Insurance'], color: 'bg-red-500' },
  { id: 'entertainment', name: 'Entertainment', subcategories: ['Movies', 'Streaming', 'Games', 'Events'], color: 'bg-green-500' },
  { id: 'healthcare', name: 'Healthcare', subcategories: ['Doctor', 'Pharmacy', 'Dental', 'Insurance'], color: 'bg-teal-500' },
  { id: 'income', name: 'Income', subcategories: ['Salary', 'Freelance', 'Investment', 'Other'], color: 'bg-emerald-500' },
  { id: 'other', name: 'Other', subcategories: ['Miscellaneous'], color: 'bg-gray-500' }
];

interface TransactionCategorizerProps {
  transactions: Transaction[];
  categories?: Category[];
  onCategoryUpdate: (transactionId: string, category: string, subcategory?: string) => void;
  onBulkCategorize: (rules: any) => void;
  onTrainModel: (corrections: any[]) => void;
}

export const TransactionCategorizer: React.FC<TransactionCategorizerProps> = ({
  transactions,
  categories = DEFAULT_CATEGORIES,
  onCategoryUpdate,
  onBulkCategorize,
  onTrainModel
}) => {
  const [filteredTransactions, setFilteredTransactions] = useState<Transaction[]>(transactions);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(0.7);
  const [showOnlyPending, setShowOnlyPending] = useState<boolean>(true);
  const [bulkRules, setBulkRules] = useState<{ merchant: string; category: string; subcategory: string }[]>([]);
  const [newRule, setNewRule] = useState({ merchant: '', category: '', subcategory: '' });
  const [corrections, setCorrections] = useState<any[]>([]);

  useEffect(() => {
    let filtered = transactions;

    if (showOnlyPending) {
      filtered = filtered.filter(t => t.status === 'pending');
    }

    if (selectedCategory !== 'all') {
      filtered = filtered.filter(t => t.suggestedCategory === selectedCategory || t.actualCategory === selectedCategory);
    }

    if (searchTerm) {
      filtered = filtered.filter(t => 
        t.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.merchantName?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    filtered = filtered.filter(t => t.confidence >= confidenceThreshold);

    setFilteredTransactions(filtered);
  }, [transactions, selectedCategory, searchTerm, confidenceThreshold, showOnlyPending]);

  const handleCategoryConfirm = (transaction: Transaction) => {
    onCategoryUpdate(transaction.id, transaction.suggestedCategory, transaction.subcategory);
  };

  const handleCategoryCorrect = (transaction: Transaction, newCategory: string, newSubcategory?: string) => {
    const correction = {
      transactionId: transaction.id,
      originalCategory: transaction.suggestedCategory,
      correctedCategory: newCategory,
      correctedSubcategory: newSubcategory,
      description: transaction.description,
      merchantName: transaction.merchantName,
      amount: transaction.amount
    };

    setCorrections(prev => [...prev, correction]);
    onCategoryUpdate(transaction.id, newCategory, newSubcategory);
  };

  const handleAddBulkRule = () => {
    if (newRule.merchant && newRule.category) {
      setBulkRules(prev => [...prev, { ...newRule }]);
      setNewRule({ merchant: '', category: '', subcategory: '' });
    }
  };

  const handleApplyBulkRules = () => {
    onBulkCategorize(bulkRules);
    setBulkRules([]);
  };

  const handleTrainModel = () => {
    if (corrections.length > 0) {
      onTrainModel(corrections);
      setCorrections([]);
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-green-600 bg-green-100';
    if (confidence >= 0.6) return 'text-yellow-600 bg-yellow-100';
    return 'text-red-600 bg-red-100';
  };

  const getConfidenceIcon = (confidence: number) => {
    if (confidence >= 0.8) return CheckCircle;
    if (confidence >= 0.6) return AlertCircle;
    return XCircle;
  };

  const getCategoryColor = (categoryId: string) => {
    return categories.find(c => c.id === categoryId)?.color || 'bg-gray-500';
  };

  const pendingCount = transactions.filter(t => t.status === 'pending').length;
  const avgConfidence = transactions.reduce((acc, t) => acc + t.confidence, 0) / transactions.length;

  return (
    <TooltipProvider>
      <div className="space-y-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center space-x-2">
                <AlertCircle className="h-5 w-5 text-orange-500" />
                <div>
                  <p className="text-sm text-gray-600">Pending Review</p>
                  <p className="text-2xl font-bold">{pendingCount}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center space-x-2">
                <Brain className="h-5 w-5 text-blue-500" />
                <div>
                  <p className="text-sm text-gray-600">Avg Confidence</p>
                  <p className="text-2xl font-bold">{(avgConfidence * 100).toFixed(1)}%</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center space-x-2">
                <TrendingUp className="h-5 w-5 text-green-500" />
                <div>
                  <p className="text-sm text-gray-600">Corrections</p>
                  <p className="text-2xl font-bold">{corrections.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Filter className="h-5 w-5" />
              <span>Filters & Search</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <Label htmlFor="search">Search</Label>
                <div className="relative">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                  <Input
                    id="search"
                    placeholder="Search transactions..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="category-filter">Category</Label>
                <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                  <SelectTrigger>
                    <SelectValue placeholder="All categories" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    {categories.map(category => (
                      <SelectItem key={category.id} value={category.id}>
                        {category.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="confidence">Min Confidence</Label>
                <Input
                  id="confidence"
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={confidenceThreshold}
                  onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
                />
                <span className="text-sm text-gray-500">{(confidenceThreshold * 100).toFixed(0)}%</span>
              </div>

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="pending-only"
                  checked={showOnlyPending}
                  onChange={(e) => setShowOnlyPending(e.target.checked)}
                  className="rounded"
                />
                <Label htmlFor="pending-only">Pending Only</Label>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Bulk Rules */}
        <Card>
          <CardHeader>
            <CardTitle>Bulk Categorization Rules</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Input
                placeholder="Merchant name..."
                value={newRule.merchant}
                onChange={(e) => setNewRule(prev => ({ ...prev, merchant: e.target.value }))}
              />
              <Select value={newRule.category} onValueChange={(value) => setNewRule(prev => ({ ...prev, category: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Category" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map(category => (
                    <SelectItem key={category.id} value={category.id}>
                      {category.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                placeholder="Subcategory (optional)"
                value={newRule.subcategory}
                onChange={(e) => setNewRule(prev => ({ ...prev, subcategory: e.target.value }))}
              />
              <Button onClick={handleAddBulkRule}>Add Rule</Button>
            </div>

            {bulkRules.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="font-medium">Active Rules ({bulkRules.length})</h4>
                  <Button onClick={handleApplyBulkRules} size="sm">Apply All Rules</Button>
                </div>
                <div className="space-y-1">
                  {bulkRules.map((rule, index) => (
                    <div key={index} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span className="text-sm">
                        <strong>{rule.merchant}</strong> → {categories.find(c => c.id === rule.category)?.name}
                        {rule.subcategory && ` (${rule.subcategory})`}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setBulkRules(prev => prev.filter((_, i) => i !== index))}
                      >
                        Remove
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Transaction List */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Transactions ({filteredTransactions.length})</span>
              {corrections.length > 0 && (
                <Button onClick={handleTrainModel} className="flex items-center space-x-2">
                  <Brain className="h-4 w-4" />
                  <span>Train Model ({corrections.length} corrections)</span>
                </Button>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {filteredTransactions.map(transaction => {
                const ConfidenceIcon = getConfidenceIcon(transaction.confidence);
                const category = categories.find(c => c.id === transaction.suggestedCategory);

                return (
                  <div key={transaction.id} className="border rounded-lg p-4 space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <h3 className="font-medium">{transaction.description}</h3>
                          {transaction.merchantName && (
                            <Badge variant="outline">{transaction.merchantName}</Badge>
                          )}
                        </div>
                        <div className="flex items-center space-x-4 mt-1 text-sm text-gray-600">
                          <span>${Math.abs(transaction.amount).toFixed(2)}</span>
                          <span>{new Date(transaction.date).toLocaleDateString()}</span>
                        </div>
                      </div>

                      <div className="flex items-center space-x-2">
                        <Tooltip>
                          <TooltipTrigger>
                            <div className={`flex items-center space-x-1 px-2 py-1 rounded text-xs ${getConfidenceColor(transaction.confidence)}`}>
                              <ConfidenceIcon className="h-3 w-3" />
                              <span>{(transaction.confidence * 100).toFixed(0)}%</span>
                            </div>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p>AI Confidence: {(transaction.confidence * 100).toFixed(1)}%</p>
                          </TooltipContent>
                        </Tooltip>
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Badge className={`${getCategoryColor(transaction.suggestedCategory)} text-white`}>
                          {category?.name || transaction.suggestedCategory}
                        </Badge>
                        {transaction.subcategory && (
                          <Badge variant="outline">{transaction.subcategory}</Badge>
                        )}
                      </div>

                      <div className="flex items-center space-x-2">
                        {transaction.status === 'pending' && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleCategoryConfirm(transaction)}
                              className="text-green-600 border-green-600 hover:bg-green-50"
                            >
                              <CheckCircle className="h-4 w-4 mr-1" />
                              Confirm
                            </Button>
                            
                            <Select
                              onValueChange={(value) => {
                                const [categoryId, subcategory] = value.split('|');
                                handleCategoryCorrect(transaction, categoryId, subcategory);
                              }}
                            >
                              <SelectTrigger className="w-32">
                                <SelectValue placeholder="Correct" />
                              </SelectTrigger>
                              <SelectContent>
                                {categories.map(cat => (
                                  <div key={cat.id}>
                                    <SelectItem value={cat.id}>{cat.name}</SelectItem>
                                    {cat.subcategories.map(sub => (
                                      <SelectItem key={`${cat.id}|${sub}`} value={`${cat.id}|${sub}`} className="pl-6">
                                        {sub}
                                      </SelectItem>
                                    ))}
                                  </div>
                                ))}
                              </SelectContent>
                            </Select>
                          </>
                        )}

                        {transaction.status === 'confirmed' && (
                          <Badge className="bg-green-500 text-white">Confirmed</Badge>
                        )}

                        {transaction.status === 'corrected' && (
                          <Badge className="bg-blue-500 text-white">Corrected</Badge>
                        )}
                      </div>
                    </div>

                    {transaction.tags && transaction.tags.length > 0 && (
                      <div className="flex items-center space-x-1">
                        {transaction.tags.map(tag => (
                          <Badge key={tag} variant="secondary" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}

              {filteredTransactions.length === 0 && (
                <div className="text-center py-8 text-gray-500">
                  <AlertCircle className="h-8 w-8 mx-auto mb-2" />
                  <p>No transactions match your current filters.</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
};