import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle } from 'lucide-react';

interface FinancialMetric {
  name: string;
  value: number;
  weight: number;
  status: 'excellent' | 'good' | 'fair' | 'poor';
  trend: 'up' | 'down' | 'stable';
  description: string;
}

interface FinancialHealthDashboardProps {
  overallScore: number;
  metrics: FinancialMetric[];
  lastUpdated: string;
}

const FinancialHealthDashboard: React.FC<FinancialHealthDashboardProps> = ({
  overallScore,
  metrics,
  lastUpdated
}) => {
  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    if (score >= 40) return 'text-orange-600';
    return 'text-red-600';
  };

  const getScoreLabel = (score: number) => {
    if (score >= 80) return 'Excellent';
    if (score >= 60) return 'Good';
    if (score >= 40) return 'Fair';
    return 'Poor';
  };

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'excellent': return 'default';
      case 'good': return 'secondary';
      case 'fair': return 'outline';
      case 'poor': return 'destructive';
      default: return 'outline';
    }
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up': return <TrendingUp className="w-4 h-4 text-green-500" />;
      case 'down': return <TrendingDown className="w-4 h-4 text-red-500" />;
      default: return <CheckCircle className="w-4 h-4 text-gray-500" />;
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            Financial Health Score
            <span className={`text-3xl font-bold ${getScoreColor(overallScore)}`}>
              {overallScore}
            </span>
          </CardTitle>
          <CardDescription>
            Overall financial health assessment • Last updated: {lastUpdated}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Progress value={overallScore} className="flex-1 mr-4" />
              <Badge variant={getStatusBadgeVariant(getScoreLabel(overallScore).toLowerCase())}>
                {getScoreLabel(overallScore)}
              </Badge>
            </div>
            {overallScore < 60 && (
              <div className="flex items-center space-x-2 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                <AlertTriangle className="w-4 h-4 text-yellow-600" />
                <span className="text-sm text-yellow-800">
                  Your financial health needs attention. Review the metrics below for improvement areas.
                </span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Metric Breakdown</CardTitle>
          <CardDescription>
            Detailed analysis of each financial health component
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {metrics.map((metric, index) => (
              <div key={index} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="font-medium">{metric.name}</span>
                    {getTrendIcon(metric.trend)}
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm text-gray-600">Weight: {metric.weight}%</span>
                    <Badge variant={getStatusBadgeVariant(metric.status)}>
                      {metric.status}
                    </Badge>
                  </div>
                </div>
                <Progress value={metric.value} className="h-2" />
                <div className="flex items-center justify-between text-sm text-gray-600">
                  <span>{metric.description}</span>
                  <span className={getScoreColor(metric.value)}>
                    {metric.value}/100
                  </span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recommendations</CardTitle>
          <CardDescription>
            Actions to improve your financial health score
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {metrics
              .filter(metric => metric.value < 70)
              .map((metric, index) => (
                <div key={index} className="flex items-start space-x-3 p-3 bg-blue-50 border border-blue-200 rounded-md">
                  <AlertTriangle className="w-4 h-4 text-blue-600 mt-0.5" />
                  <div>
                    <span className="font-medium text-blue-900">
                      Improve {metric.name}
                    </span>
                    <p className="text-sm text-blue-700 mt-1">
                      {metric.name === 'Emergency Fund Ratio' && 'Build your emergency fund to cover 3-6 months of expenses'}
                      {metric.name === 'Debt-to-Income Ratio' && 'Focus on paying down high-interest debt to reduce your debt burden'}
                      {metric.name === 'Savings Rate' && 'Increase your monthly savings by reviewing and optimizing your budget'}
                      {metric.name === 'Credit Utilization' && 'Keep credit card balances below 30% of available credit limits'}
                      {metric.name === 'Investment Diversification' && 'Diversify your portfolio across different asset classes and sectors'}
                    </p>
                  </div>
                </div>
              ))}
            {metrics.every(metric => metric.value >= 70) && (
              <div className="flex items-start space-x-3 p-3 bg-green-50 border border-green-200 rounded-md">
                <CheckCircle className="w-4 h-4 text-green-600 mt-0.5" />
                <div>
                  <span className="font-medium text-green-900">
                    Great job!
                  </span>
                  <p className="text-sm text-green-700 mt-1">
                    All your financial metrics are performing well. Continue maintaining these healthy habits.
                  </p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default FinancialHealthDashboard;